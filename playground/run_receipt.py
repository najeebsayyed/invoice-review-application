"""Playground script to test Document Intelligence receipt processing."""

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
    """Resolve sample receipt path from command line arguments or default sample."""
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if target.is_file():
            return target
        candidate = PROJECT_ROOT / "samples" / "generated" / sys.argv[1]
        if candidate.is_file():
            return candidate

    # Default to 13-nl-fuel-receipt.png
    default_sample = PROJECT_ROOT / "samples" / "generated" / "13-nl-fuel-receipt.png"
    if not default_sample.is_file():
        raise FileNotFoundError(f"Sample receipt not found at {default_sample}")
    return default_sample


def main() -> None:
    sample_file = resolve_document_path()
    print("=== Running Document Intelligence Receipt Extraction ===")
    print(f"File: {sample_file.resolve()}\n")

    service = DocumentIntelligenceService()
    receipt_data = service.process_receipt(sample_file)

    print("--- Summary Extracted Fields ---")
    print(f"Document Type   : {receipt_data.document_type}")
    print(f"Merchant Name   : {receipt_data.merchant_name}")
    print(f"Merchant Address: {receipt_data.merchant_address}")
    print(f"Merchant Phone  : {receipt_data.merchant_phone_number}")
    print(f"Transaction Date: {receipt_data.transaction_date}")
    print(f"Transaction Time: {receipt_data.transaction_time}")
    print(f"Receipt Type    : {receipt_data.receipt_type}")
    print(f"Country/Region  : {receipt_data.country_region}")
    print(f"Currency        : {receipt_data.currency}")
    print(f"Subtotal        : {receipt_data.subtotal}")
    print(f"Total Tax       : {receipt_data.total_tax}")
    print(f"Tip             : {receipt_data.tip}")
    print(f"Total           : {receipt_data.total}")
    print(f"Line Items      : {len(receipt_data.items)}")
    print(f"Tax Details     : {len(receipt_data.tax_details)}")
    print(f"Overall Conf.   : {receipt_data.confidence}\n")

    print("--- Unified Alias Access ---")
    print(f"vendor_name     : {receipt_data.vendor_name}")
    print(f"invoice_date    : {receipt_data.invoice_date}")
    print(f"invoice_total   : {receipt_data.invoice_total}\n")

    print("--- Full Receipt Data Model (JSON) ---")
    print(json.dumps(receipt_data.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
