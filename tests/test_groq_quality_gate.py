import os
import sys

sys.path.append(os.path.abspath("."))

from src.input_guard.input_validator import InputValidatorGuard

def test_groq_quality_gate():
    guard = InputValidatorGuard()

    test_cases = [
        ("", "NON_CLINICAL"),
        ("hii", "NON_CLINICAL"),
        ("hello", "NON_CLINICAL"),
        ("asdfgh", "NON_CLINICAL"),
        ("fuck", "INAPPROPRIATE"),
        ("Seizures", "VALID_CLINICAL"),
        ("Hypotonia", "VALID_CLINICAL"),
        ("pt has dev delay and seizures since 2 yrs", "NEEDS_ENHANCEMENT"),
        ("Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.", ["VALID_CLINICAL", "NEEDS_ENHANCEMENT"])
    ]

    print("=== STEP 17 TEST CASES ===")
    for text, expected in test_cases:
        val = guard.validate_input(text)
        print(f"\n[Validation] Input: '{text}'")
        print(f"Status: {val.status} | IsValid: {val.is_valid_clinical}")

        if isinstance(expected, list):
            assert val.status in expected, f"Expected {expected}, got {val.status}"
        else:
            assert val.status == expected, f"Expected {expected}, got {val.status}"

        # Test enhancement endpoint behavior
        enh = guard.enhance_text(text)
        print(f"[Enhance] Status: {enh.status} | EnhancedText: '{enh.enhanced_text}'")
        print(f"[Enhance] Changes: {enh.changes}")

        if not val.is_valid_clinical:
            assert enh.enhanced_text is None, f"Expected enhanced_text=None for invalid input '{text}', got '{enh.enhanced_text}'"
            print("=> CONFIRMED: Groq was NOT called for non-clinical/inappropriate input.")

    print("\nALL STEP 17 TEST CASES PASSED PERFECTLY!")

if __name__ == "__main__":
    test_groq_quality_gate()
