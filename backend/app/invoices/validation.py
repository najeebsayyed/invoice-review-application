"""Deterministic Northstar finance validation policies for invoices and receipts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field
from stdnum.eu.vat import is_valid as is_valid_eu_vat

from app.schemas.invoice import InvoiceData
from app.schemas.receipt import ReceiptData

NORTHSTAR_CUSTOMER_NAME = "Northstar Facilities B.V."
NORTHSTAR_CUSTOMER_VAT_ID = "NL00449544B01"
TOLERANCE = Decimal("0.01")
CONFIDENCE_THRESHOLD = 0.80


class IssueSeverity(StrEnum):
    """Severity levels for Northstar validation issues."""

    error = "error"
    warning = "warning"
    info = "info"


class ValidationIssue(BaseModel):
    """Represents a discrete compliance or arithmetic issue found during validation."""

    code: str = Field(description="Machine-readable issue code matching evaluation corpus")
    message: str = Field(description="Human-readable explanation of policy violation")
    severity: IssueSeverity = Field(description="Severity: error blocks approval, warning flags")
    field: str | None = Field(default=None, description="Document field associated with issue")


def _parse_date(val: date | str | None) -> date | None:
    """Coerce date or ISO string to date object."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return date.fromisoformat(val.strip())
        except Exception:
            return None
    return None


def _clean_vat(vat: str | None) -> str | None:
    """Strip spaces, dots, and convert to uppercase."""
    if not vat:
        return None
    return vat.strip().replace(" ", "").replace(".", "").upper()


