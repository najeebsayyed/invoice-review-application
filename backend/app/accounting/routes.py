"""FastAPI routes for Northstar General Ledger accounts."""

from __future__ import annotations

from fastapi import APIRouter

from app.accounting.catalog import NORTHSTAR_GL_CATALOG, GlAccount

router = APIRouter(prefix="/api/accounting", tags=["accounting"])


@router.get("/gl-accounts", response_model=list[GlAccount])
def list_gl_accounts() -> list[GlAccount]:
    """Return the fixed 10-account Northstar General Ledger catalog."""
    return list(NORTHSTAR_GL_CATALOG)
