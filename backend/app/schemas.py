from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ThinkLevel = Literal["low", "medium", "high"]


# --------------------------------------------------------------------------- templates


class TemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    icon: str = Field(default="file-text", max_length=40)
    instructions: str = Field(min_length=1, max_length=8000)


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=40)
    instructions: str | None = Field(default=None, min_length=1, max_length=8000)


class TemplateOut(TemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    is_builtin: bool
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- documents / jobs


class FormatRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str = Field(default="", max_length=255)
    source_filename: str | None = Field(default=None, max_length=255)
    template_id: int | None = None
    custom_instructions: str = Field(default="", max_length=4000)
    think_level: ThinkLevel = "low"
    # When set, the result overwrites this document instead of creating a new one
    document_id: int | None = None


class JobCreated(BaseModel):
    document_id: int
    status: str
    queue_position: int


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_filename: str | None
    template_id: int | None
    template_name: str | None = None
    model: str
    status: str
    duration_ms: int
    created_at: datetime
    updated_at: datetime


class DocumentOut(DocumentSummary):
    original_text: str
    formatted_markdown: str
    custom_instructions: str
    think_level: str
    error: str | None


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    formatted_markdown: str | None = Field(default=None, max_length=1_000_000)


class ExtractOut(BaseModel):
    filename: str
    title: str
    text: str
    characters: int


def document_summary(doc: Any) -> dict[str, Any]:
    data = DocumentSummary.model_validate(doc).model_dump(mode="json")
    data["template_name"] = doc.template.name if doc.template else None
    return data


def document_out(doc: Any) -> dict[str, Any]:
    data = DocumentOut.model_validate(doc).model_dump(mode="json")
    data["template_name"] = doc.template.name if doc.template else None
    return data
