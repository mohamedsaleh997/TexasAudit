from enum import Enum

from pydantic import BaseModel, HttpUrl


class CheckType(str, Enum):
    UI = "UI"
    CONTENT = "Content"
    FUNCTIONAL = "Functional"


class CheckStatus(str, Enum):
    PASSED = "Passed"
    FAILED = "Failed"
    WARNING = "Warning"


class CheckRequest(BaseModel):
    url: HttpUrl
    test_types: list[CheckType]
    headless: bool = True


class CheckResult(BaseModel):
    test_type: CheckType
    name: str
    status: CheckStatus
    details: str
