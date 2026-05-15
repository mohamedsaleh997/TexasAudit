from pathlib import Path

import yaml

from app.models.website import WebsiteConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEBSITES_PATH = PROJECT_ROOT / "config" / "websites.yaml"


class WebsiteRegistry:
    def __init__(self, config_path: Path = DEFAULT_WEBSITES_PATH) -> None:
        self.config_path = config_path

    def list_websites(self) -> list[WebsiteConfig]:
        if not self.config_path.exists():
            return []

        with self.config_path.open("r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file) or {}

        return [WebsiteConfig(**website) for website in data.get("websites", [])]

