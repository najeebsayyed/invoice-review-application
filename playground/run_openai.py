"""Playground script to test OpenAI document extraction service on invoices and receipts."""

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

from app.services.openai_service import OpenAIService  # noqa: E402


def resolve_document_path() -> Path:
    """Resolve sample document path from command line arguments or default sample."""
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
        raise FileNotFoundError(f"Sample document not found at {default_sample}")
    return default_sample


def main() -> None:
    sample_file = resolve_document_path()
    print("=== Running OpenAI Document Extraction Service ===")
    print(f"File : {sample_file.resolve()}\n")

    service = OpenAIService()
    print(f"Model: {service.model}")

    # Classify first
    doc_type = service.classify_document(sample_file)
    print(f"Detected Document Type: {doc_type}\n")

    if doc_type == "receipt":
        data = service.process_receipt(sample_file)
        print("--- Summary Extracted Fields (Receipt) ---")
        print(f"Merchant Name   : {data.merchant_name}")
        print(f"Transaction Date: {data.transaction_date}")
        print(f"Transaction Time: {data.transaction_time}")
        print(f"Subtotal        : {data.subtotal} {data.currency}")
        print(f"Total Tax       : {data.total_tax} {data.currency}")
        print(f"Total           : {data.total} {data.currency}")
        print(f"Line Items      : {len(data.items)}")
        print(f"Tax Details     : {len(data.tax_details)}")
        print(f"Overall Conf.   : {data.confidence}\n")
    else:
        data = service.process_invoice(sample_file)
        print("--- Summary Extracted Fields (Invoice) ---")
        print(f"Vendor Name   : {data.vendor_name}")
        print(f"Vendor VAT ID : {data.vendor_vat_id}")
        print(f"Customer Name : {data.customer_name}")
        print(f"Customer VAT  : {data.customer_vat_id}")
        print(f"Invoice Number: {data.invoice_number}")
        print(f"Invoice Date  : {data.invoice_date}")
        print(f"Due Date      : {data.due_date}")
        print(f"Purchase Order: {data.purchase_order}")
        print(f"Currency      : {data.currency}")
        print(f"Subtotal      : {data.subtotal}")
        print(f"Total Tax     : {data.total_tax}")
        print(f"Invoice Total : {data.invoice_total}")
        print(f"Line Items    : {len(data.items)}")
        print(f"Overall Conf. : {data.confidence}\n")

    print("--- Full Structured Model (JSON) ---")
    print(json.dumps(data.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()

