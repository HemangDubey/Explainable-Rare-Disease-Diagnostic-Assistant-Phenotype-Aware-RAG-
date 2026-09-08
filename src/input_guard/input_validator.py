import os
import yaml
import logging
from typing import Dict, Any, Optional
from src.input_guard.content_filter import check_content_safety
from src.input_guard.clinical_relevance import analyze_clinical_relevance
from src.input_guard.schemas import ValidationResponse, EnhanceResponse
from src.input_guard.groq_provider import GroqEnhancementProvider

logger = logging.getLogger(__name__)

class InputValidatorGuard:
    """
    Input Quality Gate + Groq AI Text Enhancement Engine.
    Performs local deterministic content safety & clinical relevance checks FIRST.
    Sends only valid clinical text to Groq for structured enhancement.
    """
    def __init__(self, groq_api_key: Optional[str] = None, groq_model: str = "groq/compound-mini"):
        # Load key from config or env
        key = groq_api_key or os.getenv("GROQ_API_KEY", "")
        if not key:
            try:
                with open("configs/config.yaml", "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                    key = cfg.get("groq", {}).get("api_key", "")
            except Exception:
                pass

        model = groq_model or os.getenv("GROQ_MODEL", "groq/compound-mini")
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

        # Step 2: Call Groq backend provider for valid clinical text
        groq_res = self.groq_provider.enhance(text)

        if not groq_res:
            logger.warning("Groq enhancement unavailable or failed. Returning ENHANCEMENT_UNAVAILABLE status.")
            return EnhanceResponse(
                status="ENHANCEMENT_UNAVAILABLE",
                original_text=text,
                enhanced_text=text,
                changes=[],
                added_facts=[],
                removed_facts=[],
                reason="AI enhancement is temporarily unavailable. You can continue with the original clinical text.",
                confidence=None
            )

        # Step 3: Validate and parse Groq response
        enhanced_txt = groq_res.get("enhanced_text") or text
        raw_changes = groq_res.get("changes", [])
        clean_changes = [c for c in raw_changes if c and str(c).strip().lower() != "none"]

        # If text is unchanged or no refinements made, do NOT claim fake refinements
        if enhanced_txt.strip() == text.strip():
            clean_changes = []

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
            confidence=0.95
        )
