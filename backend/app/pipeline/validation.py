"""Pipeline step for validating extracted documents against Northstar policies."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from app.invoices.validation import (
    IssueSeverity,
    ValidationIssue,
    validate_invoice,
    validate_receipt,
)
from app.pipeline.base import PipelineContext
from app.pipeline.classification import DocumentKind

logger = logging.getLogger(__name__)


class ValidationStep:
    """Pipeline step that evaluates extracted documents against deterministic Northstar policies."""

    name: str = "validation"

    def __init__(self, existing_invoices: Iterable[tuple[str, str]] | None = None) -> None:
        self._existing_invoices = set(existing_invoices) if existing_invoices else set()

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Run policy validation based on document kind and update pipeline context."""
        logger.info("Executing validation step for document: %s", ctx.document_path.name)

        doc_kind = ctx.classification.document_kind if ctx.classification else None

        issues: list[ValidationIssue] = []

        if doc_kind == DocumentKind.receipt or ctx.receipt_data is not None:
            if ctx.receipt_data is None:
                raise ValueError("Receipt extraction data missing from pipeline context.")
            issues = validate_receipt(ctx.receipt_data)
        elif doc_kind == DocumentKind.invoice or ctx.invoice_data is not None:
            if ctx.invoice_data is None:
                raise ValueError("Invoice extraction data missing from pipeline context.")
            issues = validate_invoice(ctx.invoice_data, existing_invoices=self._existing_invoices)
        else:
            raise ValueError(
                "Cannot validate document: neither classification nor extracted data is present."
            )

        is_valid = not any(issue.severity == IssueSeverity.error for issue in issues)
        return ctx.model_copy(update={"validation_issues": issues, "is_valid": is_valid})


__all__ = [
    "ValidationStep",
]
