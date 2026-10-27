"""Hermetic test environment credential-name coverage."""

from tests.conftest import _looks_like_credential


def test_secret_key_and_openapi_key_env_names_are_treated_as_credentials():
    assert _looks_like_credential("ALIYUN_SECRET_KEY") is True
    assert _looks_like_credential("FOTOR_OPENAPI_KEY") is True
