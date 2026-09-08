import os
import sys

sys.path.append(os.path.abspath("."))

from src.input_guard.input_validator import InputValidatorGuard

def test_guard():
    guard = InputValidatorGuard()

    test_cases = [
        ("hii", "NON_CLINICAL"),
        ("asdfgh", "NON_CLINICAL"),
        ("fuck", "INAPPROPRIATE"),
        ("Seizures", ["VALID_CLINICAL", "NEEDS_ENHANCEMENT"]),
        ("patient has hypotonia and developmental delay", ["VALID_CLINICAL", "NEEDS_ENHANCEMENT"]),
        ("pt has dev delay and seizures since 2 yrs", ["NEEDS_ENHANCEMENT", "VALID_CLINICAL"]),
        ("Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.", ["VALID_CLINICAL", "NEEDS_ENHANCEMENT"])
    ]

    print("=== TESTING INPUT QUALITY GATE ===")
    for text, expected in test_cases:
        res = guard.validate_input(text)
        print(f"\nInput: '{text}'")
        print(f"Status: {res.status} | Relevance: {res.clinical_relevance} | Valid: {res.is_valid_clinical}")
        print(f"Reason: {res.reason}")

        if isinstance(expected, list):
            assert res.status in expected, f"Expected one of {expected}, got {res.status}"
        else:
            assert res.status == expected, f"Expected {expected}, got {res.status}"

    print("\n=== TESTING AI TEXT ENHANCEMENT ===")
    enh_res = guard.enhance_text("pt has dev delay and seizures since 2 yrs")
    print("Original:", enh_res.original_text)
    print("Enhanced:", enh_res.enhanced_text)
    print("Changes:", enh_res.changes)
    assert "Patient" in enh_res.enhanced_text or "developmental delay" in enh_res.enhanced_text

    print("\nALL TEST CASES PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_guard()
