import os
import sys
import json
import urllib.request

sys.path.append(os.path.abspath("."))

from src.input_guard.input_validator import InputValidatorGuard
from src.reasoning.llm_provider import get_llm_provider
import yaml

with open("configs/config.yaml") as f:
    cfg = yaml.safe_load(f)

provider = get_llm_provider(cfg)
guard = InputValidatorGuard(llm_provider=provider)

test_inputs = [
    "fever",
    "hypotonia",
    "pt has dev delay and seizures since 2 yrs",
    "patient has fever and cough"
]

for inp in test_inputs:
    res = guard.enhance_text(inp)
    print(f"\n--- INPUT: '{inp}' ---")
    print("Enhanced:", res.enhanced_text)
    print("Changes:", res.changes)
