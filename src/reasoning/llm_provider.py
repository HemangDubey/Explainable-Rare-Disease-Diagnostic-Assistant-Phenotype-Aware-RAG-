"""LLM provider interface for the reasoning features. Groq is the ONLY supported provider (Phase 5R.2).

The transport lives in `src.input_guard.groq_provider.GroqClient` (single client for the whole project); this module adapts it to the
`generate_json(prompt, system_prompt)` / `check_health()` contract used by the reasoner and the copilot. Failure types are re-exported
so callers keep a single import location.
"""
import abc
import time
from typing import Any, Dict, Optional, Tuple

from src.input_guard.groq_provider import (  # noqa: F401  (re-exported)
    GroqClient, InvalidModelOutput, ProviderAuthError, ProviderError, ProviderModelError, ProviderNotConfigured, ProviderRateLimited,
    ProviderTimeout, ProviderUnavailable, resolve_model)


class BaseLLMProvider(abc.ABC):
    @abc.abstractmethod
    def generate_json(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    def check_health(self) -> Dict[str, Any]:
        pass

    def generate_json_with_meta(self, prompt: str, system_prompt: str = "") -> Tuple[Dict[str, Any], Dict[str, Any]]:
        t0 = time.time()
        data = self.generate_json(prompt, system_prompt)
        return data, {"latency_ms": round((time.time() - t0) * 1000, 1)}


class GroqProvider(BaseLLMProvider):
    def __init__(self, client: GroqClient):
        self.client = client
        self.name = "llm"

    @property
    def model(self) -> str:
        return self.client.model

    def check_health(self) -> Dict[str, Any]:
        return self.client.check_health()

    def generate_json(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        return self.client.chat_json(system_prompt, prompt)


def get_llm_provider(config: Dict[str, Any]) -> BaseLLMProvider:
    cfg = config.get("llm", {})
    name = str(cfg.get("provider", "groq")).lower()
    if name != "groq":
        raise ValueError(f"Unsupported LLM provider '{name}'. Groq is the only supported provider.")
    return GroqProvider(GroqClient(
        model=resolve_model(config), timeout=float(cfg.get("timeout", 60)), max_retries=int(cfg.get("max_retries", 2)),
        temperature=float(cfg.get("temperature", 0.1)), max_tokens=int(cfg.get("max_tokens", 2500)),
        reasoning_effort=cfg.get("reasoning_effort", "low")))
