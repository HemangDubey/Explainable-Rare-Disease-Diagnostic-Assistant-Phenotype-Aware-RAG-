import re
from typing import Tuple

# Configurable list of offensive / inappropriate terms and patterns
INAPPROPRIATE_TERMS = {
    "fuck", "shit", "bitch", "bastard", "asshole", "cunt", "dick", "pussy",
    "whore", "slut", "nigger", "faggot", "motherfucker", "cock", "prick"
}

SPAM_PATTERNS = [
    r"buy\s+now", r"click\s+here", r"discount", r"casino", r"crypto", r"viagra",
    r"http[s]?://", r"www\.", r"\.com", r"free\s+money"
]

def check_content_safety(text: str) -> Tuple[bool, str]:
    """
    Checks text for profane, abusive, or spam content.
    Returns (is_safe, reason).
    """
    if not text:
        return True, ""

    normalized_text = text.lower()
    # Extract words
    words = set(re.findall(r'\b[a-z]+\b', normalized_text))

    # Check profane terms
    if words.intersection(INAPPROPRIATE_TERMS):
        return False, "Please enter relevant clinical information to continue."

    # Check spam patterns
    for pat in SPAM_PATTERNS:
        if re.search(pat, normalized_text):
            return False, "Please enter relevant clinical information to continue."

    return True, ""
