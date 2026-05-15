from typing import Protocol

from app.models.ai_settings import AiSettings


class AiClient(Protocol):
    def review_text(self, prompt: str) -> str:
        raise NotImplementedError


class AiClientFactory:
    def create(self, settings: AiSettings) -> AiClient:
        raise NotImplementedError(
            f"{settings.provider.value} is configured, but AI review clients are not implemented yet."
        )

