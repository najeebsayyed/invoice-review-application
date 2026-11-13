"""FastAPI HTTP routes for document management, processing, and review decisions."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.accounting.schemas import AccountingSelectionRequest
from app.config import AppConfig
from app.documents.models import DocumentRecord
from app.documents.repository import DocumentRepository
from app.documents.schemas import (
    CorrectionEmailResponse,
    DecisionRequest,
    DocumentResponse,
    DocumentStatsResponse,
    DocumentStatus,
    FieldCorrectionRequest,
)
from app.documents.service import (
    DocumentContentError,
    DocumentNotFoundError,
    DocumentProcessingError,
    DocumentReviewConflictError,
    DocumentService,
)
from app.invoices.validation import ValidationIssue

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def get_workspace_id(
    x_workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> str:
    """Extract and validate required anonymous workspace ID from X-Workspace-ID header."""
    if not x_workspace_id or not x_workspace_id.strip():
        raise HTTPException(
            status_code=400,
            detail="Missing required X-Workspace-ID header.",
        )
    candidate = x_workspace_id.strip()
    try:
        val = UUID(candidate)
        return str(val)
    except (ValueError, AttributeError) as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid X-Workspace-ID header format. Must be a valid UUID.",
        ) from error


def get_session(request: Request) -> Iterator[Session]:
    """Dependency that yields a managed SQLAlchemy session per request."""
    with request.app.state.session_factory() as session:
        yield session


def get_repository(session: Annotated[Session, Depends(get_session)]) -> DocumentRepository:
    """Dependency providing a DocumentRepository bound to current request session."""
    return DocumentRepository(session)


def build_service(request: Request, repository: DocumentRepository) -> DocumentService:
    """Helper constructing a DocumentService with application state configuration."""
    config: AppConfig = request.app.state.config
    return DocumentService(
        repository=repository,
        upload_dir=config.upload_dir,
        expected_customer_name=config.expected_customer_name,
        expected_customer_vat_id=config.expected_customer_vat_id,
        min_confidence=config.min_field_confidence,
    )


def to_response(record: DocumentRecord) -> DocumentResponse:
    """Map SQLAlchemy DocumentRecord to clean Pydantic DocumentResponse."""
    issues = [ValidationIssue.model_validate(item) for item in (record.issues or [])]
    response = DocumentResponse.model_validate(record)
    return response.model_copy(update={"issues": issues})


def validate_file_magic_bytes(content: bytes, content_type: str) -> None:
    """Validate that file binary signature matches the declared MIME type."""
    if content_type == "application/pdf":
        if not content.startswith(b"%PDF"):
            raise HTTPException(
                status_code=422,
                detail="Invalid file signature: declared as PDF but does not begin with %PDF.",
            )
    elif content_type == "image/png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=422,
                detail="Invalid file signature: declared as PNG but does not match PNG signature.",
            )
    elif content_type in ("image/jpeg", "image/jpg"):
        if not content.startswith(b"\xff\xd8\xff"):
            raise HTTPException(
                status_code=422,
                detail="Invalid file signature: declared as JPEG but does not match signature.",
            )


@router.get("/stats", response_model=DocumentStatsResponse)
def get_document_stats(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentStatsResponse:
    """Retrieve aggregate KPI dashboard statistics for the requesting workspace."""
    stats = repository.get_stats(workspace_id=workspace_id)
    return DocumentStatsResponse(**stats)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    repository: Annotated[DocumentRepository, Depends(get_repository)],
    status: DocumentStatus | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> list[DocumentResponse]:
    """List processed documents scoped to the requesting workspace."""
    records = repository.list(
        workspace_id=workspace_id,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return [to_response(record) for record in records]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    """Retrieve processing details for a document belonging to the workspace."""
    service = build_service(request, repository)
    try:
        return to_response(service.get(document_id, workspace_id=workspace_id))
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{document_id}/file")
def get_document_file(
    document_id: str,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> FileResponse:
    """Retrieve original uploaded binary file for a document belonging to the workspace."""
    service = build_service(request, repository)
    try:
        record = service.get(document_id, workspace_id=workspace_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    path = request.app.state.config.upload_dir / Path(record.stored_filename).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored document file was not found.")
    return FileResponse(
        path,
        media_type=record.content_type,
        filename=record.original_filename,
        content_disposition_type="inline",
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> Response:
    """Delete a document record and file belonging to the workspace."""
    service = build_service(request, repository)
    try:
        service.delete(document_id, workspace_id=workspace_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{document_id}/accounting", response_model=DocumentResponse)
def select_gl_account(
    document_id: str,
    body: AccountingSelectionRequest,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    """Select or override GL account code for a document in the workspace."""
    service = build_service(request, repository)
    try:
        return to_response(
            service.select_gl_account(
                document_id, workspace_id=workspace_id, gl_account_code=body.gl_account_code
            )
        )
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentReviewConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{document_id}/decision", response_model=DocumentResponse)
def decide_document(
    document_id: str,
    body: DecisionRequest,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    """Record reviewer final decision on a document belonging to the workspace."""
    service = build_service(request, repository)
    try:
        return to_response(
            service.decide(document_id, workspace_id=workspace_id, decision=body.decision)
        )
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentReviewConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    """Upload a document, run pipeline, and record findings scoped to requesting workspace."""
    config: AppConfig = request.app.state.config
    content_type = file.content_type or "application/octet-stream"
    suffix = ALLOWED_CONTENT_TYPES.get(content_type)
    if suffix is None:
        raise HTTPException(
            status_code=415,
            detail="Unsupported document format. Allowed formats are PDF, JPEG, and PNG.",
        )

    payload = file.file.read(config.max_upload_bytes + 1)
    if not payload:
        raise HTTPException(status_code=422, detail="Uploaded document file is empty.")
    if len(payload) > config.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail="File size exceeds maximum allowed limit (4 MB).",
        )

    validate_file_magic_bytes(payload, content_type)

    original_filename = Path(file.filename or "document").name[:255]
    service = build_service(request, repository)
    try:
        record = service.process(
            workspace_id=workspace_id,
            original_filename=original_filename,
            content_type=content_type,
            content=payload,
            suffix=suffix,
        )
    except DocumentContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DocumentProcessingError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return to_response(record)


@router.put("/{document_id}/corrections", response_model=DocumentResponse)
def apply_corrections(
    document_id: str,
    body: FieldCorrectionRequest,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    """Apply reviewer corrections to document fields within the requesting workspace."""
    service = build_service(request, repository)
    try:
        record = service.apply_corrections(document_id, workspace_id=workspace_id, corrections=body)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentReviewConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return to_response(record)


@router.post("/{document_id}/correction-email", response_model=CorrectionEmailResponse)
def draft_correction_email(
    document_id: str,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> CorrectionEmailResponse:
    """Generate an on-demand supplier correction email draft within the workspace."""
    service = build_service(request, repository)
    try:
        subject, body = service.draft_correction_email(document_id, workspace_id=workspace_id)
        return CorrectionEmailResponse(subject=subject, body=body)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
