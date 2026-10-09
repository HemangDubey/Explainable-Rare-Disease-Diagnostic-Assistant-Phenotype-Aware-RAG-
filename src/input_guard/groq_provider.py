"""Groq — the project's ONLY LLM provider (backend-only).

`GroqClient` is the single low-level client used by every LLM feature (input enhancement, grounded explanations, copilot).
It never logs or returns the API key or prompts, bounds time and retries, and maps every failure to an explicit exception whose
`status` is safe to show to the UI. `GroqEnhancementProvider` keeps the original input-enhancement contract on top of it.
"""
import json
import re
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"       # verified against the account's /models list and a real completion (see Phase 5R.2 report)


# ---- explicit failure types (status strings are what the API/UI report) -------------------------------------------------
class ProviderError(RuntimeError):
    status = "provider_error"


class ProviderUnavailable(ProviderError):
    status = "provider_unavailable"


class ProviderNotConfigured(ProviderUnavailable):
    status = "not_configured"


class ProviderAuthError(ProviderUnavailable):
    status = "auth_error"


class ProviderModelError(ProviderUnavailable):
    status = "model_unavailable"


class ProviderRateLimited(ProviderUnavailable):
    status = "rate_limited"

    def __init__(self, message: str, retry_after: Optional[float] = None, limit: Optional[str] = None):
        super().__init__(message)
        self.retry_after = retry_after      # seconds the provider asked us to wait (Retry-After header), if given
        self.limit = limit                  # which quota was hit, e.g. "tokens per day (TPD)", parsed from the error body


_LIMIT_RE = re.compile(r"on (tokens per day \(TPD\)|tokens per minute \(TPM\)|requests per day \(RPD\)|requests per minute \(RPM\))")


class ProviderTimeout(ProviderError):
    status = "timeout"


class InvalidModelOutput(ProviderError):
    status = "invalid_output"


_HYPHENS = dict.fromkeys(range(0x2010, 0x2016), "-")
_HYPHENS[0x2212] = "-"


