"""Pydantic models for invoice documents extracted via Document Intelligence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InvoiceItem(BaseModel):
    """Individual line item within an invoice."""

    description: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    product_code: str | None = None
    item_date: str | None = None
    tax: Decimal | None = None
    tax_rate: str | None = None
    amount: Decimal | None = None
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class InvoiceTaxDetail(BaseModel):
    """Tax breakdown detail within an invoice."""

    amount: Decimal | None = None
    rate: str | float | None = None
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


# Backward compatibility alias
TaxDetail = InvoiceTaxDetail


class InvoiceData(BaseModel):
    """Normalized structured data extracted from an invoice document."""

    document_type: str = "invoice"
    vendor_name: str | None = None
    vendor_vat_id: str | None = None
    vendor_address: str | None = None
    vendor_address_recipient: str | None = None
    customer_name: str | None = None
    customer_id: str | None = None
    customer_vat_id: str | None = None
    customer_address: str | None = None
    customer_address_recipient: str | None = None
    billing_address: str | None = None
    billing_address_recipient: str | None = None
    shipping_address: str | None = None
    shipping_address_recipient: str | None = None
    invoice_number: str | None = None
    invoice_date: date | str | None = None
    due_date: date | str | None = None
    purchase_order: str | None = None
    payment_term: str | None = None
    subtotal: Decimal | None = None
    total_tax: Decimal | None = None
    invoice_total: Decimal | None = None
    amount_due: Decimal | None = None
    currency: str | None = None
    items: list[InvoiceItem] = Field(default_factory=list)
    tax_details: list[InvoiceTaxDetail] = Field(default_factory=list)
    confidence: float | None = None
    field_confidences: dict[str, float] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")
