"""Base components and context models for document processing pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.accounting.schemas import GlSuggestion
from app.invoices.validation import IssueSeverity, ValidationIssue
from app.schemas.invoice import InvoiceData
from app.schemas.receipt import ReceiptData

if TYPE_CHECKING:
    from app.pipeline.classification import DocumentKind

logger = logging.getLogger(__name__)


@runtime_checkable
class PipelineStep(Protocol):
    """Protocol defining the interface for an executable pipeline step."""

    name: str

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute step logic on the context and return updated context."""
        ...


class PipelineContext(BaseModel):
    """Context and state container passed through each processing pipeline step."""

    document_path: Path
    classification: Any | None = None
    invoice_data: InvoiceData | None = None
    receipt_data: ReceiptData | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    gl_suggestion: GlSuggestion | None = None
    is_valid: bool = True
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def extracted_data(self) -> InvoiceData | ReceiptData | None:
        """Get whichever document model was extracted."""
        return self.invoice_data or self.receipt_data

    @property
    def document_kind(self) -> DocumentKind | None:
        """Get classified document kind if classification has run."""
        return self.classification.document_kind if self.classification else None

    @property
    def issue_codes(self) -> list[str]:
        """List of codes from recorded validation issues."""
        return [issue.code for issue in self.validation_issues]

    @property
    def has_errors(self) -> bool:
        """Check if any validation issue has error severity."""
        return any(issue.severity == IssueSeverity.error for issue in self.validation_issues)

    @property
    def has_warnings(self) -> bool:
        """Check if any validation issue has warning severity."""
        return any(issue.severity == IssueSeverity.warning for issue in self.validation_issues)


class Pipeline:
    """Sequential pipeline runner that coordinates execution of discrete processing steps."""

    def __init__(self, steps: list[PipelineStep] | None = None) -> None:
        self.steps: list[PipelineStep] = list(steps) if steps else []

    def add_step(self, step: PipelineStep) -> Pipeline:
        """Add a step to the pipeline execution chain."""
        self.steps.append(step)
        return self

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute all registered pipeline steps sequentially, threading context."""
        current_ctx = ctx
        for step in self.steps:
            logger.info("Running pipeline step: %s", step.name)
            current_ctx = step.run(current_ctx)
        return current_ctx

    def run_file(
        self,
        document_path: str | Path,
        metadata: dict[str, Any] | None = None,
    ) -> PipelineContext:
        """Convenience method to construct PipelineContext and execute pipeline."""
        path = Path(document_path)
        if not path.is_file():
            raise FileNotFoundError(f"Document file not found: {path}")
        initial_ctx = PipelineContext(
            document_path=path,
            metadata=metadata or {},
        )
        return self.run(initial_ctx)


__all__ = [
    "Pipeline",
    "PipelineContext",
    "PipelineStep",
]
