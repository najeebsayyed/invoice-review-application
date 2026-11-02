"""Pydantic models for receipt documents extracted via Document Intelligence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ReceiptItem(BaseModel):
    """Individual line item within a receipt."""

    description: str | None = None
    quantity: float | None = None
    quantity_unit: str | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None
    product_code: str | None = None
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class ReceiptTaxDetail(BaseModel):
    """Tax breakdown detail within a receipt."""

    amount: Decimal | None = None
    rate: str | float | None = None
    description: str | None = None
    net_amount: Decimal | None = None
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class ReceiptData(BaseModel):
    """Normalized structured data extracted from a receipt document."""

    document_type: str = "receipt"
    merchant_name: str | None = None
    merchant_address: str | None = None
    merchant_phone_number: str | None = None
    transaction_date: date | str | None = None
    transaction_time: str | None = None
    subtotal: Decimal | None = None
    total_tax: Decimal | None = None
    tip: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    receipt_type: str | None = None
    country_region: str | None = None
    items: list[ReceiptItem] = Field(default_factory=list)
    tax_details: list[ReceiptTaxDetail] = Field(default_factory=list)
    confidence: float | None = None
    field_confidences: dict[str, float] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")

    @property
    def vendor_name(self) -> str | None:
        """Alias to support unified document interfaces."""
        return self.merchant_name

    @property
    def invoice_date(self) -> date | str | None:
        """Alias to support unified document interfaces."""
        return self.transaction_date

    @property
    def invoice_total(self) -> Decimal | None:
        """Alias to support unified document interfaces."""
        return self.total