def _ascii_hyphens(obj):
    """Models often emit Unicode hyphens (U+2011 etc.), which breaks evidence-id matching such as 'C1-E12'. Normalise to ASCII '-'."""
    if isinstance(obj, str):
        return obj.translate(_HYPHENS)
    if isinstance(obj, list):
        return [_ascii_hyphens(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _ascii_hyphens(v) for k, v in obj.items()}
    return obj


def resolve_model(config: Optional[Dict[str, Any]] = None) -> str:
    """Single source of truth for the model id: GROQ_MODEL env > config llm.model > built-in default."""
    cfg = ((config or {}).get("llm") or {})
    return os.getenv("GROQ_MODEL") or cfg.get("model") or DEFAULT_MODEL


def _redact(text: str, key: str) -> str:
    return text.replace(key, "<redacted>") if key and text else text


class GroqClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, timeout: float = 30.0, max_retries: int = 2,
                 temperature: float = 0.1, max_tokens: int = 1500, reasoning_effort: Optional[str] = "low",
                 max_retry_wait: float = 30.0, total_timeout: float = 150.0, base_url: str = GROQ_BASE_URL):
        self._key = api_key if api_key is not None else os.getenv("GROQ_API_KEY", "")
        self.model = model or resolve_model()
        self.timeout, self.max_retries = float(timeout), int(max_retries)
        self.temperature, self.max_tokens = temperature, int(max_tokens)
        self.reasoning_effort = reasoning_effort
        self.max_retry_wait = float(max_retry_wait)
        self.total_timeout = float(total_timeout)     # hard wall-clock bound across all retries
        self.base_url = base_url.rstrip("/")
        self.name = "groq"
        self.calls = 0
        self._health: Tuple[float, Dict[str, Any]] = (0.0, {})

    # ---- plumbing --------------------------------------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _request(self, path: str, payload: Optional[Dict[str, Any]], timeout: float):
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        return urllib.request.urlopen(req, timeout=timeout)

    def _map_http(self, e: urllib.error.HTTPError) -> ProviderError:
        code = e.code
        if code in (401, 403):
            return ProviderAuthError("The language-model service rejected the configured credentials (HTTP %d)." % code)
        if code == 404:
            return ProviderModelError("The configured model is not available to this account (HTTP 404).")
        if code == 429:
            try:
                retry_after = float(e.headers.get("retry-after")) if e.headers and e.headers.get("retry-after") else None
            except ValueError:
                retry_after = None
            try:                                            # the body names the quota; it never contains credentials or prompt text
                m = _LIMIT_RE.search(e.read().decode("utf-8", "replace")[:2000])
            except Exception:  # noqa: BLE001
                m = None
            limit = m.group(1) if m else None
            msg = "The language-model service rate limit was reached (HTTP 429" + (f", {limit}" if limit else "") + ")."
            if retry_after:
                msg += f" Try again in about {max(1, round(retry_after / 60))} minute(s)." if retry_after >= 90 else f" Try again in about {int(retry_after)} s."
            return ProviderRateLimited(msg, retry_after=retry_after, limit=limit)
        if code == 400:
            return InvalidModelOutput("The language-model service rejected the request (HTTP 400).")
        if code >= 500:
            return ProviderUnavailable("The language-model service failed (HTTP %d)." % code)
        return ProviderUnavailable("Unexpected response from the language-model service (HTTP %d)." % code)

    # ---- health ----------------------------------------------------------------------------------------------------
    def check_health(self, use_cache: bool = True) -> Dict[str, Any]:
        """Key present + accepted + configured model listed. Does NOT run a completion (use `verify_completion` for that)."""
        if not self.configured:
            return {"status": "not_configured", "model": self.model, "message": "GROQ_API_KEY is not set on the server."}
        if use_cache and time.time() - self._health[0] < 60 and self._health[1]:
            return self._health[1]
        res = {}
        for attempt in range(2):                     # one quick retry: a single dropped connection is not an outage
            try:
                with self._request("/models", None, 8) as r:
                    ids = [m.get("id") for m in json.loads(r.read().decode("utf-8")).get("data", [])]
                res = {"status": "healthy" if self.model in ids else "model_missing", "model": self.model}
                break
            except urllib.error.HTTPError as e:
                res = {"status": self._map_http(e).status if e.code != 404 else "model_missing", "model": self.model}
                break
            except Exception as e:  # noqa: BLE001 - a health probe never raises
                res = {"status": "offline", "model": self.model, "error": type(e).__name__}
                time.sleep(0.5)
        self._health = (time.time(), res) if res["status"] in ("healthy", "model_missing") else (0.0, {})   # never cache failures
        return res

    def verify_completion(self) -> Dict[str, Any]:
        """A real minimal chat completion (HTTP 200 from /models alone is not proof that completions work)."""
        t0 = time.time()
        try:
            data = self.chat_json('Return only a JSON object.', 'Return {"ok": true}', max_tokens=200)
            return {"status": "ok" if data.get("ok") is True else "unexpected_output", "model": self.model, "latency_ms": round((time.time() - t0) * 1000)}
        except ProviderError as e:
            return {"status": e.status, "model": self.model}

    # ---- completion ------------------------------------------------------------------------------------------------
    def chat_json(self, system: str, user: str, max_tokens: Optional[int] = None, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """One JSON-object completion with bounded retries (429/5xx/connection). Raises explicit ProviderError subclasses."""
        if not self.configured:
            raise ProviderNotConfigured("GROQ_API_KEY is not set on the server.")
        payload: Dict[str, Any] = {
            "model": self.model, "temperature": self.temperature, "max_completion_tokens": int(max_tokens or self.max_tokens),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": ({"type": "json_schema", "json_schema": {"name": "answer", "strict": False, "schema": schema}} if schema
                                else {"type": "json_object"})}
        if self.reasoning_effort and self.model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = self.reasoning_effort
        last: Optional[ProviderError] = None
        deadline = time.time() + self.total_timeout
        for attempt in range(self.max_retries + 1):
            remaining = deadline - time.time()
            if remaining <= 1:
                raise last or ProviderTimeout("The language-model request exceeded its total time budget.")
            self.calls += 1
            try:
                with self._request("/chat/completions", payload, min(self.timeout, remaining)) as r:
                    body = json.loads(r.read().decode("utf-8"))
                return self._parse(body)
            except urllib.error.HTTPError as e:
                err = self._map_http(e)
                if e.code == 400 and schema is not None and payload["response_format"].get("type") == "json_schema":
                    payload["response_format"] = {"type": "json_object"}      # model rejected strict schema: fall back to JSON mode
                    last = err
                    continue
                if not isinstance(err, (ProviderRateLimited,)) and not (e.code >= 500):
                    raise err from None
                last = err
                # The provider asked for a longer wait than we are willing to block a request for (e.g. a daily token quota):
                # fail fast instead of sleeping and re-sending, which would only burn time and quota.
                if isinstance(err, ProviderRateLimited) and err.retry_after is not None and err.retry_after > self.max_retry_wait:
                    raise err from None
                wait = min(self.max_retry_wait, float(err.retry_after if getattr(err, "retry_after", None) else 2 ** attempt))
                if attempt < self.max_retries:
                    logger.warning("llm retry %d after HTTP %d (wait %.1fs)", attempt + 1, e.code, wait)
                    time.sleep(max(0.0, min(wait, deadline - time.time() - 1)))
            except (TimeoutError, urllib.error.URLError, OSError) as e:
                timed_out = isinstance(e, TimeoutError) or "timed out" in str(e).lower() or isinstance(getattr(e, "reason", None), TimeoutError)
                last = ProviderTimeout(f"The language-model service did not answer within {self.timeout:.0f}s.") if timed_out else \
                    ProviderUnavailable("Could not connect to the language-model service.")
                if attempt < self.max_retries:
                    time.sleep(min(self.max_retry_wait, 2 ** attempt))
            except ValueError as e:
                raise InvalidModelOutput("The language-model service returned a malformed HTTP body.") from None
        raise last or ProviderUnavailable("The language-model service is unavailable.")

    @staticmethod
    def _parse(body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            raw = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise InvalidModelOutput("The language-model response had no message content.") from None
        if not isinstance(raw, str) or not raw.strip():
            raise InvalidModelOutput("The language-model response was empty.")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            a, b = raw.find("{"), raw.rfind("}")
            try:
                parsed = json.loads(raw[a:b + 1]) if a != -1 and b > a else None
            except json.JSONDecodeError:
                parsed = None
            if parsed is None:
                raise InvalidModelOutput("The language-model response was not valid JSON.") from None
        if not isinstance(parsed, dict):
            raise InvalidModelOutput("The language-model response was not a JSON object.")
        return _ascii_hyphens(parsed)


# ---- input enhancement (original contract preserved) --------------------------------------------------------------------
GROQ_ENHANCEMENT_SYSTEM_PROMPT = """You are a clinical text normalization assistant.
Your task is ONLY to improve the clarity and structure of clinical information explicitly provided by the user.

You must preserve every medical fact exactly.

You MUST NOT:
- invent symptoms
- invent diagnoses
- invent diseases
- invent genes
- invent HPO terms
- invent age
- invent gender
- invent family history
- invent laboratory findings
- invent medications
- invent examination findings
- infer unmentioned medical facts
- convert uncertainty into certainty
- add medically plausible but unstated information

If the input is not clinical information, set status to NON_CLINICAL.
If it contains abusive/profane content, set status to INAPPROPRIATE.
If it is clinically meaningful but poorly written, rewrite it using clear professional clinical language and set status to NEEDS_ENHANCEMENT.
If it is already clear, return it unchanged and set status to VALID_CLINICAL.

Return ONLY a JSON object with:
{
  "status": "VALID_CLINICAL | NEEDS_ENHANCEMENT | NON_CLINICAL | INAPPROPRIATE | INSUFFICIENT",
  "enhanced_text": "Refined clinical text",
  "changes": ["List of specific changes made, e.g. Expanded abbreviation 'pt' to 'Patient'"],
  "added_facts": [],
  "removed_facts": [],
  "reason": "Explanation of changes or status"
}
"""


class GroqEnhancementProvider:
    """Backend-only input enhancement on top of `GroqClient`."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, client: Optional[GroqClient] = None):
        self.client = client or GroqClient(api_key=api_key, model=model or resolve_model(), timeout=20, max_retries=1, max_tokens=1200)
        self.model = self.client.model

    def enhance_detailed(self, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Returns (parsed_json | None, status) with status in ok|not_configured|auth_error|model_unavailable|rate_limited|timeout|provider_unavailable|invalid_output."""
        try:
            return self.client.chat_json(GROQ_ENHANCEMENT_SYSTEM_PROMPT, text), "ok"
        except ProviderError as e:
            logger.warning("Input enhancement unavailable: %s", e.status)
            return None, e.status

    def enhance(self, text: str) -> Optional[Dict[str, Any]]:
        return self.enhance_detailed(text)[0]
