"""Documents package handling persistence, service orchestration, schemas, and API routes."""

from __future__ import annotations

from app.documents.models import DocumentRecord
from app.documents.repository import DocumentRepository
from app.documents.routes import router
from app.documents.schemas import DecisionRequest, DocumentResponse, DocumentStatus
from app.documents.service import (
    DocumentContentError,
    DocumentNotFoundError,
    DocumentProcessingError,
    DocumentReviewConflictError,
    DocumentService,
)

__all__ = [
    "DecisionRequest",
    "DocumentContentError",
    "DocumentNotFoundError",
    "DocumentProcessingError",
    "DocumentRecord",
    "DocumentRepository",
    "DocumentResponse",
    "DocumentReviewConflictError",
    "DocumentService",
    "DocumentStatus",
    "router",
]
