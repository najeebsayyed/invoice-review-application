"""Document service orchestrating uploads, pipeline execution, and review decisions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.accounting.catalog import get_gl_account
from app.accounting.schemas import AccountingCoding, AccountingSuggestion
from app.documents.models import DocumentRecord
from app.documents.repository import DocumentRepository
from app.documents.schemas import (
    DocumentStatus,
    FieldCorrectionRequest,
    ReviewData,
    ReviewLineItem,
)
from app.invoices.validation import (
    IssueSeverity,
    ValidationIssue,
    validate_invoice,
    validate_receipt,
)
from app.pipeline import GlSuggestion, create_pipeline
from app.schemas.invoice import InvoiceData
from app.schemas.receipt import ReceiptData
from app.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)


class DocumentNotFoundError(RuntimeError):
    """Document record does not exist or does not belong to the requesting workspace."""

    pass


class DocumentProcessingError(RuntimeError):
    """Unexpected failure during document pipeline processing."""

    pass


class DocumentContentError(RuntimeError):
    """Uploaded document contains unsupported format or content."""

    pass


class DocumentReviewConflictError(RuntimeError):
    """Operation conflicts with current document state or unfulfilled prerequisites."""

    pass


def _accounting_from_suggestion(suggestion: GlSuggestion | None) -> AccountingCoding:
    """Build AccountingCoding model from pipeline GlSuggestion."""
    if suggestion is None:
        return AccountingCoding(error_message="No GL suggestion was produced.")
    account = get_gl_account(suggestion.account_code)
    if account is None:
        return AccountingCoding(error_message="Suggested GL account is not in the catalog.")
    coded = AccountingSuggestion(
        gl_account_code=suggestion.account_code.value,
        category=account.name,
        rationale=suggestion.reasoning,
        confidence=suggestion.confidence,
    )
    return AccountingCoding(
        suggestion=coded,
        selected_gl_account_code=coded.gl_account_code,
        overridden=False,
    )


def status_for_issues(issues: list[ValidationIssue]) -> DocumentStatus:
    """Determine document review readiness based on validation findings."""
    has_errors = any(issue.severity == IssueSeverity.error for issue in issues)
    return "needs_review" if has_errors else "ready"


class DocumentService:
    """Orchestrates document uploads, pipeline runs, and review lifecycle transitions."""

    def __init__(
        self,
        *,
        repository: DocumentRepository,
        upload_dir: Path,
        expected_customer_name: str,
        expected_customer_vat_id: str,
        min_confidence: float,
    ) -> None:
        self.repository = repository
        self.upload_dir = upload_dir
        self.expected_customer_name = expected_customer_name
        self.expected_customer_vat_id = expected_customer_vat_id
        self.min_confidence = min_confidence

    def process(
        self,
        *,
        workspace_id: str,
        original_filename: str,
        content_type: str,
        content: bytes,
        suffix: str,
    ) -> DocumentRecord:
        """Process an uploaded document through storage, pipeline, and workspace persistence."""
        record_id = str(uuid4())
        stored_filename = f"{record_id}{suffix}"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self.upload_dir / stored_filename
        stored_path.write_bytes(content)

        self.repository.create_processing(
            record_id=record_id,
            workspace_id=workspace_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=content_type,
        )

        try:
            existing_invoices = self.repository.get_existing_invoices(
                workspace_id=workspace_id, exclude_id=record_id
            )
            pipeline = create_pipeline(existing_invoices=existing_invoices)
            context = pipeline.run_file(stored_path)
        except Exception as error:
            message = str(error) or error.__class__.__name__
            logger.exception("Document pipeline processing failed for %s", original_filename)
            self.repository.save_failure(record_id, message)
            raise DocumentProcessingError(message) from error

        issues = context.validation_issues
        accounting_coding = _accounting_from_suggestion(context.gl_suggestion)

        # Extract normalized keys and ReviewData projection
        vendor_name: str | None = None
        invoice_number: str | None = None
        review_data: ReviewData | None = None

        prov = context.metadata.get("provenance", {})
        conf = context.metadata.get("conflicts", {})

        if context.invoice_data:
            inv = context.invoice_data
            vendor_name = inv.vendor_name
            invoice_number = inv.invoice_number
            review_data = ReviewData(
                document_type="invoice",
                vendor_name=inv.vendor_name,
                vendor_vat_id=inv.vendor_vat_id,
                customer_name=inv.customer_name,
                customer_vat_id=inv.customer_vat_id,
                invoice_number=inv.invoice_number,
                purchase_order=inv.purchase_order,
                invoice_date=str(inv.invoice_date) if inv.invoice_date else None,
                due_date=str(inv.due_date) if inv.due_date else None,
                currency=inv.currency,
                subtotal=inv.subtotal,
                total_tax=inv.total_tax,
                invoice_total=inv.invoice_total,
                amount_due=inv.amount_due,
                line_items=[
                    ReviewLineItem(
                        description=item.description,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        amount=item.amount,
                    )
                    for item in inv.items
                ],
                provenance=prov,
                conflicts=conf,
            )
        elif context.receipt_data:
            rec = context.receipt_data
            vendor_name = rec.merchant_name
            review_data = ReviewData(
                document_type="receipt",
                expense_category=rec.receipt_type,
                vendor_name=rec.merchant_name,
                invoice_date=str(rec.transaction_date) if rec.transaction_date else None,
                currency=rec.currency,
                subtotal=rec.subtotal,
                total_tax=rec.total_tax,
                invoice_total=rec.total,
                amount_due=rec.total,
                line_items=[
                    ReviewLineItem(
                        description=item.description,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        amount=item.total_price,
                    )
                    for item in rec.items
                ],
                provenance=prov,
                conflicts=conf,
            )

        return self.repository.save_result(
            record_id,
            status=status_for_issues(issues),
            classification=(
                context.classification.model_dump(mode="json")
                if context.classification
                else None
            ),
            extraction=(
                context.extracted_data.model_dump(mode="json")
                if context.extracted_data
                else None
            ),
            validation={
                "findings": [issue.model_dump(mode="json") for issue in issues],
                "has_errors": any(issue.severity == IssueSeverity.error for issue in issues),
            },
            gl_suggestion=(
                context.gl_suggestion.model_dump(mode="json")
                if context.gl_suggestion
                else None
            ),
            review_data=review_data.model_dump(mode="json") if review_data else None,
            accounting_coding=accounting_coding,
            issues=issues,
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            workspace_id=workspace_id,
        )

    def get(self, record_id: str, workspace_id: str) -> DocumentRecord:
        """Fetch a document record scoped to the requesting workspace or raise 404."""
        record = self.repository.get(record_id, workspace_id=workspace_id)
        if record is None:
            raise DocumentNotFoundError(f"Document {record_id} was not found.")
        return record

    def list(
        self,
        *,
        workspace_id: str,
        status: DocumentStatus | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[DocumentRecord]:
        """List document records matching search, status filter, and workspace criteria."""
        return self.repository.list(
            workspace_id=workspace_id,
            status=status,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )

    def get_stats(self, *, workspace_id: str) -> dict[str, Any]:
        """Retrieve aggregated KPI dashboard statistics across workspace reviews."""
        return self.repository.get_stats(workspace_id=workspace_id)

    def delete(self, record_id: str, workspace_id: str) -> None:
        """Delete document record and associated file on disk within workspace."""
        record = self.get(record_id, workspace_id=workspace_id)
        stored_path = self.upload_dir / Path(record.stored_filename).name
        self.repository.delete(record_id, workspace_id=workspace_id)
        stored_path.unlink(missing_ok=True)

    def select_gl_account(
        self, record_id: str, workspace_id: str, gl_account_code: str
    ) -> DocumentRecord:
        """Set user-selected GL account code on the document within workspace."""
        record = self.get(record_id, workspace_id=workspace_id)
        if record.status in {"approved", "rejected"}:
            raise DocumentReviewConflictError("A decided document cannot be modified.")
        if get_gl_account(gl_account_code) is None:
            raise ValueError(f"Unknown GL account code: '{gl_account_code}'")
        return self.repository.select_gl_account(
            record_id, gl_account_code, workspace_id=workspace_id
        )

    def decide(self, record_id: str, workspace_id: str, decision: str) -> DocumentRecord:
        """Record human review approval or rejection within workspace."""
        record = self.get(record_id, workspace_id=workspace_id)
        if record.status in {"approved", "rejected"}:
            raise DocumentReviewConflictError(
                "This document has already received a final decision."
            )
        if record.status in {"processing", "failed"}:
            raise DocumentReviewConflictError("Only completed reviews can receive a decision.")

        if decision == "approved":
            has_errors = any(
                item.get("severity") == "error" for item in (record.issues or [])
            )
            if has_errors:
                raise DocumentReviewConflictError(
                    "Cannot approve document with active validation errors."
                )
            coding = AccountingCoding.model_validate(record.accounting_coding or {})
            if (
                not coding.selected_gl_account_code
                or get_gl_account(coding.selected_gl_account_code) is None
            ):
                raise DocumentReviewConflictError(
                    "A valid Northstar GL account must be selected before approval."
                )
        elif decision != "rejected":
            raise ValueError(f"Unsupported decision: '{decision}'")

        return self.repository.set_status(record_id, decision, workspace_id=workspace_id)  # type: ignore[arg-type]

    def apply_corrections(
        self, record_id: str, workspace_id: str, corrections: FieldCorrectionRequest
    ) -> DocumentRecord:
        """Apply reviewer field corrections and recompute deterministic policy issues."""
        record = self.get(record_id, workspace_id=workspace_id)
        if record.status in {"approved", "rejected"}:
            raise DocumentReviewConflictError(
                f"Cannot correct document in final '{record.status}' status."
            )
        if not record.review_data:
            raise DocumentReviewConflictError("Document has no review data to correct.")

        review = ReviewData.model_validate(record.review_data)
        corrections_dict = corrections.model_dump(exclude_unset=True)

        for field, new_val in corrections_dict.items():
            if new_val is not None:
                setattr(review, field, new_val)
                review.provenance[field] = "user"

        if review.document_type == "receipt":
            rec_data = ReceiptData(
                merchant_name=review.vendor_name,
                transaction_date=review.invoice_date,
                subtotal=review.subtotal,
                total_tax=review.total_tax,
                total=review.invoice_total,
                currency=review.currency,
                receipt_type=review.expense_category,
            )
            new_issues = validate_receipt(rec_data)
        else:
            existing_invoices = self.repository.get_existing_invoices(
                workspace_id=workspace_id, exclude_id=record_id
            )
            inv_data = InvoiceData(
                vendor_name=review.vendor_name,
                vendor_vat_id=review.vendor_vat_id,
                customer_name=review.customer_name,
                customer_vat_id=review.customer_vat_id,
                invoice_number=review.invoice_number,
                invoice_date=review.invoice_date,
                due_date=review.due_date,
                purchase_order=review.purchase_order,
                currency=review.currency,
                subtotal=review.subtotal,
                total_tax=review.total_tax,
                invoice_total=review.invoice_total,
            )
            new_issues = validate_invoice(inv_data, existing_invoices=existing_invoices)

        new_status = status_for_issues(new_issues)
        return self.repository.save_corrections(
            record_id,
            status=new_status,
            review_data=review.model_dump(mode="json"),
            issues=new_issues,
            vendor_name=review.vendor_name,
            invoice_number=review.invoice_number,
            workspace_id=workspace_id,
        )

    def draft_correction_email(self, record_id: str, workspace_id: str) -> tuple[str, str]:
        """Draft a formal supplier correction request email using Azure OpenAI."""
        record = self.get(record_id, workspace_id=workspace_id)
        review = (
            ReviewData.model_validate(record.review_data)
            if record.review_data
            else None
        )

        vendor = review.vendor_name if review else record.normalized_vendor_name
        inv_num = review.invoice_number if review else record.normalized_invoice_number
        inv_date = review.invoice_date if review else None
        currency = review.currency if review else "EUR"
        total = review.invoice_total if review else None

        openai_service = OpenAIService()
        return openai_service.draft_correction_email(
            vendor_name=vendor,
            invoice_number=inv_num,
            invoice_date=inv_date,
            currency=currency,
            invoice_total=total,
            issues=record.issues or [],
        )
