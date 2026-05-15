from pathlib import Path

import streamlit as st
from pydantic import ValidationError
from streamlit.runtime.uploaded_file_manager import UploadedFile

from app.models.ai_settings import DEFAULT_MODELS, AiProvider, AiSettings
from app.models.guide_evidence import GuideEvidence
from app.models.page_evidence import CrawlResult, PageEvidence
from app.models.test_result import CheckRequest, CheckResult, CheckStatus, CheckType
from app.models.website import WebsiteConfig
from app.services.guide_extractor import GuideExtractor
from app.services.playwright_runner import PlaywrightRunner
from app.services.site_crawler import SiteCrawler
from app.services.website_health_auditor import WebsiteHealthAuditor
from app.services.website_registry import WebsiteRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
TEXAS_LOGO_PATH = ASSETS_DIR / "texas logo.png"
PS_LOGO_PATH = ASSETS_DIR / "ps_logo-removebg-preview.png"


STATUS_BADGES = {
    CheckStatus.PASSED: "Passed",
    CheckStatus.WARNING: "Warning",
    CheckStatus.FAILED: "Failed",
}


def render_app() -> None:
    st.set_page_config(page_title="Texas Audit", layout="wide")
    _apply_styles()
    _render_brand_bar()
    _render_header()

    sidebar_values = _render_sidebar()
    if sidebar_values is None:
        _render_empty_state()
        return

    website, request, ai_settings, guide_file = sidebar_values
    guide_evidence = None

    if guide_file is not None:
        with st.spinner("Extracting guide PDF text and images..."):
            guide_evidence = GuideExtractor().extract(guide_file.name, guide_file.getvalue())

    with st.spinner("Crawling website and collecting audit evidence..."):
        crawl_result = SiteCrawler().crawl(website, headless=request.headless)

    with st.spinner("Running audit checks on the selected website..."):
        results = PlaywrightRunner().run(request)
        results.extend(WebsiteHealthAuditor().audit(crawl_result))

    _render_ai_settings_summary(ai_settings)
    if guide_evidence is not None:
        _render_guide_evidence(guide_evidence)
    _render_crawl_results(crawl_result)
    _render_results(results)


def _render_brand_bar() -> None:
    logo_columns = st.columns([0.55, 0.55, 5])

    with logo_columns[0]:
        if TEXAS_LOGO_PATH.exists():
            st.image(str(TEXAS_LOGO_PATH), width=68)

    with logo_columns[1]:
        if PS_LOGO_PATH.exists():
            st.image(str(PS_LOGO_PATH), width=88)


