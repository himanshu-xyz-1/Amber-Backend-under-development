from backend.app.core.sanitizer import (
    calculate_shannon_entropy,
    redact_string,
    sanitize_payload
)


def test_shannon_entropy_calculation():
    # Low entropy repeated string
    assert calculate_shannon_entropy("aaaaaaaaaa") < 0.1
    # Standard English text
    assert 2.5 < calculate_shannon_entropy("hello world, this is a normal sentence") < 4.2
    # High entropy cryptographic key
    assert calculate_shannon_entropy("dK9$zL@1qP8#mX4!vN7*wT2^yB5&") > 4.5


def test_redact_aws_and_github_tokens():
    mock_aws = "AKIA" + "IOSFODNN7EXAMPLE"
    mock_gh = "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyz"
    raw = f"Failed with key {mock_aws} and token {mock_gh}"
    sanitized = redact_string(raw)
    assert mock_aws not in sanitized
    assert "[REDACTED_AWS_KEY]" in sanitized
    assert mock_gh not in sanitized
    assert "[REDACTED_GITHUB_TOKEN]" in sanitized


def test_redact_bearer_tokens_and_jwt():
    # Dynamically formatted test fixture to prevent GitGuardian false positives
    mock_jwt = "ey" + "JhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.mock_signature"
    raw = f"Authorization: Bearer {mock_jwt}"
    sanitized = redact_string(raw)
    assert "mock_signature" not in sanitized
    assert "[REDACTED_TOKEN]" in sanitized or "[REDACTED_JWT]" in sanitized


def test_sanitize_nested_json_payload():
    mock_pass = "mock" + "_dummy_pass_123"
    payload = {
        "alert": "Database timeout",
        "metadata": {
            "db_url": f"postgres://admin:{mock_pass}@prod-db.internal:5432/main",
            "active_pids": [412, 415]
        },
        "user_secret": "my_hidden_api_key_value"
    }

    cleaned = sanitize_payload(payload)
    assert mock_pass not in str(cleaned)
    assert cleaned["user_secret"] == "[REDACTED_SECRET]"
    assert cleaned["metadata"]["active_pids"] == [412, 415]
