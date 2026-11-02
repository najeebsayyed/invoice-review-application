"""Pydantic schemas for General Ledger suggestions and reviewer selection."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.accounting.catalog import GlAccount, GlAccountCode, get_gl_account


class GlSuggestion(BaseModel):
    """Suggested GL account with confidence and reasoning for human reviewer."""

    account_code: GlAccountCode = Field(
        description="The selected Northstar GL account code from the fixed catalog"
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = Field(
        description="Clear, concise rationale explaining why this account fits the document",
        min_length=1,
        max_length=480,
    )

    model_config = ConfigDict(extra="ignore")

    @property
    def account(self) -> GlAccount | None:
        """Resolve the full catalog GlAccount definition."""
        return get_gl_account(self.account_code)

    @property
    def account_name(self) -> str:
        """Convenience property for human-readable account name."""
        acct = self.account
        return acct.name if acct else ""


class AccountingSuggestion(BaseModel):
    """Structured suggestion for API responses and review views."""

    model_config = ConfigDict(extra="forbid")

    gl_account_code: str
    category: str
    rationale: str = Field(min_length=1, max_length=480)
    confidence: float = Field(ge=0, le=1)


class AccountingCoding(BaseModel):
    """Complete accounting coding state including model suggestion and human selection."""

    suggestion: AccountingSuggestion | None = None
    selected_gl_account_code: str | None = None
    overridden: bool = False
    error_message: str | None = None


class AccountingSelectionRequest(BaseModel):
    """Request payload for reviewer overriding or confirming a GL account."""

    gl_account_code: str
