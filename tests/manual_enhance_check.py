"""MANUAL live check of the input-enhancement flow (not collected by the automated suites; needs GROQ_API_KEY and network).
Replaces the former Ollama-era script of a different name, which no longer matched the code. Run: python tests/manual_enhance_check.py"""
import os
import sys

sys.path.append(os.path.abspath("."))
from src.input_guard.input_validator import InputValidatorGuard

if not os.environ.get("GROQ_API_KEY"):
    raise SystemExit("GROQ_API_KEY is not set; nothing to check.")
guard = InputValidatorGuard()
for text in ["fever", "hypotonia", "pt has dev delay and seizures since 2 yrs", "patient has fever and cough"]:
    res = guard.enhance_text(text)
    print(f"\n--- INPUT: '{text}' ---\nStatus: {res.status}\nEnhanced: {res.enhanced_text}\nChanges: {res.changes}")
