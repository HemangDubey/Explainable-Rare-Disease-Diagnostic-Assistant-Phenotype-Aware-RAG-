import urllib.request
import json
import time

api_key = "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"
models = ["groq/compound-mini", "groq/compound", "qwen/qwen3.6-27b", "openai/gpt-oss-20b"]

for model in models:
    time.sleep(1)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a clinical text normalization assistant. Return JSON object with status, enhanced_text, changes, added_facts, removed_facts, reason."},
            {"role": "user", "content": "pt has dev delay and seizures since 2 yrs"}
        ],
        "response_format": {"type": "json_object"}
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            print(f"\nSUCCESS with model '{model}':")
            print(content)
            break
    except Exception as e:
        print(f"Model '{model}' failed: {e}")
