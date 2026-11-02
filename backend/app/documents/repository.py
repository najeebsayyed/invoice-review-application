"""SQLAlchemy repository for document persistence and queries."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.accounting.schemas import AccountingCoding
from app.documents.models import DocumentRecord
from app.documents.schemas import DocumentStatus
from app.invoices.validation import ValidationIssue


def normalize_name(name: str | None) -> str | None:
    """Normalize vendor or merchant name for deterministic duplicate lookup."""
    if not name:
        return None
    return " ".join(name.strip().lower().split())


def normalize_invoice_number(number: str | None) -> str | None:
    """Normalize invoice number for deterministic duplicate lookup."""
    if not number:
        return None
    return "".join(number.strip().lower().split())


class DocumentRepository:
    """Repository managing document persistence, state transitions, and duplicate detection."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_processing(
        self,
        *,
        record_id: str,
        original_filename: str,
        stored_filename: str,
        content_type: str,
    ) -> DocumentRecord:
        """Create a placeholder document record with 'processing' status."""
        record = DocumentRecord(
            id=record_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=content_type,
            status="processing",
            issues=[],
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get(self, record_id: str) -> DocumentRecord | None:
        """Retrieve a document record by ID."""
        return self.session.get(DocumentRecord, record_id)

    def list(self) -> list[DocumentRecord]:
        """List all document records ordered by creation date descending."""
        statement = select(DocumentRecord).order_by(
            DocumentRecord.created_at.desc(), DocumentRecord.id.desc()
        )
        return list(self.session.scalars(statement))

    def save_result(
        self,
        record_id: str,
        *,
        status: DocumentStatus,
        classification: dict[str, Any] | None,
        extraction: dict[str, Any] | None,
        validation: dict[str, Any] | None,
        gl_suggestion: dict[str, Any] | None,
        review_data: dict[str, Any] | None = None,
        accounting_coding: AccountingCoding | None,
        issues: list[ValidationIssue],
        vendor_name: str | None = None,
        invoice_number: str | None = None,
    ) -> DocumentRecord:
        """Save completed pipeline processing outputs to the record."""
        record = self._require(record_id)
        record.status = status
        record.classification = classification
        record.extraction = extraction
        record.validation = validation
        record.gl_suggestion = gl_suggestion
        record.review_data = review_data
        record.accounting_coding = (
            accounting_coding.model_dump(mode="json") if accounting_coding is not None else None
        )
        record.issues = [issue.model_dump(mode="json") for issue in issues]
        record.error_message = None
        record.normalized_vendor_name = normalize_name(vendor_name)
        record.normalized_invoice_number = normalize_invoice_number(invoice_number)
        self._commit(record)
        return record

    def select_gl_account(self, record_id: str, gl_account_code: str) -> DocumentRecord:
        """Update reviewer-selected GL account code on the record."""
        record = self._require(record_id)
        coding = AccountingCoding.model_validate(record.accounting_coding or {})
        coding.selected_gl_account_code = gl_account_code
        coding.overridden = bool(
            coding.suggestion and coding.suggestion.gl_account_code != gl_account_code
        )
        record.accounting_coding = coding.model_dump(mode="json")
        self._commit(record)
        return record

    def save_failure(self, record_id: str, message: str) -> DocumentRecord:
        """Mark record as failed with an error message."""
        record = self._require(record_id)
        record.status = "failed"
        record.error_message = message
        self._commit(record)
        return record

    def set_status(self, record_id: str, status: DocumentStatus) -> DocumentRecord:
        """Transition record status."""
        record = self._require(record_id)
        record.status = status
        self._commit(record)
        return record

    def delete(self, record_id: str) -> None:
        """Delete record from database."""
        record = self._require(record_id)
        self.session.delete(record)
        self.session.commit()

    def duplicate_exists(
        self,
        vendor_name: str,
        invoice_number: str,
        *,
        exclude_id: str | None = None,
    ) -> bool:
        """Check if an active document already exists with matching vendor and invoice number."""
        statement: Select[tuple[DocumentRecord]] = select(DocumentRecord).where(
            DocumentRecord.normalized_vendor_name == normalize_name(vendor_name),
            DocumentRecord.normalized_invoice_number == normalize_invoice_number(invoice_number),
            DocumentRecord.status != "rejected",
        )
        if exclude_id is not None:
            statement = statement.where(DocumentRecord.id != exclude_id)
        return self.session.scalar(statement.limit(1)) is not None

    def get_existing_invoices(self, exclude_id: str | None = None) -> list[tuple[str, str]]:
        """Return list of (vendor_name, invoice_number) for all active invoices in the ledger."""
        statement = select(
            DocumentRecord.normalized_vendor_name,
            DocumentRecord.normalized_invoice_number,
        ).where(
            DocumentRecord.normalized_vendor_name.is_not(None),
            DocumentRecord.normalized_invoice_number.is_not(None),
            DocumentRecord.status != "rejected",
        )
        if exclude_id is not None:
            statement = statement.where(DocumentRecord.id != exclude_id)
        results = self.session.execute(statement).all()
        return [(str(row[0]), str(row[1])) for row in results if row[0] and row[1]]

    def _require(self, record_id: str) -> DocumentRecord:
        record = self.get(record_id)
        if record is None:
            raise KeyError(record_id)
        return record

    def _commit(self, record: DocumentRecord) -> None:
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
