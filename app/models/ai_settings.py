from enum import Enum

from pydantic import BaseModel, Field, model_validator


class AiProvider(str, Enum):
    OPENAI = "OpenAI"
    ANTHROPIC = "Anthropic / Claude"
    GOOGLE = "Google Gemini"
    AZURE_OPENAI = "Azure OpenAI"
    CUSTOM = "Custom API"


DEFAULT_MODELS = {
    AiProvider.OPENAI: "gpt-5.4-mini",
    AiProvider.ANTHROPIC: "claude-sonnet-4-5",
    AiProvider.GOOGLE: "gemini-2.5-pro",
    AiProvider.AZURE_OPENAI: "company-deployment-name",
    AiProvider.CUSTOM: "custom-model-name",
}


class AiSettings(BaseModel):
    enabled: bool = False
    provider: AiProvider = AiProvider.OPENAI
    model_name: str = ""
    api_key: str = Field(default="", repr=False)
    base_url: str = ""

    @model_validator(mode="after")
    def validate_enabled_settings(self) -> "AiSettings":
        if not self.enabled:
            return self

        if not self.api_key.strip():
            raise ValueError("Enter your AI provider API key.")

        if not self.model_name.strip():
            raise ValueError("Enter the AI model name.")

        if self.provider == AiProvider.CUSTOM and not self.base_url.strip():
            raise ValueError("Enter the custom provider base URL.")

        return self

    def masked_key(self) -> str:
        if not self.api_key:
            return "Not provided"

        return f"{self.api_key[:4]}...{self.api_key[-4:]}" if len(self.api_key) >= 8 else "Provided"