def validate_invoice(
    invoice: InvoiceData,
    existing_invoices: Iterable[tuple[str, str]] | None = None,
) -> list[ValidationIssue]:
    """Pure deterministic validation of an invoice against Northstar policy.

    Errors (block approval):
    - missing vendor / customer identity
    - missing or malformed supplier VAT (offline EU structure/checksum check)
    - missing or mismatched customer VAT (must match Northstar: NL00449544B01)
    - missing invoice number, invoice date, currency, or total
    - non-positive total
    - invalid date order (due_date < invoice_date)
    - total mismatch over EUR 0.01 (subtotal + total_tax != invoice_total)
    - duplicate vendor/invoice keys

    Warnings:
    - missing purchase order
    - low primary extraction confidence (< 0.80)
    """
    issues: list[ValidationIssue] = []

    # 1. Vendor & Customer identity
    if not invoice.vendor_name or not invoice.vendor_name.strip():
        issues.append(
            ValidationIssue(
                code="vendor_name_required",
                message="Vendor name is required.",
                severity=IssueSeverity.error,
                field="vendor_name",
            )
        )

    if not invoice.customer_name or not invoice.customer_name.strip():
        issues.append(
            ValidationIssue(
                code="customer_name_required",
                message="Customer name is required.",
                severity=IssueSeverity.error,
                field="customer_name",
            )
        )

    # 2. Supplier VAT validation (EU structure/checksum with python-stdnum)
    cleaned_vendor_vat = _clean_vat(invoice.vendor_vat_id)
    if not cleaned_vendor_vat:
        issues.append(
            ValidationIssue(
                code="vendor_vat_id_required",
                message="Supplier VAT ID is required on invoices.",
                severity=IssueSeverity.error,
                field="vendor_vat_id",
            )
        )
    elif not is_valid_eu_vat(cleaned_vendor_vat):
        issues.append(
            ValidationIssue(
                code="vendor_vat_id_invalid",
                message=f"Supplier VAT ID '{invoice.vendor_vat_id}' is invalid or malformed.",
                severity=IssueSeverity.error,
                field="vendor_vat_id",
            )
        )

    # 3. Customer VAT check (must match Northstar B.V.)
    cleaned_customer_vat = _clean_vat(invoice.customer_vat_id)
    if not cleaned_customer_vat:
        issues.append(
            ValidationIssue(
                code="customer_vat_id_required",
                message="Customer VAT ID is required on invoices.",
                severity=IssueSeverity.error,
                field="customer_vat_id",
            )
        )
    elif cleaned_customer_vat != NORTHSTAR_CUSTOMER_VAT_ID:
        issues.append(
            ValidationIssue(
                code="customer_vat_id_mismatch",
                message=(
                    f"Customer VAT ID '{invoice.customer_vat_id}' does not match "
                    f"Northstar VAT ID '{NORTHSTAR_CUSTOMER_VAT_ID}'."
                ),
                severity=IssueSeverity.error,
                field="customer_vat_id",
            )
        )

    # 4. Mandatory fields: invoice number, dates, currency, total
    if not invoice.invoice_number or not invoice.invoice_number.strip():
        issues.append(
            ValidationIssue(
                code="invoice_number_required",
                message="Invoice number is required.",
                severity=IssueSeverity.error,
                field="invoice_number",
            )
        )

    if not invoice.invoice_date:
        issues.append(
            ValidationIssue(
                code="invoice_date_required",
                message="Invoice date is required.",
                severity=IssueSeverity.error,
                field="invoice_date",
            )
        )

    if not invoice.currency or not invoice.currency.strip():
        issues.append(
            ValidationIssue(
                code="currency_required",
                message="Currency code is required.",
                severity=IssueSeverity.error,
                field="currency",
            )
        )

    if invoice.invoice_total is None:
        issues.append(
            ValidationIssue(
                code="invoice_total_required",
                message="Invoice total amount is required.",
                severity=IssueSeverity.error,
                field="invoice_total",
            )
        )
    elif invoice.invoice_total <= Decimal("0"):
        issues.append(
            ValidationIssue(
                code="invoice_total_non_positive",
                message="Invoice total must be a positive amount.",
                severity=IssueSeverity.error,
                field="invoice_total",
            )
        )

    # 5. Date order check (due_date cannot be earlier than invoice_date)
    if invoice.invoice_date and invoice.due_date:
        inv_date = _parse_date(invoice.invoice_date)
        due_date = _parse_date(invoice.due_date)
        if inv_date and due_date and due_date < inv_date:
            issues.append(
                ValidationIssue(
                    code="invalid_date_order",
                    message=(
                        f"Invoice due date ({due_date}) cannot precede "
                        f"invoice date ({inv_date})."
                    ),
                    severity=IssueSeverity.error,
                    field="due_date",
                )
            )

    # 6. Total reconciliation check (subtotal + total_tax vs invoice_total)
    if (
        invoice.subtotal is not None
        and invoice.total_tax is not None
        and invoice.invoice_total is not None
    ):
        expected_total = invoice.subtotal + invoice.total_tax
        if abs(expected_total - invoice.invoice_total) > TOLERANCE:
            issues.append(
                ValidationIssue(
                    code="invoice_total_mismatch",
                    message=(
                        f"Calculated total ({expected_total}) does not reconcile with "
                        f"invoice total ({invoice.invoice_total}) within EUR {TOLERANCE}."
                    ),
                    severity=IssueSeverity.error,
                    field="invoice_total",
                )
            )

    # 7. Duplicate invoice detection
    if existing_invoices and invoice.vendor_name and invoice.invoice_number:
        v_name = invoice.vendor_name.strip().lower()
        inv_num = invoice.invoice_number.strip().lower()
        normalized_existing = {
            (v.strip().lower(), num.strip().lower()) for v, num in existing_invoices
        }
        if (v_name, inv_num) in normalized_existing:
            issues.append(
                ValidationIssue(
                    code="duplicate_invoice",
                    message=(
                        f"Invoice '{invoice.invoice_number}' from vendor '{invoice.vendor_name}' "
                        "already exists in the records."
                    ),
                    severity=IssueSeverity.error,
                    field="invoice_number",
                )
            )

    # 8. Warnings: missing purchase order
    if not invoice.purchase_order or not invoice.purchase_order.strip():
        issues.append(
            ValidationIssue(
                code="purchase_order_missing",
                message="Purchase order is missing.",
                severity=IssueSeverity.warning,
                field="purchase_order",
            )
        )

    # 9. Warnings: low primary extraction confidence
    if invoice.confidence is not None and invoice.confidence < CONFIDENCE_THRESHOLD:
        issues.append(
            ValidationIssue(
                code="low_confidence",
                message=(
                    f"Primary extraction confidence ({invoice.confidence:.2f}) "
                    f"is below warning threshold ({CONFIDENCE_THRESHOLD:.2f})."
                ),
                severity=IssueSeverity.warning,
                field="confidence",
            )
        )

    return issues