def _render_header() -> None:
    st.markdown(
        """
        <section class="app-header">
            <div>
                <p class="eyebrow">QA Website Audit</p>
                <h1>Texas Audit</h1>
                <p class="header-copy">
                    Review informative country websites for UI, content, and functional quality.
                </p>
            </div>
            <div class="header-panel">
                <span>Current scope</span>
                <strong>Playwright smoke audit</strong>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar() -> tuple[WebsiteConfig, CheckRequest, AiSettings, UploadedFile | None] | None:
    websites = WebsiteRegistry().list_websites()

    with st.sidebar:
        st.markdown("## Audit Setup")
        st.caption("Choose a site and the audit areas you want to run.")

        if not websites:
            st.error("No websites are configured.")
            return None

        with st.form("audit-form"):
            selected_website = st.selectbox(
                "Website",
                options=websites,
                format_func=lambda website: website.display_name,
            )
            selected_test_types = st.multiselect(
                "Audit areas",
                options=list(CheckType),
                default=[CheckType.UI, CheckType.CONTENT, CheckType.FUNCTIONAL],
                format_func=lambda option: option.value,
            )
            headless = st.toggle("Run browser in background", value=True)
            guide_file = st.file_uploader("Audit guide PDF", type=["pdf"])
            st.markdown("### AI Review")
            ai_enabled = st.checkbox("Enable AI review", value=False)
            ai_provider = st.selectbox(
                "AI provider",
                options=list(AiProvider),
                format_func=lambda provider: provider.value,
                disabled=not ai_enabled,
            )
            model_name = st.text_input(
                "Model name",
                value=DEFAULT_MODELS[ai_provider],
                disabled=not ai_enabled,
            )
            api_key = st.text_input(
                "API key",
                type="password",
                placeholder="Stored for this session only",
                disabled=not ai_enabled,
            )
            base_url = ""
            if ai_provider == AiProvider.CUSTOM:
                base_url = st.text_input(
                    "Base URL",
                    placeholder="https://api.provider.com/v1",
                    disabled=not ai_enabled,
                )
            submitted = st.form_submit_button("Run Audit", type="primary", use_container_width=True)

    if not submitted:
        return None

    if not websites:
        st.error("No websites are configured.")
        return None

    try:
        request = CheckRequest(
            url=selected_website.base_url,
            test_types=selected_test_types,
            headless=headless,
        )
        ai_settings = AiSettings(
            enabled=ai_enabled,
            provider=ai_provider,
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
        )
    except ValidationError as error:
        st.error(_format_validation_error(error))
        return None
    except ValueError as error:
        st.error(str(error))
        return None

    if not request.test_types:
        st.warning("Select at least one audit area.")
        return None

    return selected_website, request, ai_settings, guide_file


def _render_empty_state() -> None:
    columns = st.columns(3)
    audit_cards = [
        (
            "UI Review",
            "Checks page structure, banners, images, buttons, and visible UI elements.",
        ),
        (
            "Content Review",
            "Checks title, visible text, and content signals that will later support brand guide comparison.",
        ),
        (
            "Functional Review",
            "Checks that the page loads and key links or actions are available for interaction.",
        ),
    ]

    for column, (title, description) in zip(columns, audit_cards, strict=True):
        with column:
            st.markdown(
                f"""
                <div class="audit-card">
                    <h3>{title}</h3>
                    <p>{description}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.info("Select the Iraq website in the sidebar and click Run Audit.")


def _render_ai_settings_summary(ai_settings: AiSettings) -> None:
    if not ai_settings.enabled:
        st.caption("AI review is disabled for this run.")
        return

    st.markdown(
        f"""
        <div class="ai-summary">
            <strong>AI review configured</strong>
            <span>{ai_settings.provider.value} / {ai_settings.model_name}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_guide_evidence(guide_evidence: GuideEvidence) -> None:
    st.markdown("## Guide PDF Status")
    columns = st.columns(4)
    total_images = sum(len(page.images) for page in guide_evidence.pages)
    total_text_chars = sum(len(page.text) for page in guide_evidence.pages)

    if guide_evidence.errors:
        st.error("Guide PDF was uploaded, but some pages failed during extraction.")
    else:
        st.success("Guide PDF uploaded and extracted successfully.")

    columns[0].metric("PDF Pages", guide_evidence.page_count)
    columns[1].metric("Reference Images", total_images)
    columns[2].metric("Text Characters", total_text_chars)
    columns[3].metric("Issues", len(guide_evidence.errors))

    if guide_evidence.errors:
        st.markdown("### Guide Issues")
        for error in guide_evidence.errors:
            st.warning(error)

    with st.expander("Raw guide extraction details", expanded=False):
        st.caption(f"Saved PDF: {guide_evidence.saved_pdf_path}")

        for page in guide_evidence.pages:
            st.markdown(f"**Guide page {page.page_number}**")
            text_tab, images_tab = st.tabs(["Text", "Images"])

            with text_tab:
                st.write(page.text or "No selectable text extracted from this page.")

            with images_tab:
                if not page.images:
                    st.caption("No embedded images extracted from this page.")
                    continue

                for image in page.images:
                    image_path = PROJECT_ROOT / image.file_path
                    st.image(str(image_path), caption=image.file_path, use_container_width=True)

                st.dataframe(
                    [
                        {
                            "Image": image.file_path,
                            "Width": image.width,
                            "Height": image.height,
                            "Extension": image.extension,
                        }
                        for image in page.images
                    ],
                    use_container_width=True,
                    hide_index=True,
                )


def _render_crawl_results(crawl_result: CrawlResult) -> None:
    st.markdown("## Website Crawl Status")
    summary_columns = st.columns(4)
    total_images = sum(len(page.images) for page in crawl_result.pages)
    total_links = sum(len(page.links) for page in crawl_result.pages)
    total_banners = sum(len(page.banners) for page in crawl_result.pages)

    if crawl_result.errors:
        st.error("Website crawl finished, but some pages failed.")
    elif not crawl_result.pages:
        st.error("Website crawl did not collect any pages.")
    else:
        st.success("Website crawled successfully and evidence was captured.")

    summary_columns[0].metric("Pages Crawled", len(crawl_result.pages))
    summary_columns[1].metric("Links Found", total_links)
    summary_columns[2].metric("Images Found", total_images)
    summary_columns[3].metric("Banner Screenshots", total_banners)

    if crawl_result.errors:
        st.markdown("### Crawl Issues")
        for error in crawl_result.errors:
            st.warning(error)

    with st.expander("Raw website evidence details", expanded=False):
        for page_number, page in enumerate(crawl_result.pages, start=1):
            _render_page_evidence(page_number, page)


def _render_page_evidence(page_number: int, page: PageEvidence) -> None:
    with st.expander(f"Page {page_number}: {page.title or page.url}", expanded=page_number == 1):
        st.caption(page.url)

        overview_columns = st.columns(4)
        overview_columns[0].metric("Headings", len(page.headings))
        overview_columns[1].metric("Buttons", len(page.buttons))
        overview_columns[2].metric("Links", len(page.links))
        overview_columns[3].metric("Images", len(page.images))

        if page.screenshot_path:
            st.caption(f"Screenshot: {page.screenshot_path}")

        content_tab, links_tab, images_tab, banners_tab = st.tabs(
            ["Content", "Links", "Images", "Banner Candidates"]
        )

        with content_tab:
            if page.headings:
                st.markdown("**Headings**")
                st.write(page.headings)

            if page.buttons:
                st.markdown("**Buttons**")
                st.write(page.buttons)

            st.markdown("**Text preview**")
            st.write(page.text_preview or "No visible text collected.")

        with links_tab:
            st.dataframe(
                [{"Text": link.text, "URL": link.url} for link in page.links],
                use_container_width=True,
                hide_index=True,
            )

        with images_tab:
            st.dataframe(
                [
                    {
                        "Alt": image.alt,
                        "Source": image.src,
                        "Width": image.width,
                        "Height": image.height,
                    }
                    for image in page.images
                ],
                use_container_width=True,
                hide_index=True,
            )

        with banners_tab:
            if not page.banners:
                st.caption("No banner screenshots captured on this page.")
                return

            for banner_number, banner in enumerate(page.banners, start=1):
                st.markdown(f"**Banner {banner_number}**")
                if banner.screenshot_path:
                    st.image(str(PROJECT_ROOT / banner.screenshot_path), use_container_width=True)
                st.caption(
                    f"{banner.selector} | {banner.width}x{banner.height} | {banner.screenshot_path}"
                )
                if banner.text:
                    st.write(banner.text)

            st.dataframe(
                [
                    {
                        "Screenshot": banner.screenshot_path,
                        "Selector": banner.selector,
                        "Image Source": banner.image_src,
                        "Width": banner.width,
                        "Height": banner.height,
                    }
                    for banner in page.banners
                ],
                use_container_width=True,
                hide_index=True,
            )


def _render_results(results: list[CheckResult]) -> None:
    passed_count = sum(result.status == CheckStatus.PASSED for result in results)
    warning_count = sum(result.status == CheckStatus.WARNING for result in results)
    failed_count = sum(result.status == CheckStatus.FAILED for result in results)
    total_count = len(results)

    st.markdown("## Audit Check Status")
    metric_columns = st.columns(4)
    metric_columns[0].metric("Total Checks", total_count)
    metric_columns[1].metric("Passed", passed_count)
    metric_columns[2].metric("Warnings", warning_count)
    metric_columns[3].metric("Failed", failed_count)

    failed_results = [result for result in results if result.status == CheckStatus.FAILED]
    warning_results = [result for result in results if result.status == CheckStatus.WARNING]

    if failed_results:
        st.error("Some audit checks failed.")
        for result in failed_results:
            _render_result_item(result)
    else:
        st.success("No failed audit checks found.")

    if warning_results:
        with st.expander("Warnings requiring QA review", expanded=False):
            for result in warning_results:
                _render_result_item(result)

    with st.expander("All audit check results", expanded=False):
        st.dataframe(
            [
                {
                    "Area": result.test_type.value,
                    "Check": result.name,
                    "Status": result.status.value,
                    "Details": result.details,
                }
                for result in results
            ],
            use_container_width=True,
            hide_index=True,
        )


def _render_result_item(result: CheckResult) -> None:
    st.markdown(
        f"""
        <div class="result-item {result.status.value.lower()}">
            <div>
                <span class="status-badge">{STATUS_BADGES[result.status]}</span>
                <h4>{result.name}</h4>
            </div>
            <p>{result.details}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _format_validation_error(error: ValidationError) -> str:
    first_error = error.errors()[0]
    return str(first_error.get("msg", "Invalid audit request."))


def _apply_styles() -> None:
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 2rem;
                padding-bottom: 3rem;
            }

            .brand-spacer {
                min-height: 78px;
            }

            .app-header {
                align-items: center;
                background: #f7f7f4;
                border: 1px solid #e1ded6;
                border-left: 8px solid #c8102e;
                display: flex;
                justify-content: space-between;
                margin-bottom: 1.5rem;
                padding: 1.5rem 1.75rem;
            }

            .eyebrow {
                color: #6f6257;
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0;
                margin: 0 0 0.35rem;
                text-transform: uppercase;
            }

            .app-header h1 {
                color: #202020;
                font-size: 2.25rem;
                line-height: 1.1;
                margin: 0;
            }

            .header-copy {
                color: #5f5b56;
                font-size: 1rem;
                margin: 0.5rem 0 0;
                max-width: 720px;
            }

            .header-panel {
                background: #ffffff;
                border: 1px solid #e1ded6;
                min-width: 220px;
                padding: 1rem;
            }

            .header-panel span {
                color: #6f6257;
                display: block;
                font-size: 0.78rem;
                margin-bottom: 0.25rem;
            }

            .header-panel strong {
                color: #202020;
                font-size: 0.95rem;
            }

            .audit-card {
                background: #ffffff;
                border: 1px solid #e1ded6;
                min-height: 150px;
                padding: 1.25rem;
            }

            .audit-card h3 {
                color: #202020;
                font-size: 1.05rem;
                margin: 0 0 0.6rem;
            }

            .audit-card p {
                color: #5f5b56;
                font-size: 0.95rem;
                line-height: 1.5;
                margin: 0;
            }

            .ai-summary {
                align-items: center;
                background: #fff7e0;
                border: 1px solid #edd28b;
                display: flex;
                gap: 0.75rem;
                justify-content: space-between;
                margin-bottom: 1rem;
                padding: 0.85rem 1rem;
            }

            .ai-summary strong {
                color: #202020;
            }

            .ai-summary span {
                color: #5f5b56;
            }

            .result-item {
                background: #ffffff;
                border: 1px solid #e1ded6;
                border-left: 6px solid #b7b1a8;
                margin-bottom: 0.75rem;
                padding: 1rem 1.1rem;
            }

            .result-item.passed {
                border-left-color: #237a57;
            }

            .result-item.warning {
                border-left-color: #b7791f;
            }

            .result-item.failed {
                border-left-color: #c8102e;
            }

            .result-item h4 {
                color: #202020;
                font-size: 1rem;
                margin: 0.35rem 0 0;
            }

            .result-item p {
                color: #5f5b56;
                margin: 0.55rem 0 0;
            }

            .status-badge {
                background: #f2f0ea;
                color: #202020;
                display: inline-block;
                font-size: 0.78rem;
                font-weight: 700;
                padding: 0.18rem 0.5rem;
            }

            section[data-testid="stSidebar"] {
                background: #fbfaf7;
                border-right: 1px solid #e1ded6;
            }

            div[data-testid="stMetric"] {
                background: #ffffff;
                border: 1px solid #e1ded6;
                padding: 1rem;
            }

            div[data-testid="stMetricValue"] {
                color: #202020;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
