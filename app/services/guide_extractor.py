from pathlib import Path
from re import sub

import fitz

from app.models.guide_evidence import GuideEvidence, GuideImageEvidence, GuidePageEvidence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUIDE_DIR = PROJECT_ROOT / "reports" / "guide"


class GuideExtractor:
    def extract(self, file_name: str, file_bytes: bytes) -> GuideEvidence:
        GUIDE_DIR.mkdir(parents=True, exist_ok=True)
        safe_file_name = self._safe_file_name(file_name)
        saved_pdf_path = GUIDE_DIR / safe_file_name
        saved_pdf_path.write_bytes(file_bytes)

        pages: list[GuidePageEvidence] = []
        errors: list[str] = []

        with fitz.open(stream=file_bytes, filetype="pdf") as document:
            for page_index, page in enumerate(document, start=1):
                try:
                    images = self._extract_page_images(document, page, page_index, safe_file_name)
                    pages.append(
                        GuidePageEvidence(
                            page_number=page_index,
                            text=self._normalize_text(page.get_text("text")),
                            images=images,
                        )
                    )
                except Exception as error:
                    errors.append(f"Page {page_index}: {error}")

            page_count = document.page_count

        return GuideEvidence(
            file_name=file_name,
            saved_pdf_path=str(saved_pdf_path.relative_to(PROJECT_ROOT)),
            page_count=page_count,
            pages=pages,
            errors=errors,
        )

    def _extract_page_images(
        self,
        document: fitz.Document,
        page: fitz.Page,
        page_number: int,
        safe_file_name: str,
    ) -> list[GuideImageEvidence]:
        images: list[GuideImageEvidence] = []
        pdf_stem = Path(safe_file_name).stem

        for image_number, image_info in enumerate(page.get_images(full=True), start=1):
            xref = image_info[0]
            image = document.extract_image(xref)
            extension = image.get("ext", "png")
            image_bytes = image["image"]
            image_path = GUIDE_DIR / f"{pdf_stem}-page-{page_number}-image-{image_number}.{extension}"
            image_path.write_bytes(image_bytes)

            images.append(
                GuideImageEvidence(
                    page_number=page_number,
                    image_number=image_number,
                    file_path=str(image_path.relative_to(PROJECT_ROOT)),
                    width=image.get("width", 0),
                    height=image.get("height", 0),
                    extension=extension,
                )
            )

        return images

    def _normalize_text(self, text: str) -> str:
        return sub(r"\s+", " ", text).strip()

    def _safe_file_name(self, file_name: str) -> str:
        safe_name = sub(r"[^A-Za-z0-9_.-]+", "-", file_name).strip("-")
        return safe_name or "guide.pdf"

