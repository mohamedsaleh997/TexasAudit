from http.client import HTTPResponse
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageStat

from app.models.page_evidence import CrawlResult, ImageEvidence, LinkEvidence, PageEvidence
from app.models.test_result import CheckResult, CheckStatus, CheckType


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BAD_HTTP_STATUS = 400
REQUEST_TIMEOUT_SECONDS = 8
MAX_LINKS_TO_CHECK = 80


class WebsiteHealthAuditor:
    def audit(self, crawl_result: CrawlResult) -> list[CheckResult]:
        results: list[CheckResult] = []

        results.extend(self._audit_crawl_errors(crawl_result))

        for page in crawl_result.pages:
            results.extend(self._audit_page_basics(page))
            results.extend(self._audit_images(page))
            results.extend(self._audit_banners(page))

        results.extend(self._audit_links(crawl_result))
        return results

    def _audit_crawl_errors(self, crawl_result: CrawlResult) -> list[CheckResult]:
        if not crawl_result.errors:
            return [
                CheckResult(
                    test_type=CheckType.FUNCTIONAL,
                    name="Website crawl completed",
                    status=CheckStatus.PASSED,
                    details=f"Crawled {len(crawl_result.pages)} page(s) without crawler errors.",
                )
            ]

        return [
            CheckResult(
                test_type=CheckType.FUNCTIONAL,
                name="Website crawl completed",
                status=CheckStatus.FAILED,
                details=error,
            )
            for error in crawl_result.errors
        ]

    def _audit_page_basics(self, page: PageEvidence) -> list[CheckResult]:
        results = [
            CheckResult(
                test_type=CheckType.CONTENT,
                name="Page title exists",
                status=CheckStatus.PASSED if page.title else CheckStatus.FAILED,
                details=f"{page.url}: {page.title or 'Missing page title'}",
            ),
            CheckResult(
                test_type=CheckType.CONTENT,
                name="Page has headings",
                status=CheckStatus.PASSED if page.headings else CheckStatus.WARNING,
                details=f"{page.url}: found {len(page.headings)} heading(s).",
            ),
            CheckResult(
                test_type=CheckType.CONTENT,
                name="Page has visible text",
                status=CheckStatus.PASSED if len(page.text_preview) >= 80 else CheckStatus.WARNING,
                details=f"{page.url}: collected {len(page.text_preview)} text character(s).",
            ),
        ]
        return results

    def _audit_images(self, page: PageEvidence) -> list[CheckResult]:
        if not page.images:
            return [
                CheckResult(
                    test_type=CheckType.UI,
                    name="Page images loaded",
                    status=CheckStatus.WARNING,
                    details=f"{page.url}: no image elements were found.",
                )
            ]

        results: list[CheckResult] = []
        broken_images = [image for image in page.images if self._is_broken_image(image)]

        if broken_images:
            for image in broken_images:
                results.append(
                    CheckResult(
                        test_type=CheckType.UI,
                        name="Broken image detected",
                        status=CheckStatus.FAILED,
                        details=(
                            f"{page.url}: image failed to load. "
                            f"src={image.src or 'missing'}, "
                            f"natural={image.natural_width}x{image.natural_height}"
                        ),
                    )
                )
            return results

        return [
            CheckResult(
                test_type=CheckType.UI,
                name="Page images loaded",
                status=CheckStatus.PASSED,
                details=f"{page.url}: {len(page.images)} image(s) loaded.",
            )
        ]

    def _audit_banners(self, page: PageEvidence) -> list[CheckResult]:
        if not page.banners:
            return [
                CheckResult(
                    test_type=CheckType.UI,
                    name="Banner screenshots captured",
                    status=CheckStatus.WARNING,
                    details=f"{page.url}: no banner screenshots were captured.",
                )
            ]

        results: list[CheckResult] = []
        for banner in page.banners:
            screenshot_path = PROJECT_ROOT / banner.screenshot_path

            if not screenshot_path.exists():
                results.append(
                    CheckResult(
                        test_type=CheckType.UI,
                        name="Banner screenshot exists",
                        status=CheckStatus.FAILED,
                        details=f"{page.url}: missing banner screenshot {banner.screenshot_path}.",
                    )
                )
                continue

            if self._is_blank_image(screenshot_path):
                results.append(
                    CheckResult(
                        test_type=CheckType.UI,
                        name="Blank banner screenshot detected",
                        status=CheckStatus.FAILED,
                        details=f"{page.url}: banner screenshot appears blank: {banner.screenshot_path}.",
                    )
                )

        if results:
            return results

        return [
            CheckResult(
                test_type=CheckType.UI,
                name="Banner screenshots valid",
                status=CheckStatus.PASSED,
                details=f"{page.url}: {len(page.banners)} banner screenshot(s) captured.",
            )
        ]

    def _audit_links(self, crawl_result: CrawlResult) -> list[CheckResult]:
        unique_links = self._unique_links(crawl_result.pages)
        if not unique_links:
            return [
                CheckResult(
                    test_type=CheckType.FUNCTIONAL,
                    name="Links are available",
                    status=CheckStatus.WARNING,
                    details="No links were collected from crawled pages.",
                )
            ]

        results: list[CheckResult] = []
        checked_count = 0

        for link in unique_links[:MAX_LINKS_TO_CHECK]:
            checked_count += 1
            status_code, error = self._check_url(link.url)
            if error or status_code >= BAD_HTTP_STATUS:
                results.append(
                    CheckResult(
                        test_type=CheckType.FUNCTIONAL,
                        name="Broken link detected",
                        status=CheckStatus.FAILED,
                        details=(
                            f"{link.url} returned {status_code or 'no status'}"
                            f"{f' ({error})' if error else ''}."
                        ),
                    )
                )

        if results:
            return results

        return [
            CheckResult(
                test_type=CheckType.FUNCTIONAL,
                name="Links are reachable",
                status=CheckStatus.PASSED,
                details=f"Checked {checked_count} unique link(s); no broken links found.",
            )
        ]

    def _is_broken_image(self, image: ImageEvidence) -> bool:
        if not image.src:
            return True

        if image.src.startswith("data:"):
            return False

        return not image.is_loaded or not image.natural_width or not image.natural_height

    def _is_blank_image(self, image_path: Path) -> bool:
        try:
            with Image.open(image_path) as image:
                grayscale_image = image.convert("L")
                stat = ImageStat.Stat(grayscale_image)
                return bool(stat.stddev and stat.stddev[0] < 2)
        except Exception:
            return True

    def _unique_links(self, pages: list[PageEvidence]) -> list[LinkEvidence]:
        links: list[LinkEvidence] = []
        seen_urls: set[str] = set()

        for page in pages:
            for link in page.links:
                parsed_url = urlparse(link.url)
                if parsed_url.scheme not in {"http", "https"} or link.url in seen_urls:
                    continue

                seen_urls.add(link.url)
                links.append(link)

        return links

    def _check_url(self, url: str) -> tuple[int, str]:
        request = Request(url, method="HEAD", headers={"User-Agent": "TexasAudit/0.1"})

        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return self._status_code(response), ""
        except HTTPError as error:
            if error.code == 405:
                return self._check_url_with_get(url)
            return error.code, str(error.reason)
        except URLError as error:
            return 0, str(error.reason)
        except Exception as error:
            return 0, str(error)

    def _check_url_with_get(self, url: str) -> tuple[int, str]:
        request = Request(url, method="GET", headers={"User-Agent": "TexasAudit/0.1"})

        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return self._status_code(response), ""
        except HTTPError as error:
            return error.code, str(error.reason)
        except URLError as error:
            return 0, str(error.reason)
        except Exception as error:
            return 0, str(error)

    def _status_code(self, response: HTTPResponse) -> int:
        return int(response.status)

