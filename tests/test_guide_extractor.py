import fitz

from app.services.guide_extractor import GuideExtractor


def test_guide_extractor_reads_pdf_text() -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Home page banner should match the approved guide.")
    pdf_bytes = document.tobytes()
    document.close()

    evidence = GuideExtractor().extract("sample guide.pdf", pdf_bytes)

    assert evidence.page_count == 1
    assert evidence.pages[0].page_number == 1
    assert "Home page banner" in evidence.pages[0].text
    assert evidence.errors == []
