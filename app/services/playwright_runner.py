from collections.abc import Callable

from playwright.sync_api import Page, sync_playwright

from app.models.test_result import CheckRequest, CheckResult, CheckStatus, CheckType


class PlaywrightRunner:
    def run(self, request: CheckRequest) -> list[CheckResult]:
        results: list[CheckResult] = []

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=request.headless)
            page = browser.new_page()

            try:
                page.goto(str(request.url), wait_until="domcontentloaded", timeout=30_000)

                checks: dict[CheckType, Callable[[Page], list[CheckResult]]] = {
                    CheckType.UI: self._run_ui_checks,
                    CheckType.CONTENT: self._run_content_checks,
                    CheckType.FUNCTIONAL: self._run_functional_checks,
                }

                for test_type in request.test_types:
                    results.extend(checks[test_type](page))
            except Exception as error:
                results.append(
                    CheckResult(
                        test_type=CheckType.FUNCTIONAL,
                        name="Open target URL",
                        status=CheckStatus.FAILED,
                        details=f"Could not open {request.url}: {error}",
                    )
                )
            finally:
                browser.close()

        return results

    def _run_ui_checks(self, page: Page) -> list[CheckResult]:
        return [
            self._check_count(page, "Page has at least one heading", "h1, h2, h3", CheckType.UI),
            self._check_count(page, "Page has navigation links", "a[href]", CheckType.UI),
            self._check_count(
                page,
                "Page has visible interactive controls",
                "button, input, select, textarea",
                CheckType.UI,
            ),
            self._check_images_have_alt_text(page),
        ]

    def _run_content_checks(self, page: Page) -> list[CheckResult]:
        title = page.title().strip()
        body_text = page.locator("body").inner_text(timeout=5_000).strip()
        meta_description = page.locator("meta[name='description']").first

        results = [
            CheckResult(
                test_type=CheckType.CONTENT,
                name="Page title exists",
                status=CheckStatus.PASSED if title else CheckStatus.FAILED,
                details=title or "The page title is empty.",
            ),
            CheckResult(
                test_type=CheckType.CONTENT,
                name="Body content exists",
                status=CheckStatus.PASSED if len(body_text) >= 100 else CheckStatus.WARNING,
                details=f"Visible body text length: {len(body_text)} characters.",
            ),
        ]

        try:
            description = meta_description.get_attribute("content") or ""
            results.append(
                CheckResult(
                    test_type=CheckType.CONTENT,
                    name="Meta description exists",
                    status=CheckStatus.PASSED if description.strip() else CheckStatus.WARNING,
                    details=description.strip() or "No meta description content found.",
                )
            )
        except Exception:
            results.append(
                CheckResult(
                    test_type=CheckType.CONTENT,
                    name="Meta description exists",
                    status=CheckStatus.WARNING,
                    details="No meta description tag found.",
                )
            )

        return results

    def _run_functional_checks(self, page: Page) -> list[CheckResult]:
        results = [
            CheckResult(
                test_type=CheckType.FUNCTIONAL,
                name="Page loaded",
                status=CheckStatus.PASSED,
                details=f"Loaded URL: {page.url}",
            )
        ]

        first_link = page.locator("a[href]").first
        try:
            href = first_link.get_attribute("href", timeout=5_000)
            results.append(
                CheckResult(
                    test_type=CheckType.FUNCTIONAL,
                    name="First link is reachable for interaction",
                    status=CheckStatus.PASSED if href else CheckStatus.WARNING,
                    details=f"First link href: {href}" if href else "First link has no href.",
                )
            )
        except Exception:
            results.append(
                CheckResult(
                    test_type=CheckType.FUNCTIONAL,
                    name="First link is reachable for interaction",
                    status=CheckStatus.WARNING,
                    details="No link was available for a basic interaction check.",
                )
            )

        return results

    def _check_count(
        self,
        page: Page,
        name: str,
        selector: str,
        test_type: CheckType,
    ) -> CheckResult:
        count = page.locator(selector).count()
        return CheckResult(
            test_type=test_type,
            name=name,
            status=CheckStatus.PASSED if count > 0 else CheckStatus.WARNING,
            details=f"Found {count} matching element(s).",
        )

    def _check_images_have_alt_text(self, page: Page) -> CheckResult:
        images = page.locator("img")
        image_count = images.count()
        missing_alt_count = page.locator("img:not([alt]), img[alt='']").count()

        if image_count == 0:
            return CheckResult(
                test_type=CheckType.UI,
                name="Images include alt text",
                status=CheckStatus.WARNING,
                details="No images found on the page.",
            )

        return CheckResult(
            test_type=CheckType.UI,
            name="Images include alt text",
            status=CheckStatus.PASSED if missing_alt_count == 0 else CheckStatus.WARNING,
            details=f"{missing_alt_count} of {image_count} image(s) are missing alt text.",
        )
