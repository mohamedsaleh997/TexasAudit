from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urlparse

from playwright.sync_api import Browser, Locator, Page, sync_playwright

from app.models.page_evidence import (
    BannerEvidence,
    CrawlResult,
    ImageEvidence,
    LinkEvidence,
    PageEvidence,
)
from app.models.website import WebsiteConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS_DIR = PROJECT_ROOT / "reports" / "screenshots"


class SiteCrawler:
    def crawl(self, website: WebsiteConfig, headless: bool = True) -> CrawlResult:
        start_url = str(website.base_url)
        start_domain = urlparse(start_url).netloc.lower()
        queued_urls: deque[str] = deque([start_url])
        visited_urls: set[str] = set()
        skipped_urls: list[str] = []
        errors: list[str] = []
        pages: list[PageEvidence] = []

        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})

            while queued_urls and len(pages) < website.max_pages:
                current_url = queued_urls.popleft()
                normalized_url = self._normalize_url(current_url)

                if normalized_url in visited_urls:
                    continue

                if not self._is_internal_url(normalized_url, start_domain):
                    skipped_urls.append(normalized_url)
                    continue

                visited_urls.add(normalized_url)

                try:
                    page.goto(normalized_url, wait_until="domcontentloaded", timeout=30_000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10_000)
                    except Exception:
                        pass

                    evidence = self._collect_page_evidence(page, len(pages) + 1)
                    pages.append(evidence)

                    for link in evidence.links:
                        normalized_link = self._normalize_url(link.url)
                        if (
                            normalized_link not in visited_urls
                            and self._is_internal_url(normalized_link, start_domain)
                            and len(queued_urls) + len(pages) < website.max_pages * 3
                        ):
                            queued_urls.append(normalized_link)
                except Exception as error:
                    errors.append(f"{normalized_url}: {error}")

            self._close_browser(browser)

        return CrawlResult(
            start_url=start_url,
            pages=pages,
            skipped_urls=skipped_urls,
            errors=errors,
        )

    def _collect_page_evidence(self, page: Page, page_number: int) -> PageEvidence:
        screenshot_path = SCREENSHOTS_DIR / f"page-{page_number}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)

        return PageEvidence(
            url=page.url,
            title=page.title().strip(),
            headings=self._collect_texts(page, "h1, h2, h3"),
            buttons=self._collect_texts(page, "button, [role='button'], input[type='button'], input[type='submit']"),
            links=self._collect_links(page),
            images=self._collect_images(page),
            banners=self._collect_banners(page, page_number),
            text_preview=self._collect_text_preview(page),
            screenshot_path=str(screenshot_path.relative_to(PROJECT_ROOT)),
        )

    def _collect_texts(self, page: Page, selector: str, limit: int = 40) -> list[str]:
        values = page.locator(selector).evaluate_all(
            """elements => elements
                .map(element => (element.innerText || element.value || '').trim())
                .filter(Boolean)
            """
        )
        return list(dict.fromkeys(values))[:limit]

    def _collect_links(self, page: Page, limit: int = 120) -> list[LinkEvidence]:
        raw_links = page.locator("a[href]").evaluate_all(
            """elements => elements.map(element => ({
                text: (element.innerText || element.getAttribute('aria-label') || '').trim(),
                href: element.href
            }))"""
        )
        links: list[LinkEvidence] = []
        seen_urls: set[str] = set()

        for raw_link in raw_links:
            url = self._normalize_url(raw_link["href"])
            if not url or url in seen_urls:
                continue

            seen_urls.add(url)
            links.append(LinkEvidence(text=raw_link["text"], url=url))

            if len(links) >= limit:
                break

        return links

    def _collect_images(self, page: Page, limit: int = 80) -> list[ImageEvidence]:
        raw_images = page.locator("img").evaluate_all(
            """elements => elements.map(element => {
                const rect = element.getBoundingClientRect();
                return {
                    alt: element.getAttribute('alt') || '',
                    src: element.currentSrc || element.src || '',
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    top: Math.round(rect.top),
                    naturalWidth: element.naturalWidth || 0,
                    naturalHeight: element.naturalHeight || 0,
                    complete: Boolean(element.complete)
                };
            })"""
        )

        images: list[ImageEvidence] = []
        for raw_image in raw_images:
            width = raw_image["width"]
            height = raw_image["height"]
            top = raw_image["top"]
            images.append(
                ImageEvidence(
                    alt=raw_image["alt"],
                    src=raw_image["src"],
                    width=width,
                    height=height,
                    natural_width=raw_image["naturalWidth"],
                    natural_height=raw_image["naturalHeight"],
                    is_loaded=raw_image["complete"] and raw_image["naturalWidth"] > 0,
                    is_banner_candidate=width >= 600 and height >= 180 and top <= 2400,
                )
            )

            if len(images) >= limit:
                break

        return images

    def _collect_banners(self, page: Page, page_number: int, limit: int = 8) -> list[BannerEvidence]:
        banner_candidates = page.locator(
            "img, picture, [class*='banner' i], [class*='hero' i], "
            "[class*='carousel' i], [class*='swiper-slide' i], section"
        )
        banners: list[BannerEvidence] = []

        for index in range(banner_candidates.count()):
            if len(banners) >= limit:
                break

            locator = banner_candidates.nth(index)
            banner = self._capture_banner_candidate(locator, page_number, len(banners) + 1)
            if banner is not None:
                banners.append(banner)

        return banners

    def _capture_banner_candidate(
        self,
        locator: Locator,
        page_number: int,
        banner_number: int,
    ) -> BannerEvidence | None:
        try:
            if not locator.is_visible(timeout=1_000):
                return None

            box = locator.bounding_box(timeout=1_000)
            if box is None:
                return None

            width = round(box["width"])
            height = round(box["height"])
            top = round(box["y"])

            if width < 600 or height < 160 or top > 2600:
                return None

            screenshot_path = SCREENSHOTS_DIR / f"page-{page_number}-banner-{banner_number}.png"
            locator.screenshot(path=str(screenshot_path), timeout=5_000)

            return BannerEvidence(
                screenshot_path=str(screenshot_path.relative_to(PROJECT_ROOT)),
                selector=self._best_effort_selector(locator),
                text=self._safe_inner_text(locator),
                image_src=self._safe_image_src(locator),
                width=width,
                height=height,
            )
        except Exception:
            return None

    def _best_effort_selector(self, locator: Locator) -> str:
        return locator.evaluate(
            """element => {
                const tag = element.tagName.toLowerCase();
                const id = element.id ? `#${element.id}` : '';
                const classes = Array.from(element.classList || []).slice(0, 3).map(value => `.${value}`).join('');
                return `${tag}${id}${classes}`;
            }"""
        )

    def _safe_inner_text(self, locator: Locator, limit: int = 500) -> str:
        try:
            return " ".join(locator.inner_text(timeout=1_000).split())[:limit]
        except Exception:
            return ""

    def _safe_image_src(self, locator: Locator) -> str:
        try:
            return locator.evaluate(
                """element => {
                    if (element.tagName.toLowerCase() === 'img') {
                        return element.currentSrc || element.src || '';
                    }
                    const image = element.querySelector('img');
                    return image ? (image.currentSrc || image.src || '') : '';
                }"""
            )
        except Exception:
            return ""

    def _collect_text_preview(self, page: Page, limit: int = 1200) -> str:
        try:
            body_text = page.locator("body").inner_text(timeout=5_000).strip()
        except Exception:
            return ""

        return " ".join(body_text.split())[:limit]

    def _normalize_url(self, url: str) -> str:
        normalized_url, _fragment = urldefrag(url)
        parsed_url = urlparse(normalized_url)

        if parsed_url.scheme not in {"http", "https"}:
            return ""

        return parsed_url._replace(query="").geturl().rstrip("/")

    def _is_internal_url(self, url: str, start_domain: str) -> bool:
        if not url:
            return False

        domain = urlparse(url).netloc.lower()
        return domain == start_domain

    def _close_browser(self, browser: Browser) -> None:
        browser.close()
