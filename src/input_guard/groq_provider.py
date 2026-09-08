import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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
    """
    Backend-only Groq LLM Provider for Clinical Input Enhancement.
    Communicates exclusively backend-to-backend with Groq API.
    """
    def __init__(self, api_key: Optional[str] = None, model: str = "groq/compound-mini"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model = model or os.getenv("GROQ_MODEL", "groq/compound-mini")
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def enhance(self, text: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("Groq API Key not configured.")
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": GROQ_ENHANCEMENT_SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 1000
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                raw_content = res_json["choices"][0]["message"]["content"]
                parsed = json.loads(raw_content)
                return parsed
        except Exception as e:
            logger.error(f"Groq API call error: {e}", exc_info=True)
            return None
