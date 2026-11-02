"""Pydantic schemas for document review API responses and client requests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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


class ReviewLineItem(BaseModel):
    """Line item within review projection."""

    description: str | None = None
    quantity: float | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class ReviewData(BaseModel):
    """Normalized document view for human review and presentation."""

    document_type: str = "invoice"
    expense_category: str | None = None
    vendor_name: str | None = None
    vendor_vat_id: str | None = None
    customer_name: str | None = None
    customer_vat_id: str | None = None
    invoice_number: str | None = None
    purchase_order: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    total_tax: Decimal | None = None
    invoice_total: Decimal | None = None
    amount_due: Decimal | None = None
    line_items: list[ReviewLineItem] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)
    conflicts: dict[str, dict[str, Any]] = Field(default_factory=dict)


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
    review_data: ReviewData | None = None
    accounting_coding: AccountingCoding | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    supplier_action_required: bool = False
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DecisionRequest(BaseModel):
    """Payload for user approving or rejecting a document review."""

    decision: Literal["approved", "rejected"]


class FieldCorrectionRequest(BaseModel):
    """Payload for reviewer correcting extracted document fields."""

    vendor_name: str | None = None
    vendor_vat_id: str | None = None
    customer_name: str | None = None
    customer_vat_id: str | None = None
    invoice_number: str | None = None
    purchase_order: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    total_tax: Decimal | None = None
    invoice_total: Decimal | None = None


class CorrectionEmailResponse(BaseModel):
    """Structured supplier correction email draft."""

    subject: str
    body: str
