"""OpenAI service for extracting and processing invoices and receipts using Responses API."""

from __future__ import annotations

import base64
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import IO, Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.invoice import (
    InvoiceData,
    InvoiceItem,
    InvoiceTaxDetail,
)
from app.schemas.receipt import (
    ReceiptData,
    ReceiptItem,
    ReceiptTaxDetail,
)

logger = logging.getLogger(__name__)

# Resolve backend .env deterministically
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"


class OpenAISettings(BaseSettings):
    """Configuration settings for OpenAI."""

    openai_api_key: str
    openai_model: str = "gpt-5.6-terra"

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.is_file() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# ---------------------------------------------------------------------------
# Internal extraction schemas for strict structured outputs
# ---------------------------------------------------------------------------


class _ExtractedInvoiceItem(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    product_code: str | None = None
    item_date: str | None = None
    tax: float | None = None
    tax_rate: str | None = None
    amount: float | None = None
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class _ExtractedInvoiceTaxDetail(BaseModel):
    amount: float | None = None
    rate: str | None = None
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class _ExtractedInvoice(BaseModel):
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
    invoice_date: str | None = None
    due_date: str | None = None
    purchase_order: str | None = None
    payment_term: str | None = None
    subtotal: float | None = None
    total_tax: float | None = None
    invoice_total: float | None = None
    amount_due: float | None = None
    currency: str | None = None
    items: list[_ExtractedInvoiceItem] = []
    tax_details: list[_ExtractedInvoiceTaxDetail] = []
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class _ExtractedReceiptItem(BaseModel):
    description: str | None = None
    quantity: float | None = None
    quantity_unit: str | None = None
    unit_price: float | None = None
    total_price: float | None = None
    product_code: str | None = None
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class _ExtractedReceiptTaxDetail(BaseModel):
    amount: float | None = None
    rate: float | None = None
    description: str | None = None
    net_amount: float | None = None
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class _ExtractedReceipt(BaseModel):
    document_type: str = "receipt"
    merchant_name: str | None = None
    merchant_address: str | None = None
    merchant_phone_number: str | None = None
    transaction_date: str | None = None
    transaction_time: str | None = None
    subtotal: float | None = None
    total_tax: float | None = None
    tip: float | None = None
    total: float | None = None
    currency: str | None = None
    receipt_type: str | None = None
    country_region: str | None = None
    items: list[_ExtractedReceiptItem] = []
    tax_details: list[_ExtractedReceiptTaxDetail] = []
    confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class _DocumentClassification(BaseModel):
    document_type: Literal["invoice", "receipt"]
    confidence: float
    reason: str

    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# OpenAIService
# ---------------------------------------------------------------------------


class OpenAIService:
    """Encapsulates OpenAI Responses API document extraction, classification, and mapping."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = OpenAISettings()
        resolved_key = api_key or settings.openai_api_key
        resolved_model = model or settings.openai_model

        if not resolved_key or resolved_key == "your_openai_api_key":
            raise ValueError("OpenAI API key is required. Please set OPENAI_API_KEY in .env")
        if not resolved_model or resolved_model == "model_to_use":
            raise ValueError("OpenAI model is required. Please set OPENAI_MODEL in .env")

        self._client = OpenAI(api_key=resolved_key)
        self._model = resolved_model

    @property
    def model(self) -> str:
        """Configured OpenAI model name."""
        return self._model

    def _prepare_document_content(
        self,
        document_source: str | Path | bytes | IO[bytes],
    ) -> tuple[dict, str]:
        """Read document source and construct OpenAI Responses API multimodal content item."""
        filename = "document"
        if isinstance(document_source, (str, Path)):
            path = Path(document_source)
            if not path.is_file():
                raise FileNotFoundError(f"Document file not found: {path}")
            filename = path.name
            with open(path, "rb") as file_stream:
                data = file_stream.read()
        elif isinstance(document_source, bytes):
            data = document_source
        else:
            if hasattr(document_source, "name") and isinstance(document_source.name, str):
                filename = Path(document_source.name).name
            data = document_source.read()

        mime_type = self._detect_mime_type(data, filename)
        b64_str = base64.b64encode(data).decode("utf-8")

        if mime_type == "application/pdf":
            content_item = {
                "type": "input_file",
                "file_data": f"data:application/pdf;base64,{b64_str}",
                "filename": filename if filename.endswith(".pdf") else f"{filename}.pdf",
            }
        else:
            content_item = {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{b64_str}",
            }

        return content_item, mime_type

    @staticmethod
    def _detect_mime_type(data: bytes, filename: str | None = None) -> str:
        """Infer MIME type from file extension or magic bytes."""
        if filename:
            suffix = Path(filename).suffix.lower()
            if suffix == ".pdf":
                return "application/pdf"
            if suffix == ".png":
                return "image/png"
            if suffix in (".jpg", ".jpeg"):
                return "image/jpeg"
            if suffix == ".webp":
                return "image/webp"

        # Inspect magic bytes fallback
        if data.startswith(b"%PDF"):
            return "application/pdf"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"

        return "application/pdf"

    def process_invoice(self, document_source: str | Path | bytes | IO[bytes]) -> InvoiceData:
        """Analyze an invoice document using OpenAI Responses API with structured output.

        Accepts a file path (str or Path), raw bytes, or an open binary stream.
        Returns a normalized, typed InvoiceData model.
        """
        doc_content, _ = self._prepare_document_content(document_source)

        prompt_text = (
            "You are an expert financial document extractor. "
            "Extract all structured invoice fields from the provided document with high precision. "
            "If a field is not present or cannot be found, leave it as null. "
            "Extract line items, tax details, totals, currency, dates, and vendor/customer VAT IDs."
        )

        response = self._client.responses.parse(
            model=self._model,
            text_format=_ExtractedInvoice,
            input=[
                {
                    "role": "user",
                    "content": [
                        doc_content,
                        {"type": "input_text", "text": prompt_text},
                    ],
                }
            ],
        )

        extracted = response.output_parsed
        return self._map_to_invoice_data(extracted)

    def process_receipt(self, document_source: str | Path | bytes | IO[bytes]) -> ReceiptData:
        """Analyze a receipt document using OpenAI Responses API with structured output.

        Accepts a file path (str or Path), raw bytes, or an open binary stream.
        Returns a normalized, typed ReceiptData model.
        """
        doc_content, _ = self._prepare_document_content(document_source)

        prompt_text = (
            "You are an expert financial document extractor. "
            "Extract all structured receipt fields from the provided document with high precision. "
            "If a field is not present or cannot be found, leave it as null. "
            "Extract line items, tax details, merchant details, totals, currency, and date/time."
        )

        response = self._client.responses.parse(
            model=self._model,
            text_format=_ExtractedReceipt,
            input=[
                {
                    "role": "user",
                    "content": [
                        doc_content,
                        {"type": "input_text", "text": prompt_text},
                    ],
                }
            ],
        )

        extracted = response.output_parsed
        return self._map_to_receipt_data(extracted)

    def classify_document(
        self,
        document_source: str | Path | bytes | IO[bytes],
    ) -> str:
        """Classify whether a document is an 'invoice' or a 'receipt'.

        Returns 'invoice' or 'receipt'.
        """
        doc_content, _ = self._prepare_document_content(document_source)

        prompt_text = (
            "Analyze this financial document and classify if it is an 'invoice' or a 'receipt'. "
            "Provide the document_type, your confidence score (0.0 to 1.0), and a concise reason."
        )

        response = self._client.responses.parse(
            model=self._model,
            text_format=_DocumentClassification,
            input=[
                {
                    "role": "user",
                    "content": [
                        doc_content,
                        {"type": "input_text", "text": prompt_text},
                    ],
                }
            ],
        )

        return response.output_parsed.document_type

    def process_document(
        self,
        document_source: str | Path | bytes | IO[bytes],
    ) -> InvoiceData | ReceiptData:
        """Automatically classify and process a financial document (invoice or receipt)."""
        doc_type = self.classify_document(document_source)
        if doc_type == "receipt":
            return self.process_receipt(document_source)
        return self.process_invoice(document_source)

    def _map_to_invoice_data(self, extracted: _ExtractedInvoice) -> InvoiceData:
        """Map _ExtractedInvoice to the domain InvoiceData Pydantic model."""
        base_confidence = extracted.confidence or 0.95

        items: list[InvoiceItem] = []
        for item in extracted.items:
            items.append(
                InvoiceItem(
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    unit_price=self._to_decimal(item.unit_price),
                    product_code=item.product_code,
                    item_date=item.item_date,
                    tax=self._to_decimal(item.tax),
                    tax_rate=item.tax_rate,
                    amount=self._to_decimal(item.amount),
                    confidence=item.confidence or base_confidence,
                )
            )

        tax_details: list[InvoiceTaxDetail] = []
        for tax in extracted.tax_details:
            tax_details.append(
                InvoiceTaxDetail(
                    amount=self._to_decimal(tax.amount),
                    rate=tax.rate,
                    confidence=tax.confidence or base_confidence,
                )
            )

        field_confidences: dict[str, float] = {}
        for field_name, value in extracted.model_dump().items():
            if field_name not in ("confidence", "items", "tax_details") and value is not None:
                field_confidences[field_name] = base_confidence

        return InvoiceData(
            document_type="invoice",
            vendor_name=extracted.vendor_name,
            vendor_vat_id=extracted.vendor_vat_id,
            vendor_address=extracted.vendor_address,
            vendor_address_recipient=extracted.vendor_address_recipient,
            customer_name=extracted.customer_name,
            customer_id=extracted.customer_id,
            customer_vat_id=extracted.customer_vat_id,
            customer_address=extracted.customer_address,
            customer_address_recipient=extracted.customer_address_recipient,
            billing_address=extracted.billing_address,
            billing_address_recipient=extracted.billing_address_recipient,
            shipping_address=extracted.shipping_address,
            shipping_address_recipient=extracted.shipping_address_recipient,
            invoice_number=extracted.invoice_number,
            invoice_date=self._to_date(extracted.invoice_date),
            due_date=self._to_date(extracted.due_date),
            purchase_order=extracted.purchase_order,
            payment_term=extracted.payment_term,
            subtotal=self._to_decimal(extracted.subtotal),
            total_tax=self._to_decimal(extracted.total_tax),
            invoice_total=self._to_decimal(extracted.invoice_total),
            amount_due=self._to_decimal(extracted.amount_due),
            currency=extracted.currency,
            items=items,
            tax_details=tax_details,
            confidence=base_confidence,
            field_confidences=field_confidences,
        )

    def _map_to_receipt_data(self, extracted: _ExtractedReceipt) -> ReceiptData:
        """Map _ExtractedReceipt to the domain ReceiptData Pydantic model."""
        base_confidence = extracted.confidence or 0.95

        items: list[ReceiptItem] = []
        for item in extracted.items:
            items.append(
                ReceiptItem(
                    description=item.description,
                    quantity=item.quantity,
                    quantity_unit=item.quantity_unit,
                    unit_price=self._to_decimal(item.unit_price),
                    total_price=self._to_decimal(item.total_price),
                    product_code=item.product_code,
                    confidence=item.confidence or base_confidence,
                )
            )

        tax_details: list[ReceiptTaxDetail] = []
        for tax in extracted.tax_details:
            tax_details.append(
                ReceiptTaxDetail(
                    amount=self._to_decimal(tax.amount),
                    rate=tax.rate,
                    description=tax.description,
                    net_amount=self._to_decimal(tax.net_amount),
                    confidence=tax.confidence or base_confidence,
                )
            )

        field_confidences: dict[str, float] = {}
        for field_name, value in extracted.model_dump().items():
            if field_name not in ("confidence", "items", "tax_details") and value is not None:
                field_confidences[field_name] = base_confidence

        return ReceiptData(
            document_type="receipt",
            merchant_name=extracted.merchant_name,
            merchant_address=extracted.merchant_address,
            merchant_phone_number=extracted.merchant_phone_number,
            transaction_date=self._to_date(extracted.transaction_date),
            transaction_time=extracted.transaction_time,
            subtotal=self._to_decimal(extracted.subtotal),
            total_tax=self._to_decimal(extracted.total_tax),
            tip=self._to_decimal(extracted.tip),
            total=self._to_decimal(extracted.total),
            currency=extracted.currency,
            receipt_type=extracted.receipt_type,
            country_region=extracted.country_region,
            items=items,
            tax_details=tax_details,
            confidence=base_confidence,
            field_confidences=field_confidences,
        )

    @staticmethod
    def _to_decimal(val: float | str | None) -> Decimal | None:
        """Convert a scalar amount to Decimal safely."""
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    @staticmethod
    def _to_date(val: str | None) -> date | str | None:
        """Convert an ISO date string to a date object or return string fallback."""
        if not val:
            return None
        cleaned = val.strip()
        try:
            return date.fromisoformat(cleaned)
        except Exception:
            return cleaned


__all__ = [
    "OpenAIService",
    "OpenAISettings",
]
