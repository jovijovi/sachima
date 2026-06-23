"""Tests for display-oriented gateway progress redaction."""

import pytest

from gateway.progress.redaction import sanitize_for_progress


class BadRepr:
    def __repr__(self):  # pragma: no cover - test expects sanitizer to survive this
        raise RuntimeError("repr should not escape sanitizer")


def test_sanitize_for_progress_redacts_sensitive_mapping_values():
    data = {
        "api_key": "sk-live-abc123",
        "ACCESS-TOKEN": "tok-secret-456",
        "nested": {
            "password": "hunter2",
            "passwd": "letmein",
            "Authorization": "Bearer auth-secret-789",
            "bearer_token": "bearer-token-value",
            "webhook_url": "https://hooks.example.invalid/very-secret-hook",
            "safe": "visible value",
        },
    }

    rendered = sanitize_for_progress(data)

    assert isinstance(rendered, str)
    assert "visible value" in rendered
    for secret in (
        "sk-live-abc123",
        "tok-secret-456",
        "hunter2",
        "letmein",
        "auth-secret-789",
        "bearer-token-value",
        "very-secret-hook",
    ):
        assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_sanitize_for_progress_redacts_sensitive_url_query_values():
    data = {
        "callback": "https://example.invalid/cb?token=url-token&key=url-key&signature=url-sig&ok=yes",
        "next": "https://example.invalid/path?password=url-password&secret=url-secret&name=public",
    }

    rendered = sanitize_for_progress(data)

    assert "ok=yes" in rendered
    assert "name=public" in rendered
    for secret in ("url-token", "url-key", "url-sig", "url-password", "url-secret"):
        assert secret not in rendered
    assert rendered.count("[REDACTED]") >= 5


def test_sanitize_for_progress_handles_plain_strings_and_bearer_tokens():
    rendered = sanitize_for_progress(
        "curl -H 'Authorization: Bearer plain-secret-token' "
        "https://example.invalid/?token=query-secret&debug=true"
    )

    assert "plain-secret-token" not in rendered
    assert "query-secret" not in rendered
    assert "debug=true" in rendered


def test_sanitize_for_progress_redacts_colon_header_and_plain_key_value_forms():
    rendered = sanitize_for_progress(
        "Authorization: Basic basic-secret-123\n"
        "Authorization: Token token-secret-321\n"
        "Authorization: ApiKey apikey-secret-654\n"
        "X-API-Key: 'header-secret-456'\n"
        "api_key: \"colon-secret-789\"\n"
        "password: 'colon-password-000'\n"
        "safe: public-value"
    )

    assert "public-value" in rendered
    for secret in (
        "basic-secret-123",
        "token-secret-321",
        "apikey-secret-654",
        "header-secret-456",
        "colon-secret-789",
        "colon-password-000",
    ):
        assert secret not in rendered
    assert rendered.count("[REDACTED]") >= 6


def test_sanitize_for_progress_redacts_quoted_authorization_header_value():
    rendered = sanitize_for_progress('Authorization: "Token quoted-token-secret" safe=visible')

    assert "quoted-token-secret" not in rendered
    assert "safe=visible" in rendered
    assert "[REDACTED]" in rendered


def test_sanitize_for_progress_redacts_prefixed_assignment_and_query_keys():
    rendered = sanitize_for_progress(
        "OPENAI_API_KEY=openai-secret GITHUB_TOKEN=github-secret "
        "AWS_SECRET_ACCESS_KEY=aws-secret PRIVATE_KEY=private-secret "
        "https://example.invalid/cb?access_token=url-token&client_secret=url-secret&ok=yes"
    )

    assert "ok=yes" in rendered
    for secret in (
        "openai-secret",
        "github-secret",
        "aws-secret",
        "private-secret",
        "url-token",
        "url-secret",
    ):
        assert secret not in rendered
    assert rendered.count("[REDACTED]") >= 6


def test_sanitize_for_progress_redacts_json_style_sensitive_keys_and_quoted_assignments():
    rendered = sanitize_for_progress(
        '{"api_key": "json-secret", "token":"json-token", "safe": "visible"} '
        'OPENAI_API_KEY="secret with spaces" PRIVATE_KEY="pem line one line two"'
    )

    assert "visible" in rendered
    for secret in (
        "json-secret",
        "json-token",
        "secret with spaces",
        "pem line one line two",
    ):
        assert secret not in rendered
    assert rendered.count("[REDACTED]") >= 4


def test_sanitize_for_progress_redacts_bare_provider_key_shapes():
    bare_openai_key = "sk-" + "test-" + ("a" * 32)
    project_key = "sk-" + "proj-" + ("b" * 32)
    github_pat = "ghp_" + ("C" * 36)
    google_key = "AIza" + ("D" * 35)
    safe_route = "/health"
    safe_path = "/home/ecs-user/.hermes/config.yaml"

    rendered = sanitize_for_progress(
        f"implement {safe_route} using {bare_openai_key}; "
        f"project={project_key}; pat {github_pat}; google {google_key}; "
        f"read {safe_path}"
    )

    assert safe_route in rendered
    assert safe_path in rendered
    for secret in (bare_openai_key, project_key, github_pat, google_key):
        assert secret not in rendered
    assert rendered.count("[REDACTED]") >= 4



def test_sanitize_for_progress_never_raises_and_respects_max_len():
    data = {
        "bad": BadRepr(),
        "safe": "x" * 200,
        "token": "must-not-leak-even-when-truncated",
    }

    rendered = sanitize_for_progress(data, max_len=80)

    assert isinstance(rendered, str)
    assert len(rendered) <= 80
    assert "must-not-leak-even-when-truncated" not in rendered


@pytest.mark.parametrize("max_len", [0, -1])
def test_sanitize_for_progress_non_positive_max_len_returns_empty_string(max_len):
    assert sanitize_for_progress({"safe": "visible"}, max_len=max_len) == ""
