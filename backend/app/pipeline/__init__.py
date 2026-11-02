"""Pipeline package for orchestrating end-to-end document processing."""

from __future__ import annotations

from collections.abc import Iterable

from app.pipeline.base import (
    Pipeline,
    PipelineContext,
    PipelineStep,
)
from app.pipeline.classification import (
    ClassificationStep,
    DocumentClassification,
    DocumentClassifier,
    DocumentKind,
)
from app.pipeline.extraction import (
    ExtractionService,
    ExtractionStep,
)
from app.pipeline.gl_categorization import (
    GlCategorizationStep,
    GlCategorizer,
    GlSuggestion,
)
from app.pipeline.validation import (
    ValidationStep,
)


def create_pipeline(
    classifier: DocumentClassifier | None = None,
    extractor: ExtractionService | None = None,
    categorizer: GlCategorizer | None = None,
    existing_invoices: Iterable[tuple[str, str]] | None = None,
) -> Pipeline:
    """Factory creating the standard Invoice Review pipeline.

    Steps in order:
    1. ClassificationStep (LLM-backed classifier)
    2. ExtractionStep (document-kind routed extraction & merge)
    3. ValidationStep (deterministic Northstar policy validation)
    4. GlCategorizationStep (suggested GL account from 10-account catalog)
    """
    return Pipeline(
        steps=[
            ClassificationStep(classifier=classifier),
            ExtractionStep(extractor=extractor),
            ValidationStep(existing_invoices=existing_invoices),
            GlCategorizationStep(categorizer=categorizer),
        ]
    )


__all__ = [
    "ClassificationStep",
    "DocumentClassification",
    "DocumentClassifier",
    "DocumentKind",
    "ExtractionService",
    "ExtractionStep",
    "GlCategorizationStep",
    "GlCategorizer",
    "GlSuggestion",
    "Pipeline",
    "PipelineContext",
    "PipelineStep",
    "ValidationStep",
    "create_pipeline",
]
