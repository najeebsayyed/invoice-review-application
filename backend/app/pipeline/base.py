"""Base components and context models for document processing pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.invoice import InvoiceData
from app.schemas.receipt import ReceiptData


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
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


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
            current_ctx = step.run(current_ctx)
        return current_ctx


__all__ = [
    "Pipeline",
    "PipelineContext",
    "PipelineStep",
]
