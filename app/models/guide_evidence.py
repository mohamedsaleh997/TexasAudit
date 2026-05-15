from pydantic import BaseModel


class GuideImageEvidence(BaseModel):
    page_number: int
    image_number: int
    file_path: str
    width: int
    height: int
    extension: str


class GuidePageEvidence(BaseModel):
    page_number: int
    text: str
    images: list[GuideImageEvidence]


class GuideEvidence(BaseModel):
    file_name: str
    saved_pdf_path: str
    page_count: int
    pages: list[GuidePageEvidence]
    errors: list[str]

