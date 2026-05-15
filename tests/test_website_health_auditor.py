from pathlib import Path

from PIL import Image

from app.models.page_evidence import (
    CrawlResult,
    ImageEvidence,
    PageEvidence,
)
from app.models.test_result import CheckStatus
from app.services.website_health_auditor import WebsiteHealthAuditor


def test_health_auditor_flags_broken_images() -> None:
    page = PageEvidence(
        url="https://example.com",
        title="Example",
        headings=["Home"],
        buttons=[],
        links=[],
        images=[
            ImageEvidence(
                alt="Broken",
                src="https://example.com/broken.png",
                natural_width=0,
                natural_height=0,
                is_loaded=False,
            )
        ],
        banners=[],
        text_preview="This is enough visible text for a basic content check.",
    )
    crawl_result = CrawlResult(
        start_url="https://example.com",
        pages=[page],
        skipped_urls=[],
        errors=[],
    )

    results = WebsiteHealthAuditor().audit(crawl_result)

    assert any(result.name == "Broken image detected" for result in results)
    assert any(result.status == CheckStatus.FAILED for result in results)


def test_health_auditor_detects_blank_banner_screenshot(tmp_path: Path) -> None:
    blank_image = tmp_path / "blank.png"
    Image.new("RGB", (100, 100), "white").save(blank_image)

    auditor = WebsiteHealthAuditor()

    assert auditor._is_blank_image(blank_image)


def test_health_auditor_accepts_valid_banner_screenshot(tmp_path: Path) -> None:
    image_path = tmp_path / "valid.png"
    image = Image.new("RGB", (100, 100), "white")
    image.putpixel((50, 50), (0, 0, 0))
    image.save(image_path)

    auditor = WebsiteHealthAuditor()

    assert not auditor._is_blank_image(image_path)
