from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Severity = Literal["low", "medium", "high"]
AuditStatus = Literal["pending", "running", "completed", "failed"]
ReviewDepth = Literal["text_blocks", "image", "both"]


class RuleBase(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    severity: Severity = "medium"
    is_required: bool = True


class RuleCreate(RuleBase):
    pass


class RuleResponse(RuleBase):
    id: str

    model_config = ConfigDict(from_attributes=True)


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rules: list[RuleCreate] = Field(default_factory=list)


class StrategyUpdate(StrategyCreate):
    pass


class StrategyResponse(BaseModel):
    id: str
    name: str
    created_at: dt.datetime
    rules: list[RuleResponse]

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    page_count: int
    doc_type: str
    upload_time: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    page_count: int
    doc_type: str


class PageMeta(BaseModel):
    page_number: int
    has_text: bool
    text_preview: str = ""
    image_density: float = 0.0
    page_width: float = 0.0
    page_height: float = 0.0
    is_toc_like: bool = False
    likely_drawing: bool = False


class PageTextBlock(BaseModel):
    text: str
    bbox: list[float]

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox must contain 4 coordinates.")
        return value


class ReviewPlanPage(BaseModel):
    page: int
    depth: ReviewDepth
    reason: str


class ReviewPlan(BaseModel):
    page_budget: int
    selected_pages: list[ReviewPlanPage]
    coverage_warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AuditRequest(BaseModel):
    doc_id: str
    strategy_id: str


class AuditResultPayload(BaseModel):
    rule_id: str
    page: int
    bbox: list[float]
    content: str
    suggestion: str
    status: Literal["pass", "fail"]
    severity: Severity = "medium"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox must contain 4 coordinates.")
        return value


class AuditResultResponse(AuditResultPayload):
    id: str


class AuditJobResponse(BaseModel):
    job_id: str
    doc_id: str
    strategy_id: str
    status: AuditStatus
    progress: float
    error_message: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    review_plan: ReviewPlan | None = None
    visited_pages: list[int] = Field(default_factory=list)
    audit_log: list[str] = Field(default_factory=list)
    results: list[AuditResultResponse] = Field(default_factory=list)


class AuditSubmitResponse(BaseModel):
    job_id: str
    status: AuditStatus
    progress: float


class SearchPagesResponse(BaseModel):
    pages: list[int]


