import pytest
from pydantic import ValidationError

from app.models.ai_settings import AiProvider, AiSettings
from app.models.test_result import CheckRequest, CheckType
from app.services.website_registry import WebsiteRegistry


def test_test_request_accepts_valid_url() -> None:
    request = CheckRequest(url="https://example.com", test_types=[CheckType.UI])

    assert str(request.url) == "https://example.com/"
    assert request.test_types == [CheckType.UI]


def test_test_request_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        CheckRequest(url="not-a-url", test_types=[CheckType.UI])


def test_ai_settings_requires_key_when_enabled() -> None:
    with pytest.raises(ValidationError):
        AiSettings(
            enabled=True,
            provider=AiProvider.OPENAI,
            model_name="gpt-5.4-mini",
            api_key="",
        )


def test_ai_settings_accepts_provider_model_and_key() -> None:
    settings = AiSettings(
        enabled=True,
        provider=AiProvider.ANTHROPIC,
        model_name="claude-sonnet-4-5",
        api_key="test-api-key",
    )

    assert settings.provider == AiProvider.ANTHROPIC
    assert settings.model_name == "claude-sonnet-4-5"


def test_website_registry_loads_iraq_site() -> None:
    websites = WebsiteRegistry().list_websites()

    assert websites
    assert websites[0].country == "Iraq"
    assert str(websites[0].base_url) == "https://iraq.texaschicken.com/"
