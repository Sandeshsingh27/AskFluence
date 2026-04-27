from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    title: str
    url: str
    page_id: str
    score: float


class AskFilters(BaseModel):
    spaces: Optional[List[str]] = None

    @field_validator("spaces")
    @classmethod
    def _clean_spaces(cls, v):
        if v is None:
            return v
        cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        # Restrict to safe identifier characters to prevent injection in any
        # downstream string handling.
        for s in cleaned:
            if not s.replace("_", "").replace("-", "").isalnum():
                raise ValueError("Invalid space key")
        return cleaned or None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    filters: Optional[AskFilters] = None

    @field_validator("question")
    @classmethod
    def _strip_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        return v


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
