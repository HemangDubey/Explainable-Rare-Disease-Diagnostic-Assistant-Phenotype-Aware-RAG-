"""Manual Groq connectivity check for the input-enhancement utility.

Not collected as an automated test: it makes live network calls and needs
GROQ_API_KEY in the environment (see .env.example). Run explicitly:

    python tests/test_groq.py
"""
import json
import os
import time
import urllib.request

import yaml
MODELS = [os.environ.get("GROQ_MODEL") or yaml.safe_load(open("configs/config.yaml", encoding="utf-8"))["llm"]["model"]]


def main():
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is not set; nothing to test.")
    for model in MODELS:
        time.sleep(1)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a clinical text normalization assistant. Return JSON object with status, enhanced_text, changes, added_facts, removed_facts, reason."},
                {"role": "user", "content": "pt has dev delay and seizures since 2 yrs"},
            ],
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(model, "->", resp.status)
        except Exception as e:  # noqa: BLE001 - manual diagnostic script
            print(model, "-> error:", type(e).__name__)


if __name__ == "__main__":
    main()
