from pydantic import BaseModel


class LinkEvidence(BaseModel):
    text: str
    url: str


class ImageEvidence(BaseModel):
    alt: str
    src: str
    width: int | None = None
    height: int | None = None
    natural_width: int | None = None
    natural_height: int | None = None
    is_loaded: bool = True
    is_banner_candidate: bool = False


class BannerEvidence(BaseModel):
    screenshot_path: str
    selector: str
    text: str
    image_src: str
    width: int
    height: int


class PageEvidence(BaseModel):
    url: str
    title: str
    headings: list[str]
    buttons: list[str]
    links: list[LinkEvidence]
    images: list[ImageEvidence]
    banners: list[BannerEvidence]
    text_preview: str
    screenshot_path: str | None = None


class CrawlResult(BaseModel):
    start_url: str
    pages: list[PageEvidence]
    skipped_urls: list[str]
    errors: list[str]
