"""Playground script to test Document Intelligence invoice processing."""

import json
import subprocess
import sys
from pathlib import Path

# Paths
PLAYGROUND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PLAYGROUND_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"

# If invoked with system python, automatically delegate to backend virtual environment python
if VENV_PYTHON.is_file() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    sys.exit(subprocess.call([str(VENV_PYTHON), *sys.argv]))

# Ensure backend directory is in sys.path
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.document_intelligence_service import DocumentIntelligenceService  # noqa: E402


def resolve_document_path() -> Path:
    """Resolve sample invoice path from command line arguments or default sample."""
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if target.is_file():
            return target
        candidate = PROJECT_ROOT / "samples" / "generated" / sys.argv[1]
        if candidate.is_file():
            return candidate

    # Default to 01-en-happy-classic.pdf
    default_sample = PROJECT_ROOT / "samples" / "generated" / "01-en-happy-classic.pdf"
    if not default_sample.is_file():
        raise FileNotFoundError(f"Sample invoice not found at {default_sample}")
    return default_sample


def main() -> None:
    sample_file = resolve_document_path()
    print("=== Running Document Intelligence Extraction ===")
    print(f"File: {sample_file.resolve()}\n")

    service = DocumentIntelligenceService()
    invoice_data = service.process_invoice(sample_file)

    print("--- Summary Extracted Fields ---")
    print(f"Document Type : {invoice_data.document_type}")
    print(f"Vendor Name   : {invoice_data.vendor_name}")
    print(f"Vendor VAT ID : {invoice_data.vendor_vat_id}")
    print(f"Customer Name : {invoice_data.customer_name}")
    print(f"Customer VAT  : {invoice_data.customer_vat_id}")
    print(f"Invoice Number: {invoice_data.invoice_number}")
    print(f"Invoice Date  : {invoice_data.invoice_date}")
    print(f"Due Date      : {invoice_data.due_date}")
    print(f"Purchase Order: {invoice_data.purchase_order}")
    print(f"Currency      : {invoice_data.currency}")
    print(f"Subtotal      : {invoice_data.subtotal}")
    print(f"Total Tax     : {invoice_data.total_tax}")
    print(f"Invoice Total : {invoice_data.invoice_total}")
    print(f"Line Items    : {len(invoice_data.items)}")
    print(f"Overall Conf. : {invoice_data.confidence}\n")

    print("--- Full Invoice Data Model (JSON) ---")
    print(json.dumps(invoice_data.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
