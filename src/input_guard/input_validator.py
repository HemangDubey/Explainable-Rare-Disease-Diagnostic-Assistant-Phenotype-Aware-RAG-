import os
import re
import yaml
import logging
from typing import Dict, Any, Optional
from src.input_guard.content_filter import check_content_safety
from src.input_guard.clinical_relevance import analyze_clinical_relevance
from src.input_guard.schemas import ValidationResponse, EnhanceResponse
from src.input_guard.groq_provider import GroqEnhancementProvider, resolve_model

logger = logging.getLogger(__name__)

_NEG = re.compile(r"\b(no|not|denies|denied|without|never|absent|negative)\b", re.I)
_UNC = re.compile(r"\b(possible|possibly|suspected|probable|likely|query|may)\b", re.I)
_NUM = re.compile(r"\d+(?:\.\d+)?")


def check_enhancement_safety(original: str, enhanced: str):
    """Deterministic guard on the LLM rewrite: numbers must not appear/disappear and negation/uncertainty cues must not vanish."""
    issues = []
    o_nums, e_nums = set(_NUM.findall(original)), set(_NUM.findall(enhanced))
    if e_nums - o_nums:
        issues.append("new number(s) not in the original: " + ", ".join(sorted(e_nums - o_nums)))
    if o_nums - e_nums:
        issues.append("number(s) from the original are missing: " + ", ".join(sorted(o_nums - e_nums)))
    if len(_NEG.findall(original)) > len(_NEG.findall(enhanced)):
        issues.append("a negation present in the original may have been dropped")
    if len(_UNC.findall(original)) > len(_UNC.findall(enhanced)):
        issues.append("an uncertainty marker present in the original may have been dropped")
    return issues

class InputValidatorGuard:
    """
    Input Quality Gate + Groq AI Text Enhancement Engine.
    Performs local deterministic content safety & clinical relevance checks FIRST.
    Sends only valid clinical text to Groq for structured enhancement.
    """
    def __init__(self, groq_api_key: Optional[str] = None, groq_model: Optional[str] = None):
        # Load key from config or env
        key = groq_api_key or os.getenv("GROQ_API_KEY", "")
        if not key:
            try:
                with open("configs/config.yaml", "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                    key = cfg.get("groq", {}).get("api_key", "")
            except Exception:
                pass

        model = groq_model or resolve_model()
        self.groq_provider = GroqEnhancementProvider(api_key=key, model=model)

    def validate_input(self, text: str) -> ValidationResponse:
        """
        Deterministic Input Quality Gate:
        Checks profanity/abuse and clinical relevance BEFORE any LLM call.
        """
        # 1. Deterministic Content Safety Check
        is_safe, safety_reason = check_content_safety(text)
        if not is_safe:
            return ValidationResponse(
                status="INAPPROPRIATE",
                clinical_relevance="NONE",
                reason=safety_reason,
                suggested_action="Please enter relevant clinical information to continue.",
                is_valid_clinical=False
            )

        # 2. Clinical Relevance Analysis
        rel_res = analyze_clinical_relevance(text)
        return ValidationResponse(
            status=rel_res["status"],
            clinical_relevance=rel_res["clinical_relevance"],
            reason=rel_res["reason"],
            suggested_action=rel_res["suggested_action"],
            is_valid_clinical=rel_res["is_valid"]
        )

    def enhance_text(self, text: str) -> EnhanceResponse:
        """
        Enhances clinical text using backend Groq LLM.
        Non-clinical / profane / useless input is rejected BEFORE Groq is called.
        """
        val_res = self.validate_input(text)

        # Step 1: Reject non-clinical / inappropriate input before hitting Groq
        if not val_res.is_valid_clinical:
            return EnhanceResponse(
                status=val_res.status,
                original_text=text,
                enhanced_text=None,
                changes=[],
                added_facts=[],
                removed_facts=[],
                reason=val_res.reason,
                confidence=None
            )

        # Step 2: optional LLM enhancement (only for text that passed the deterministic gate)
        groq_res, call_status = self.groq_provider.enhance_detailed(text)

        if not groq_res:
            logger.warning("Enhancement unavailable (%s).", call_status)
            labels = {"not_configured": ("ENHANCEMENT_UNAVAILABLE", "AI enhancement is not configured on the server."),
                      "auth_error": ("ENHANCEMENT_UNAVAILABLE", "AI enhancement credentials were rejected by the service."),
                      "model_unavailable": ("ENHANCEMENT_UNAVAILABLE", "The configured enhancement model is not available."),
                      "rate_limited": ("ENHANCEMENT_RATE_LIMITED", "AI enhancement is rate-limited right now; try again shortly."),
                      "timeout": ("ENHANCEMENT_TIMEOUT", "AI enhancement timed out."),
                      "invalid_output": ("ENHANCEMENT_MALFORMED", "AI enhancement returned an unusable response."),
                      "provider_unavailable": ("ENHANCEMENT_UNAVAILABLE", "AI enhancement is temporarily unavailable.")}
            st, why = labels.get(call_status, ("ENHANCEMENT_UNAVAILABLE", "AI enhancement is temporarily unavailable."))
            return EnhanceResponse(status=st, original_text=text, enhanced_text=text, changes=[], added_facts=[], removed_facts=[],
                                   reason=why + " You can continue with the original clinical text.", confidence=None)

        # Step 3: Validate and parse Groq response
        enhanced_txt = groq_res.get("enhanced_text") or text
        raw_changes = groq_res.get("changes", [])
        clean_changes = [c for c in raw_changes if c and str(c).strip().lower() != "none"]

        # If text is unchanged or no refinements made, do NOT claim fake refinements
        if enhanced_txt.strip() == text.strip():
            clean_changes = []

        issues = check_enhancement_safety(text, enhanced_txt) if enhanced_txt.strip() != text.strip() else []
        if issues or groq_res.get("added_facts"):
            return EnhanceResponse(status="ENHANCEMENT_REJECTED", original_text=text, enhanced_text=text, changes=[],
                                   added_facts=[str(x) for x in (groq_res.get("added_facts") or [])] + issues, removed_facts=[],
                                   reason="The suggested rewrite was not applied because it may add or change clinical facts. Original text kept.",
                                   confidence=None)

        status = groq_res.get("status", "NEEDS_ENHANCEMENT")
        if status not in {"VALID_CLINICAL", "NEEDS_ENHANCEMENT", "NON_CLINICAL", "INAPPROPRIATE", "INSUFFICIENT"}:
            status = "NEEDS_ENHANCEMENT"

        return EnhanceResponse(
            status=status,
            original_text=text,
            enhanced_text=enhanced_txt,
            changes=clean_changes,
            added_facts=groq_res.get("added_facts", []),
            removed_facts=groq_res.get("removed_facts", []),
            reason=groq_res.get("reason", "Clinical text enhanced for clarity."),
            confidence=None   # no calibrated confidence exists; the former constant 0.95 was removed
        )