def validate_receipt(receipt: ReceiptData) -> list[ValidationIssue]:
    """Pure deterministic validation of a receipt against Northstar policy.

    Errors (block approval):
    - missing merchant name
    - missing transaction date
    - missing currency
    - missing or non-positive total
    - missing VAT total (total_tax)
    - total reconciliation mismatch over EUR 0.01 (subtotal + total_tax != total)

    Warnings:
    - low primary extraction confidence (< 0.80)
    """
    issues: list[ValidationIssue] = []

    # 1. Merchant name
    if not receipt.merchant_name or not receipt.merchant_name.strip():
        issues.append(
            ValidationIssue(
                code="merchant_name_required",
                message="Merchant name is required on receipts.",
                severity=IssueSeverity.error,
                field="merchant_name",
            )
        )

    # 2. Transaction date
    if not receipt.transaction_date:
        issues.append(
            ValidationIssue(
                code="transaction_date_required",
                message="Transaction date is required on receipts.",
                severity=IssueSeverity.error,
                field="transaction_date",
            )
        )

    # 3. Currency
    if not receipt.currency or not receipt.currency.strip():
        issues.append(
            ValidationIssue(
                code="currency_required",
                message="Currency code is required on receipts.",
                severity=IssueSeverity.error,
                field="currency",
            )
        )

    # 4. Total and positive total
    if receipt.total is None:
        issues.append(
            ValidationIssue(
                code="total_required",
                message="Total amount is required on receipts.",
                severity=IssueSeverity.error,
                field="total",
            )
        )
    elif receipt.total <= Decimal("0"):
        issues.append(
            ValidationIssue(
                code="total_non_positive",
                message="Total amount on receipt must be positive.",
                severity=IssueSeverity.error,
                field="total",
            )
        )

    # 5. VAT total
    if receipt.total_tax is None:
        issues.append(
            ValidationIssue(
                code="total_tax_required",
                message="VAT total is required on receipts.",
                severity=IssueSeverity.error,
                field="total_tax",
            )
        )

    # 6. Reconciliation: subtotal + total_tax vs total
    if (
        receipt.subtotal is not None
        and receipt.total_tax is not None
        and receipt.total is not None
    ):
        expected_total = receipt.subtotal + receipt.total_tax
        if abs(expected_total - receipt.total) > TOLERANCE:
            issues.append(
                ValidationIssue(
                    code="receipt_total_mismatch",
                    message=(
                        f"Calculated receipt total ({expected_total}) does not reconcile with "
                        f"total ({receipt.total}) within EUR {TOLERANCE}."
                    ),
                    severity=IssueSeverity.error,
                    field="total",
                )
            )

    # 7. Low confidence warning
    if receipt.confidence is not None and receipt.confidence < CONFIDENCE_THRESHOLD:
        issues.append(
            ValidationIssue(
                code="low_confidence",
                message=(
                    f"Primary extraction confidence ({receipt.confidence:.2f}) "
                    f"is below warning threshold ({CONFIDENCE_THRESHOLD:.2f})."
                ),
                severity=IssueSeverity.warning,
                field="confidence",
            )
        )

    return issues


__all__ = [
    "CONFIDENCE_THRESHOLD",
    "NORTHSTAR_CUSTOMER_NAME",
    "NORTHSTAR_CUSTOMER_VAT_ID",
    "TOLERANCE",
    "IssueSeverity",
    "ValidationIssue",
    "validate_invoice",
    "validate_receipt",
]
