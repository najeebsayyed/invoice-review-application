"""Pydantic schemas for document review API responses and client requests."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.accounting.schemas import AccountingCoding
from app.invoices.validation import ValidationIssue

DocumentStatus = Literal[
    "processing",
    "ready",
    "needs_review",
    "approved",
    "rejected",
    "failed",
]


class DocumentResponse(BaseModel):
    """Full API representation of a processed document record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    content_type: str
    status: DocumentStatus
    classification: dict[str, Any] | None = None
    extraction: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    gl_suggestion: dict[str, Any] | None = None
    accounting_coding: AccountingCoding | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    supplier_action_required: bool = False
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DecisionRequest(BaseModel):
    """Payload for user approving or rejecting a document review."""

    decision: Literal["approved", "rejected"]
