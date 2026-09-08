import re
from typing import Tuple, Dict, Any

# Common clinical symptom keywords, signs, systems, and shorthand
CLINICAL_KEYWORDS = {
    # Neurological / Developmental
    "seizure", "seizures", "hypotonia", "hypertonia", "delay", "developmental", "intellectual", 
    "microcephaly", "macrocephaly", "ataxia", "epilepsy", "spasticity", "encephalopathy", "palsy",
    "autism", "regression", "speech", "motor", "dystonia", "tremor", "paresis", "headache",

    # Skeletal / Craniofacial / Dysmorphic
    "stature", "short", "tall", "syndactyly", "polydactyly", "craniosynostosis", "dysmorphism", 
    "facies", "scoliosis", "cleft", "palate", "clubfoot", "hypermobility", "contractures", "skeletal",

    # Metabolic / Systemic / Organ
    "acidosis", "lactic", "hepatomegaly", "splenomegaly", "cardiomyopathy", "murmur", "failure", 
    "thrive", "fever", "infection", "infections", "recurrent", "weakness", "muscle", "myopathy", 
    "fatigue", "hypoglycemia", "jaundice", "rhabdomyolysis", "deafness", "blindness", "cataract",
    "retinitis", "pigmentosa", "rash", "skin", "edema", "vomiting", "diarrhea", "anemia",

    # Clinical Shorthand / Abbreviations
    "pt", "pts", "hx", "dx", "sx", "dev", "yrs", "yo", "mth", "mo", "mths", "w/", "w/o", "h/o"
}

NON_CLINICAL_GIBBERISH = {
    "hii", "hi", "hello", "hey", "test", "testing", "asdf", "asdfgh", "asdfghjkl", 
    "qwerty", "what", "what is this", "abc", "xyz", "123", "temp", "foo", "bar",
    "who", "why", "how", "ok", "okay", "yes", "no", "bye", "good"
}

def analyze_clinical_relevance(text: str) -> Dict[str, Any]:
    """
    Analyzes text clinical relevance.
    Distinguishes SHORT BUT CLINICAL (e.g. 'Seizures', 'Hypotonia') from SHORT AND USELESS ('hii', 'test', 'asdfgh').
    """
    cleaned = text.strip()
    if not cleaned:
        return {
            "status": "NON_CLINICAL",
            "clinical_relevance": "NONE",
            "reason": "Clinical input area is empty.",
            "suggested_action": "Please enter clinical observations, symptoms, or physical findings.",
            "is_valid": False
        }

    lower_text = cleaned.lower()

    # Check known casual / test non-clinical input
    if lower_text in NON_CLINICAL_GIBBERISH or len(cleaned) < 3:
        return {
            "status": "NON_CLINICAL",
            "clinical_relevance": "NONE",
            "reason": "No clinical signs, symptoms, examination findings, or relevant patient observations were detected.",
            "suggested_action": "Please enter clinical information before running diagnostic prioritization.",
            "is_valid": False
        }

    # Extract words
    words = set(re.findall(r'\b[a-z0-9]+\b', lower_text))

    # Check for gibberish (e.g. repeated non-vowel patterns or keyboard mashes)
    if len(cleaned) > 5 and not any(c in "aeiouy" for c in lower_text):
        return {
            "status": "NON_CLINICAL",
            "clinical_relevance": "NONE",
            "reason": "Input appears to contain random character combinations without recognized clinical terminology.",
            "suggested_action": "Please enter valid medical terms or patient observations.",
            "is_valid": False
        }

    matched_clinical_words = words.intersection(CLINICAL_KEYWORDS)

    # Detect informal clinical shorthand (e.g. "pt has dev delay", "2 yrs")
    has_shorthand = any(w in {"pt", "dev", "yrs", "yo", "hx", "dx", "sx", "w/"} for w in words)

    if matched_clinical_words:
        if has_shorthand or len(words) > 8:
            return {
                "status": "NEEDS_ENHANCEMENT",
                "clinical_relevance": "HIGH" if len(matched_clinical_words) >= 2 else "MODERATE",
                "reason": "Clinical information is relevant but can be expressed more clearly using standard medical phrasing.",
                "suggested_action": "Enhance with AI or proceed directly to diagnosis.",
                "is_valid": True
            }
        else:
            return {
                "status": "VALID_CLINICAL",
                "clinical_relevance": "HIGH" if len(matched_clinical_words) >= 2 else "MODERATE",
                "reason": "Valid clinical information detected.",
                "suggested_action": "Ready for analysis.",
                "is_valid": True
            }

    # Fallback heuristic: If word count >= 4 and contains medical-like structure (e.g., patient narrative), allow as VALID_CLINICAL or NEEDS_ENHANCEMENT
    if len(words) >= 4:
        return {
            "status": "VALID_CLINICAL",
            "clinical_relevance": "MODERATE",
            "reason": "Clinical narrative detected.",
            "suggested_action": "Ready for analysis.",
            "is_valid": True
        }

    return {
        "status": "NON_CLINICAL",
        "clinical_relevance": "LOW",
        "reason": "The input does not contain recognized symptoms, medical terms, or clinical observations.",
        "suggested_action": "Please enter patient symptoms, physical exam findings, or medical history.",
        "is_valid": False
    }
