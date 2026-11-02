"""Document extraction pipeline step routed by classified document kind.

Supports:
- Document kind routing (invoice -> prebuilt-invoice, receipt -> prebuilt-receipt)
- Primary Document Intelligence extraction
- Secondary LLM extraction for missing field fill
- Deterministic merging with provenance and conflict tracking
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import IO, Any, Protocol, runtime_checkable

from app.pipeline.base import PipelineContext
from app.pipeline.classification import DocumentKind
from app.schemas.invoice import InvoiceData
from app.schemas.receipt import ReceiptData
from app.services.document_intelligence_service import DocumentIntelligenceService
from app.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)


@runtime_checkable
class ExtractionService(Protocol):
    """Protocol for services providing structured invoice and receipt extraction."""

    def process_invoice(self, document_source: str | Path | bytes | IO[bytes]) -> InvoiceData:
        """Extract structured invoice data from document source."""
        ...

    def process_receipt(self, document_source: str | Path | bytes | IO[bytes]) -> ReceiptData:
        """Extract structured receipt data from document source."""
        ...


def merge_invoice_data(
    primary: InvoiceData,
    secondary: InvoiceData | None,
) -> tuple[InvoiceData, dict[str, str], dict[str, dict[str, Any]]]:
    """Deterministically merge primary Document Intelligence with secondary LLM extraction.

    - Keeps Document Intelligence values primary.
    - Fills missing fields from secondary.
    - Exposes provenance ('primary' vs 'secondary') for each field.
    - Exposes conflicts where both had different non-empty values.
    """
    if secondary is None:
        provenance = {
            k: "primary"
            for k, v in primary.model_dump().items()
            if v is not None and k != "field_confidences"
        }
        return primary, provenance, {}

    merged_dict = primary.model_dump()
    secondary_dict = secondary.model_dump()
    provenance: dict[str, str] = {}
    conflicts: dict[str, dict[str, Any]] = {}

    scalar_fields = [
        "vendor_name",
        "vendor_vat_id",
        "vendor_address",
        "vendor_address_recipient",
        "customer_name",
        "customer_id",
        "customer_vat_id",
        "customer_address",
        "customer_address_recipient",
        "billing_address",
        "billing_address_recipient",
        "shipping_address",
        "shipping_address_recipient",
        "invoice_number",
        "invoice_date",
        "due_date",
        "purchase_order",
        "payment_term",
        "subtotal",
        "total_tax",
        "invoice_total",
        "amount_due",
        "currency",
    ]

    for field in scalar_fields:
        p_val = getattr(primary, field)
        s_val = getattr(secondary, field)

        if p_val is not None and str(p_val).strip() != "":
            merged_dict[field] = p_val
            provenance[field] = "primary"
            if s_val is not None and str(s_val).strip() != "" and str(p_val) != str(s_val):
                conflicts[field] = {"primary": p_val, "secondary": s_val}
        elif s_val is not None and str(s_val).strip() != "":
            merged_dict[field] = s_val
            provenance[field] = "secondary"
        else:
            merged_dict[field] = None

    # Line items and tax details: fallback to secondary if primary is empty
    if not primary.items and secondary.items:
        merged_dict["items"] = secondary_dict["items"]
        provenance["items"] = "secondary"
    else:
        merged_dict["items"] = primary.model_dump()["items"]
        if primary.items:
            provenance["items"] = "primary"

    if not primary.tax_details and secondary.tax_details:
        merged_dict["tax_details"] = secondary_dict["tax_details"]
        provenance["tax_details"] = "secondary"
    else:
        merged_dict["tax_details"] = primary.model_dump()["tax_details"]
        if primary.tax_details:
            provenance["tax_details"] = "primary"

    merged = InvoiceData(**merged_dict)
    return merged, provenance, conflicts


def merge_receipt_data(
    primary: ReceiptData,
    secondary: ReceiptData | None,
) -> tuple[ReceiptData, dict[str, str], dict[str, dict[str, Any]]]:
    """Deterministically merge primary Document Intelligence with secondary LLM extraction."""
    if secondary is None:
        provenance = {
            k: "primary"
            for k, v in primary.model_dump().items()
            if v is not None and k != "field_confidences"
        }
        return primary, provenance, {}

    merged_dict = primary.model_dump()
    secondary_dict = secondary.model_dump()
    provenance: dict[str, str] = {}
    conflicts: dict[str, dict[str, Any]] = {}

    scalar_fields = [
        "merchant_name",
        "merchant_address",
        "merchant_phone_number",
        "transaction_date",
        "transaction_time",
        "subtotal",
        "total_tax",
        "tip",
        "total",
        "currency",
        "receipt_type",
        "country_region",
    ]

    for field in scalar_fields:
        p_val = getattr(primary, field)
        s_val = getattr(secondary, field)

        if p_val is not None and str(p_val).strip() != "":
            merged_dict[field] = p_val
            provenance[field] = "primary"
            if s_val is not None and str(s_val).strip() != "" and str(p_val) != str(s_val):
                conflicts[field] = {"primary": p_val, "secondary": s_val}
        elif s_val is not None and str(s_val).strip() != "":
            merged_dict[field] = s_val
            provenance[field] = "secondary"
        else:
            merged_dict[field] = None

    if not primary.items and secondary.items:
        merged_dict["items"] = secondary_dict["items"]
        provenance["items"] = "secondary"
    else:
        merged_dict["items"] = primary.model_dump()["items"]
        if primary.items:
            provenance["items"] = "primary"

    if not primary.tax_details and secondary.tax_details:
        merged_dict["tax_details"] = secondary_dict["tax_details"]
        provenance["tax_details"] = "secondary"
    else:
        merged_dict["tax_details"] = primary.model_dump()["tax_details"]
        if primary.tax_details:
            provenance["tax_details"] = "primary"

    merged = ReceiptData(**merged_dict)
    return merged, provenance, conflicts


class ExtractionStep:
    """Pipeline step that routes document extraction by document kind."""

    name: str = "extraction"

    def __init__(
        self,
        extractor: ExtractionService | None = None,
        secondary_extractor: ExtractionService | None = None,
        enable_secondary_fallback: bool = True,
    ) -> None:
        self._extractor = extractor or DocumentIntelligenceService()
        # By default, use OpenAIService for secondary missing-field filling if enabled
        self._secondary_extractor: ExtractionService | None = None
        if enable_secondary_fallback:
            if secondary_extractor is not None:
                self._secondary_extractor = secondary_extractor
            else:
                try:
                    self._secondary_extractor = OpenAIService()
                except Exception as e:
                    logger.debug("Secondary LLM extractor unavailable: %s", e)
                    self._secondary_extractor = None

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute extraction routed by the context document kind."""
        if not ctx.classification:
            raise ValueError(
                "Document must be classified before extraction. Run ClassificationStep first."
            )

        doc_kind = ctx.classification.document_kind
        logger.info(
            "Routing extraction for '%s' as document kind: %s",
            ctx.document_path.name,
            doc_kind,
        )

        if doc_kind == DocumentKind.receipt:
            primary_receipt = self._extractor.process_receipt(ctx.document_path)
            secondary_receipt = (
                self._secondary_extractor.process_receipt(ctx.document_path)
                if self._secondary_extractor
                else None
            )
            merged_receipt, prov, conf = merge_receipt_data(primary_receipt, secondary_receipt)
            meta = dict(ctx.metadata)
            meta["provenance"] = prov
            meta["conflicts"] = conf
            return ctx.model_copy(
                update={
                    "receipt_data": merged_receipt,
                    "metadata": meta,
                }
            )

        # Invoice route
        primary_invoice = self._extractor.process_invoice(ctx.document_path)
        secondary_invoice = (
            self._secondary_extractor.process_invoice(ctx.document_path)
            if self._secondary_extractor
            else None
        )
        merged_invoice, prov, conf = merge_invoice_data(primary_invoice, secondary_invoice)
        meta = dict(ctx.metadata)
        meta["provenance"] = prov
        meta["conflicts"] = conf
        return ctx.model_copy(
            update={
                "invoice_data": merged_invoice,
                "metadata": meta,
            }
        )


__all__ = [
    "ExtractionService",
    "ExtractionStep",
    "merge_invoice_data",
    "merge_receipt_data",
]
