"""LLM-backed document classification pipeline step for invoices and receipts."""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path
from typing import IO

from pydantic import BaseModel, ConfigDict, Field

from app.pipeline.base import PipelineContext
from app.services.openai_service import OpenAIService, OpenAISettings

logger = logging.getLogger(__name__)


class DocumentKind(StrEnum):
    """Supported document categories for financial review."""

    invoice = "invoice"
    receipt = "receipt"


class DocumentClassification(BaseModel):
    """Structured classification output produced by DocumentClassifier."""

    document_kind: DocumentKind
    confidence: float = Field(
        description="Confidence score of classification between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = Field(
        description="Concise reasoning explaining why this document type was chosen",
    )

    model_config = ConfigDict(extra="ignore")

    @property
    def document_type(self) -> str:
        """Convenience alias returning the document kind string value."""
        return self.document_kind.value


class DocumentClassifier:
    """LLM-backed classifier that inspects an uploaded file to decide invoice vs receipt."""

    def __init__(
        self,
        openai_service: OpenAIService | None = None,
        settings: OpenAISettings | None = None,
    ) -> None:
        self._openai_service = openai_service or OpenAIService(
            api_key=settings.openai_api_key if settings else None,
            model=settings.openai_model if settings else None,
        )

    def run(self, document_source: str | Path | bytes | IO[bytes]) -> DocumentClassification:
        """Classify an uploaded financial document into invoice or receipt with reasoning."""
        doc_content, _ = self._openai_service._prepare_document_content(document_source)

        prompt_text = (
            "You are an expert document classifier for an accounts payable system. "
            "Analyze the document and determine whether it is an 'invoice' or a 'receipt'. "
            "Invoices are billed requests for payment containing vendor, customer details, "
            "and an invoice number. Receipts record already paid retail/fuel/expense purchases. "
            "Return the document_kind ('invoice' or 'receipt'), your confidence (0.0 to 1.0), "
            "and a clear, concise reasoning sentence."
        )

        response = self._openai_service._client.responses.parse(
            model=self._openai_service.model,
            text_format=DocumentClassification,
            input=[
                {
                    "role": "user",
                    "content": [
                        doc_content,
                        {"type": "input_text", "text": prompt_text},
                    ],
                }
            ],
        )

        return response.output_parsed


class ClassificationStep:
    """First pipeline step: classifies the document as an invoice or receipt via LLM."""

    name: str = "classification"

    def __init__(self, classifier: DocumentClassifier | None = None) -> None:
        self._classifier = classifier or DocumentClassifier()

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Classify document and return an updated copy of the pipeline context."""
        logger.info("Executing classification step for document: %s", ctx.document_path)
        classification = self._classifier.run(ctx.document_path)
        return ctx.model_copy(update={"classification": classification})


__all__ = [
    "ClassificationStep",
    "DocumentClassification",
    "DocumentClassifier",
    "DocumentKind",
]
