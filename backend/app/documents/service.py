"""Document service orchestrating uploads, pipeline execution, and review decisions."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.accounting.catalog import get_gl_account
from app.accounting.schemas import AccountingCoding, AccountingSuggestion
from app.documents.models import DocumentRecord
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentStatus
from app.invoices.validation import IssueSeverity, ValidationIssue
from app.pipeline import GlSuggestion, create_pipeline

logger = logging.getLogger(__name__)


class DocumentNotFoundError(RuntimeError):
    """Document record does not exist."""

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
        original_filename: str,
        content_type: str,
        content: bytes,
        suffix: str,
    ) -> DocumentRecord:
        """Process an uploaded document through storage, the pipeline, and SQLite persistence."""
        record_id = str(uuid4())
        stored_filename = f"{record_id}{suffix}"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self.upload_dir / stored_filename
        stored_path.write_bytes(content)

        self.repository.create_processing(
            record_id=record_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=content_type,
        )

        try:
            existing_invoices = self.repository.get_existing_invoices(exclude_id=record_id)
            pipeline = create_pipeline(existing_invoices=existing_invoices)
            context = pipeline.run_file(stored_path)
        except Exception as error:
            message = str(error) or error.__class__.__name__
            logger.exception("Document pipeline processing failed for %s", original_filename)
            self.repository.save_failure(record_id, message)
            raise DocumentProcessingError(message) from error

        issues = context.validation_issues
        accounting_coding = _accounting_from_suggestion(context.gl_suggestion)

        # Extract normalized keys for duplicate detection
        vendor_name: str | None = None
        invoice_number: str | None = None
        if context.invoice_data:
            vendor_name = context.invoice_data.vendor_name
            invoice_number = context.invoice_data.invoice_number
        elif context.receipt_data:
            vendor_name = context.receipt_data.merchant_name

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
            accounting_coding=accounting_coding,
            issues=issues,
            vendor_name=vendor_name,
            invoice_number=invoice_number,
        )

    def get(self, record_id: str) -> DocumentRecord:
        """Fetch a document record or raise DocumentNotFoundError."""
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError(f"Document {record_id} was not found.")
        return record

    def delete(self, record_id: str) -> None:
        """Delete document record and associated file on disk."""
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError(f"Document {record_id} was not found.")
        stored_path = self.upload_dir / Path(record.stored_filename).name
        self.repository.delete(record_id)
        stored_path.unlink(missing_ok=True)

    def select_gl_account(self, record_id: str, gl_account_code: str) -> DocumentRecord:
        """Set user-selected GL account code on the document."""
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError(f"Document {record_id} was not found.")
        if record.status in {"approved", "rejected"}:
            raise DocumentReviewConflictError("A decided document cannot be modified.")
        if get_gl_account(gl_account_code) is None:
            raise ValueError(f"Unknown GL account code: '{gl_account_code}'")
        return self.repository.select_gl_account(record_id, gl_account_code)

    def decide(self, record_id: str, decision: str) -> DocumentRecord:
        """Record human review approval or rejection."""
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError(f"Document {record_id} was not found.")
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

        return self.repository.set_status(record_id, decision)  # type: ignore[arg-type]
