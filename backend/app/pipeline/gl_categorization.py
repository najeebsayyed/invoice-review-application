"""Pipeline step and categorizer suggesting a Northstar GL account from normalized fields."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.accounting.catalog import format_catalog_for_prompt
from app.accounting.schemas import GlSuggestion
from app.schemas.invoice import InvoiceData
from app.schemas.receipt import ReceiptData
from app.services.openai_service import OpenAIService, OpenAISettings

if TYPE_CHECKING:
    from app.pipeline.base import PipelineContext

logger = logging.getLogger(__name__)

GL_CATEGORIZATION_PROMPT = (
    "Suggest the best Northstar GL account for this extracted financial document."
)

GL_CATEGORIZATION_INSTRUCTIONS = f"""\
You categorize extracted invoice and receipt fields for Northstar Facilities B.V.,
a facilities-management company in Amsterdam.

Use the vendor or merchant name, line-item descriptions, totals, and document type
to pick the single best GL account from the fixed catalog below. Invoices usually
reflect supplier services; receipts usually reflect paid employee or field expenses.

{format_catalog_for_prompt()}

Return exactly one catalog code from the list above, a confidence score between 0.0 and 1.0,
and a concise human-readable rationale that Maya (the finance reviewer) can read
to understand your choice.
"""


def build_gl_categorization_input(
    data: InvoiceData | ReceiptData,
) -> dict[str, Any]:
    """Convert normalized invoice or receipt domain models into a clean categorizer payload.

    Boundary rule: The GL categorizer receives normalized invoice/receipt fields only,
    never raw document bytes or unparsed PDF/image layouts.
    """
    if isinstance(data, InvoiceData):
        return {
            "document_type": "invoice",
            "vendor_name": data.vendor_name,
            "vendor_address": data.vendor_address,
            "invoice_number": data.invoice_number,
            "invoice_date": str(data.invoice_date) if data.invoice_date else None,
            "due_date": str(data.due_date) if data.due_date else None,
            "purchase_order": data.purchase_order,
            "subtotal": float(data.subtotal) if data.subtotal is not None else None,
            "total_tax": float(data.total_tax) if data.total_tax is not None else None,
            "invoice_total": float(data.invoice_total) if data.invoice_total is not None else None,
            "currency": data.currency,
            "line_items": [
                {
                    "description": item.description,
                    "amount": float(item.amount) if item.amount is not None else None,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price) if item.unit_price is not None else None,
                }
                for item in data.items
            ]
            if data.items
            else [],
        }

    return {
        "document_type": "receipt",
        "merchant_name": data.merchant_name,
        "merchant_address": data.merchant_address,
        "transaction_date": str(data.transaction_date) if data.transaction_date else None,
        "transaction_time": data.transaction_time,
        "receipt_type": data.receipt_type,
        "subtotal": float(data.subtotal) if data.subtotal is not None else None,
        "total_tax": float(data.total_tax) if data.total_tax is not None else None,
        "tip": float(data.tip) if data.tip is not None else None,
        "total": float(data.total) if data.total is not None else None,
        "currency": data.currency,
        "line_items": [
            {
                "description": item.description,
                "amount": float(item.total_price) if item.total_price is not None else None,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price) if item.unit_price is not None else None,
            }
            for item in data.items
        ]
        if data.items
        else [],
    }


class GlCategorizer:
    """Suggest a Northstar GL account from normalized extraction fields using structured output."""

    def __init__(
        self,
        openai_service: OpenAIService | None = None,
        settings: OpenAISettings | None = None,
    ) -> None:
        self._openai_service = openai_service or OpenAIService(
            api_key=settings.openai_api_key if settings else None,
            model=settings.openai_model if settings else None,
        )

    def run(self, extraction: InvoiceData | ReceiptData) -> GlSuggestion:
        """Categorize a normalized invoice or receipt into a catalog GL account."""
        payload = build_gl_categorization_input(extraction)

        prompt_text = (
            f"{GL_CATEGORIZATION_INSTRUCTIONS}\n\n"
            f"Extracted document fields:\n"
            f"{json.dumps(payload, indent=2, default=str)}\n\n"
            f"{GL_CATEGORIZATION_PROMPT}"
        )

        response = self._openai_service._client.responses.parse(
            model=self._openai_service.model,
            text_format=GlSuggestion,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt_text},
                    ],
                }
            ],
        )

        return response.output_parsed


class GlCategorizationStep:
    """Pipeline step that suggests a GL account and records ctx.gl_suggestion."""

    name: str = "gl_categorization"

    def __init__(self, categorizer: GlCategorizer | None = None) -> None:
        self._categorizer = categorizer or GlCategorizer()

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Run GL categorization using normalized extracted data in context."""
        extraction = ctx.invoice_data or ctx.receipt_data
        if extraction is None:
            logger.warning("No extraction data found in context for GL categorization.")
            return ctx

        logger.info("Suggesting Northstar GL account with OpenAI")
        suggestion = self._categorizer.run(extraction)
        logger.info(
            "Suggested GL account %s (%s, confidence=%.2f)",
            suggestion.account_code.value,
            suggestion.account_name,
            suggestion.confidence,
        )
        return ctx.model_copy(update={"gl_suggestion": suggestion})
