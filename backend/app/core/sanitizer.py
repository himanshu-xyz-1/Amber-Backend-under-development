import math
import re
from typing import Any


def calculate_shannon_entropy(text: str) -> float:
    """Calculates Shannon entropy of a string to detect high-entropy secrets."""
    if not text:
        return 0.0
    probabilities = [text.count(c) / len(text) for c in set(text)]
    return -sum(p * math.log2(p) for p in probabilities)


# Common sensitive patterns
SECRET_PATTERNS = [
    # AWS Access Key & Secret
    (re.compile(r'(AKIA|ASIA)[0-9A-Z]{16}', re.IGNORECASE), '[REDACTED_AWS_KEY]'),
    # GitHub Personal Access Tokens
    (re.compile(r'(ghp|gho|ghu|ghs|ghr)_[0-9a-zA-Z]{36}', re.IGNORECASE), '[REDACTED_GITHUB_TOKEN]'),
    # Generic Bearer Tokens and JWTs
    (re.compile(r'Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*', re.IGNORECASE), 'Bearer [REDACTED_TOKEN]'),
    (re.compile(r'eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*'), '[REDACTED_JWT]'),
    # Private Keys
    (re.compile(r'-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----'), '[REDACTED_PRIVATE_KEY]'),
    # Database Connection Strings
    (re.compile(r'(postgres|postgresql|mysql|redis|mongodb)://[^:]+:([^@]+)@', re.IGNORECASE), r'\1://[USER]:[REDACTED_PASSWORD]@'),
    # Key-value secret assignments
    (re.compile(r'(?i)(password|passwd|secret|token|apikey|api_key|auth|authorization)\s*[:=]\s*["\']?([^"\'\s,;]+)["\']?'), r'\1: "[REDACTED_SECRET]"'),
]


def redact_string(text: str) -> str:
    """Synchronously scrubs secrets, tokens, and credentials from a text string."""
    if not text or not isinstance(text, str):
        return text

    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    # Check for uncaptured high-entropy words (>4.8 entropy, length > 24)
    words = sanitized.split()
    redacted_words = []
    for word in words:
        clean_w = re.sub(r'[^a-zA-Z0-9]', '', word)
        if len(clean_w) >= 28 and calculate_shannon_entropy(clean_w) > 4.8:
            redacted_words.append('[REDACTED_ENTROPY_TOKEN]')
        else:
            redacted_words.append(word)

    return " ".join(redacted_words)


def sanitize_payload(obj: dict | list | str | Any) -> Any:
    """Recursively walks arbitrary nested JSON payloads to scrub sensitive strings and keys."""
    if isinstance(obj, str):
        return redact_string(obj)
    elif isinstance(obj, dict):
        sanitized_dict = {}
        for k, v in obj.items():
            # If key itself is sensitive, mask the value
            if re.search(r'(?i)(password|secret|token|private_key|api_key)', str(k)):
                sanitized_dict[k] = "[REDACTED_SECRET]"
            else:
                sanitized_dict[k] = sanitize_payload(v)
        return sanitized_dict
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    return obj
