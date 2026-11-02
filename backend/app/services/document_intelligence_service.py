"""Azure AI Document Intelligence service for processing invoices and receipts."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import IO

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeResult,
    DocumentField,
)
from azure.core.credentials import AzureKeyCredential
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.invoice import (
    InvoiceData,
    InvoiceItem,
    InvoiceTaxDetail,
    TaxDetail,
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


class DocumentIntelligenceSettings(BaseSettings):
    """Configuration settings for Azure Document Intelligence."""

    azure_document_intelligence_endpoint: str
    azure_document_intelligence_key: str

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.is_file() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class DocumentIntelligenceService:
    """Encapsulates Azure AI Document Intelligence document extraction and mapping."""

    def __init__(
        self,
        endpoint: str | None = None,
        key: str | None = None,
    ) -> None:
        settings = DocumentIntelligenceSettings()
        resolved_endpoint = endpoint or settings.azure_document_intelligence_endpoint
        resolved_key = key or settings.azure_document_intelligence_key

        if not resolved_endpoint:
            raise ValueError("Azure Document Intelligence endpoint is required.")
        if not resolved_key:
            raise ValueError("Azure Document Intelligence key is required.")

        self._client = DocumentIntelligenceClient(
            endpoint=resolved_endpoint,
            credential=AzureKeyCredential(resolved_key),
        )

    def _analyze_document(
        self,
        document_source: str | Path | bytes | IO[bytes],
        model_id: str,
    ) -> AnalyzeResult:
        """Submit document source to Document Intelligence and await result."""
        if isinstance(document_source, (str, Path)):
            path = Path(document_source)
            if not path.is_file():
                raise FileNotFoundError(f"Document file not found: {path}")
            with open(path, "rb") as file_stream:
                poller = self._client.begin_analyze_document(
                    model_id=model_id,
                    body=file_stream,
                )
                return poller.result()
        elif isinstance(document_source, bytes):
            poller = self._client.begin_analyze_document(
                model_id=model_id,
                body=document_source,
            )
            return poller.result()
        else:
            poller = self._client.begin_analyze_document(
                model_id=model_id,
                body=document_source,
            )
            return poller.result()

    def process_invoice(self, document_source: str | Path | bytes | IO[bytes]) -> InvoiceData:
        """Analyze an invoice document using the prebuilt-invoice model.

        Accepts a file path (str or Path), raw bytes, or an open binary stream.
        Returns a normalized, typed InvoiceData model.
        """
        analyze_result = self._analyze_document(document_source, model_id="prebuilt-invoice")
        return self._map_to_invoice_data(analyze_result)

    def process_receipt(self, document_source: str | Path | bytes | IO[bytes]) -> ReceiptData:
        """Analyze a receipt document using the prebuilt-receipt model.

        Accepts a file path (str or Path), raw bytes, or an open binary stream.
        Returns a normalized, typed ReceiptData model.
        """
        analyze_result = self._analyze_document(document_source, model_id="prebuilt-receipt")
        return self._map_to_receipt_data(analyze_result)

    def _map_to_invoice_data(self, result: AnalyzeResult) -> InvoiceData:
        """Map Azure AnalyzeResult to the normalized InvoiceData Pydantic model."""
        if not result.documents:
            return InvoiceData()

        doc = result.documents[0]
        fields = doc.fields or {}

        field_confidences = {
            name: round(field.confidence, 4)
            for name, field in fields.items()
            if field and field.confidence is not None
        }

        scalar_confidences = [
            field.confidence for field in fields.values() if field and field.confidence is not None
        ]
        overall_confidence = (
            round(sum(scalar_confidences) / len(scalar_confidences), 4)
            if scalar_confidences
            else doc.confidence
        )

        currency = (
            self._get_currency_code(fields.get("InvoiceTotal"))
            or self._get_currency_code(fields.get("SubTotal"))
            or self._get_currency_code(fields.get("TotalTax"))
        )

        return InvoiceData(
            document_type="invoice",
            vendor_name=self._get_string(fields.get("VendorName")),
            vendor_vat_id=self._get_string(fields.get("VendorTaxId")),
            vendor_address=self._get_content(fields.get("VendorAddress")),
            vendor_address_recipient=self._get_string(fields.get("VendorAddressRecipient")),
            customer_name=self._get_string(fields.get("CustomerName")),
            customer_id=self._get_string(fields.get("CustomerId")),
            customer_vat_id=self._get_string(fields.get("CustomerTaxId")),
            customer_address=self._get_content(fields.get("CustomerAddress")),
            customer_address_recipient=self._get_string(fields.get("CustomerAddressRecipient")),
            billing_address=self._get_content(fields.get("BillingAddress")),
            billing_address_recipient=self._get_string(fields.get("BillingAddressRecipient")),
            shipping_address=self._get_content(fields.get("ShippingAddress")),
            shipping_address_recipient=self._get_string(fields.get("ShippingAddressRecipient")),
            invoice_number=self._get_string(fields.get("InvoiceId")),
            invoice_date=self._get_date(fields.get("InvoiceDate")),
            due_date=self._get_date(fields.get("DueDate")),
            purchase_order=self._get_string(fields.get("PurchaseOrder")),
            payment_term=self._get_string(fields.get("PaymentTerm")),
            subtotal=self._get_currency_amount(fields.get("SubTotal")),
            total_tax=self._get_currency_amount(fields.get("TotalTax")),
            invoice_total=self._get_currency_amount(fields.get("InvoiceTotal")),
            amount_due=self._get_currency_amount(fields.get("AmountDue")),
            currency=currency,
            items=self._parse_invoice_items(fields.get("Items")),
            tax_details=self._parse_invoice_tax_details(fields.get("TaxDetails")),
            confidence=overall_confidence,
            field_confidences=field_confidences,
        )

    def _map_to_receipt_data(self, result: AnalyzeResult) -> ReceiptData:
        """Map Azure AnalyzeResult to the normalized ReceiptData Pydantic model."""
        if not result.documents:
            return ReceiptData()

        doc = result.documents[0]
        fields = doc.fields or {}

        field_confidences = {
            name: round(field.confidence, 4)
            for name, field in fields.items()
            if field and field.confidence is not None
        }

        scalar_confidences = [
            field.confidence for field in fields.values() if field and field.confidence is not None
        ]
        overall_confidence = (
            round(sum(scalar_confidences) / len(scalar_confidences), 4)
            if scalar_confidences
            else doc.confidence
        )

        currency = (
            self._get_currency_code(fields.get("Total"))
            or self._get_currency_code(fields.get("Subtotal"))
            or self._get_currency_code(fields.get("TotalTax"))
            or self._get_currency_code(fields.get("Tax"))
        )

        return ReceiptData(
            document_type="receipt",
            merchant_name=self._get_string(fields.get("MerchantName")),
            merchant_address=self._get_content(fields.get("MerchantAddress")),
            merchant_phone_number=self._get_string(fields.get("MerchantPhoneNumber")),
            transaction_date=self._get_date(fields.get("TransactionDate")),
            transaction_time=self._get_time(fields.get("TransactionTime")),
            subtotal=self._get_currency_amount(fields.get("Subtotal")),
            total_tax=self._get_currency_amount(fields.get("TotalTax"))
            or self._get_currency_amount(fields.get("Tax")),
            tip=self._get_currency_amount(fields.get("Tip")),
            total=self._get_currency_amount(fields.get("Total")),
            currency=currency,
            receipt_type=self._get_string(fields.get("ReceiptType")),
            country_region=self._get_string(fields.get("CountryRegion")),
            items=self._parse_receipt_items(fields.get("Items")),
            tax_details=self._parse_receipt_tax_details(fields.get("TaxDetails")),
            confidence=overall_confidence,
            field_confidences=field_confidences,
        )

    def _parse_invoice_items(self, items_field: DocumentField | None) -> list[InvoiceItem]:
        """Parse invoice line items from the Items field."""
        if not items_field or not items_field.value_array:
            return []

        items: list[InvoiceItem] = []
        for item_field in items_field.value_array:
            item_obj = item_field.value_object or {}
            qty_field = item_obj.get("Quantity")
            date_field = item_obj.get("Date")

            qty_val = (
                float(qty_field.value_number)
                if qty_field and qty_field.value_number is not None
                else None
            )

            item_date_val = None
            if date_field:
                item_date_val = (
                    str(date_field.value_date)
                    if date_field.value_date
                    else self._get_string(date_field)
                )

            items.append(
                InvoiceItem(
                    description=self._get_string(item_obj.get("Description")),
                    quantity=qty_val,
                    unit=self._get_string(item_obj.get("Unit")),
                    unit_price=self._get_currency_amount(item_obj.get("UnitPrice")),
                    product_code=self._get_string(item_obj.get("ProductCode")),
                    item_date=item_date_val,
                    tax=self._get_currency_amount(item_obj.get("Tax")),
                    tax_rate=self._get_string(item_obj.get("TaxRate")),
                    amount=self._get_currency_amount(item_obj.get("Amount")),
                    confidence=item_field.confidence,
                )
            )
        return items

    def _parse_receipt_items(self, items_field: DocumentField | None) -> list[ReceiptItem]:
        """Parse receipt line items from the Items field."""
        if not items_field or not items_field.value_array:
            return []

        items: list[ReceiptItem] = []
        for item_field in items_field.value_array:
            item_obj = item_field.value_object or {}
            qty_field = item_obj.get("Quantity")

            qty_val = (
                float(qty_field.value_number)
                if qty_field and qty_field.value_number is not None
                else None
            )

            description = self._get_string(item_obj.get("Description")) or self._get_string(
                item_obj.get("Name")
            )
            unit_price = (
                self._get_currency_amount(item_obj.get("Price"))
                or self._get_currency_amount(item_obj.get("UnitPrice"))
            )
            total_price = (
                self._get_currency_amount(item_obj.get("TotalPrice"))
                or self._get_currency_amount(item_obj.get("Amount"))
            )
            quantity_unit = self._get_string(item_obj.get("QuantityUnit")) or self._get_string(
                item_obj.get("Unit")
            )

            items.append(
                ReceiptItem(
                    description=description,
                    quantity=qty_val,
                    quantity_unit=quantity_unit,
                    unit_price=unit_price,
                    total_price=total_price,
                    product_code=self._get_string(item_obj.get("ProductCode")),
                    confidence=item_field.confidence,
                )
            )
        return items

    def _parse_invoice_tax_details(self, tax_field: DocumentField | None) -> list[InvoiceTaxDetail]:
        """Parse tax breakdown from the TaxDetails field for invoices."""
        if not tax_field or not tax_field.value_array:
            return []

        tax_details: list[InvoiceTaxDetail] = []
        for tax_item in tax_field.value_array:
            tax_obj = tax_item.value_object or {}
            tax_details.append(
                InvoiceTaxDetail(
                    amount=self._get_currency_amount(tax_obj.get("Amount")),
                    rate=self._get_rate(tax_obj.get("Rate")),
                    confidence=tax_item.confidence,
                )
            )
        return tax_details

    def _parse_receipt_tax_details(self, tax_field: DocumentField | None) -> list[ReceiptTaxDetail]:
        """Parse tax breakdown from the TaxDetails field for receipts."""
        if not tax_field or not tax_field.value_array:
            return []

        tax_details: list[ReceiptTaxDetail] = []
        for tax_item in tax_field.value_array:
            tax_obj = tax_item.value_object or {}
            tax_details.append(
                ReceiptTaxDetail(
                    amount=self._get_currency_amount(tax_obj.get("Amount")),
                    rate=self._get_rate(tax_obj.get("Rate")),
                    description=self._get_string(tax_obj.get("Description")),
                    net_amount=self._get_currency_amount(tax_obj.get("NetAmount")),
                    confidence=tax_item.confidence,
                )
            )
        return tax_details

    @staticmethod
    def _get_string(field: DocumentField | None) -> str | None:
        if field is None:
            return None
        return field.value_string or field.content

    @staticmethod
    def _get_content(field: DocumentField | None) -> str | None:
        if field is None:
            return None
        return field.content

    @staticmethod
    def _get_date(field: DocumentField | None) -> date | str | None:
        if field is None:
            return None
        return field.value_date or field.content

    @staticmethod
    def _get_time(field: DocumentField | None) -> str | None:
        if field is None:
            return None
        if hasattr(field, "value_time") and field.value_time:
            return str(field.value_time)
        return field.value_string or field.content

    @staticmethod
    def _get_rate(field: DocumentField | None) -> str | float | None:
        if field is None:
            return None
        if hasattr(field, "value_number") and field.value_number is not None:
            return float(field.value_number)
        return field.value_string or field.content

    @staticmethod
    def _get_currency_amount(field: DocumentField | None) -> Decimal | None:
        if field is None:
            return None
        if field.value_currency and field.value_currency.amount is not None:
            return Decimal(str(field.value_currency.amount))
        if hasattr(field, "value_number") and field.value_number is not None:
            return Decimal(str(field.value_number))
        if field.content:
            cleaned = field.content.replace("EUR", "").replace("$", "").replace("€", "").strip()
            try:
                return Decimal(cleaned)
            except Exception:
                return None
        return None

    @staticmethod
    def _get_currency_code(field: DocumentField | None) -> str | None:
        if field and field.value_currency:
            return field.value_currency.currency_code or field.value_currency.currency_symbol
        return None


# Re-exports for backward compatibility
__all__ = [
    "DocumentIntelligenceService",
    "DocumentIntelligenceSettings",
    "InvoiceData",
    "InvoiceItem",
    "InvoiceTaxDetail",
    "ReceiptData",
    "ReceiptItem",
    "ReceiptTaxDetail",
    "TaxDetail",
]
