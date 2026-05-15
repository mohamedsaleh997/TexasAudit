from pydantic import BaseModel, HttpUrl


class WebsiteConfig(BaseModel):
    name: str
    country: str
    base_url: HttpUrl
    max_pages: int = 12

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.country})"

