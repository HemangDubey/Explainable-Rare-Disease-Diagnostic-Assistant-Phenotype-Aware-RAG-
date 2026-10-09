"""Password hashing, credential validation and session-token primitives.

* Passwords: argon2id (argon2-cffi defaults), salted per hash, never stored or logged in plaintext.
* Session tokens: 256-bit random bearer tokens; only their SHA-256 is stored (a database leak does not yield usable tokens).
* No signing secret exists, so nothing secret has to be shipped to the frontend.
"""
import hashlib
import os
import re
import secrets
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()
DUMMY_HASH = _ph.hash(secrets.token_hex(16))      # verified against when the account does not exist (uniform timing)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
COMMON_PASSWORDS = {"password1234", "passwordpassword", "123456789012", "qwertyuiop12", "letmein12345", "welcome12345", "administrator", "iloveyou1234"}
MIN_PASSWORD, MAX_PASSWORD = 12, 128


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return False


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str):
    return [] if len(email) <= 254 and EMAIL_RE.match(email) else ["Enter a valid email address."]


def validate_password(password: str, email: str = ""):
    problems = []
    if len(password) < MIN_PASSWORD:
        problems.append(f"Use at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        problems.append(f"Use at most {MAX_PASSWORD} characters.")
    if password.lower() in COMMON_PASSWORDS or len(set(password)) < 5:
        problems.append("That password is too easy to guess.")
    local = email.split("@")[0]
    if local and len(local) >= 4 and local in password.lower():
        problems.append("The password must not contain your email name.")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def new_id() -> str:
    return uuid.uuid4().hex


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default
