"""Comprehensive experiments script verifying Invoice and Receipt schemas and mapping."""

import json
import subprocess
import sys
from decimal import Decimal
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

from app.schemas.invoice import InvoiceData, InvoiceItem, InvoiceTaxDetail  # noqa: E402
from app.schemas.receipt import ReceiptData, ReceiptItem, ReceiptTaxDetail  # noqa: E402
from app.services.document_intelligence_service import DocumentIntelligenceService  # noqa: E402


def experiment_1_schema_direct_instantiation() -> None:
    """Experiment 1: Direct instantiation and type validation of schemas."""
    print("=================================================================")
    print("Experiment 1: Direct Schema Instantiation & Validation")
    print("=================================================================")

    # Test Invoice schema with Decimal precision and line items
    sample_invoice = InvoiceData(
        vendor_name="Bright Spark Europe S.A.S.",
        vendor_vat_id="FR61954506077",
        customer_name="Northstar Facilities B.V.",
        customer_vat_id="NL00449544B01",
        invoice_number="EN-2026-1001",
        invoice_date="2026-07-01",
        due_date="2026-07-31",
        purchase_order="PO-4001",
        subtotal=Decimal("100.00"),
        total_tax=Decimal("21.00"),
        invoice_total=Decimal("121.00"),
        currency="EUR",
        items=[
            InvoiceItem(
                description="Facility maintenance",
                quantity=4.0,
                unit_price=Decimal("25.00"),
                amount=Decimal("100.00"),
                confidence=0.95,
            )
        ],
        tax_details=[
            InvoiceTaxDetail(
                amount=Decimal("21.00"),
                rate="21%",
                confidence=0.92,
            )
        ],
        confidence=0.96,
    )

    assert sample_invoice.document_type == "invoice"
    assert sample_invoice.invoice_total == Decimal("121.00")
    assert len(sample_invoice.items) == 1
    assert sample_invoice.items[0].amount == Decimal("100.00")
    print("[PASS] InvoiceData instantiated and validated successfully.")

    # Test Receipt schema with unified aliases
    sample_receipt = ReceiptData(
        merchant_name="North Sea Fuel B.V.",
        merchant_address="Wibautstraat 150, Amsterdam",
        transaction_date="2026-07-19",
        transaction_time="14:32:00",
        subtotal=Decimal("50.00"),
        total_tax=Decimal("10.50"),
        total=Decimal("60.50"),
        currency="EUR",
        receipt_type="Fuel&Energy.Gas",
        items=[
            ReceiptItem(
                description="EURO 95 Brandstof",
                quantity=25.0,
                quantity_unit="L",
                unit_price=Decimal("2.42"),
                total_price=Decimal("60.50"),
                confidence=0.88,
            )
        ],
        tax_details=[
            ReceiptTaxDetail(
                amount=Decimal("10.50"),
                rate=0.21,
                description="BTW",
                confidence=0.98,
            )
        ],
        confidence=0.98,
    )

    assert sample_receipt.document_type == "receipt"
    assert sample_receipt.total == Decimal("60.50")
    # Verify unified alias access
    assert sample_receipt.vendor_name == "North Sea Fuel B.V."
    assert sample_receipt.invoice_date == "2026-07-19"
    assert sample_receipt.invoice_total == Decimal("60.50")
    print("[PASS] ReceiptData instantiated and aliases verified successfully.\n")


def experiment_2_live_invoice_extraction() -> None:
    """Experiment 2: Live extraction and mapping for invoice document."""
    print("=================================================================")
    print("Experiment 2: Live Extraction & Mapping - Invoice (01-en-happy-classic.pdf)")
    print("=================================================================")
    sample_path = PROJECT_ROOT / "samples" / "generated" / "01-en-happy-classic.pdf"
    service = DocumentIntelligenceService()
    invoice = service.process_invoice(sample_path)

    print(f"Document Type  : {invoice.document_type}")
    print(f"Vendor Name    : {invoice.vendor_name}")
    print(f"Vendor VAT ID  : {invoice.vendor_vat_id}")
    print(f"Customer Name  : {invoice.customer_name}")
    print(f"Customer VAT ID: {invoice.customer_vat_id}")
    print(f"Invoice Number : {invoice.invoice_number}")
    print(f"Invoice Date   : {invoice.invoice_date}")
    print(f"Due Date       : {invoice.due_date}")
    print(f"Subtotal       : {invoice.subtotal} {invoice.currency}")
    print(f"Total Tax      : {invoice.total_tax} {invoice.currency}")
    print(f"Invoice Total  : {invoice.invoice_total} {invoice.currency}")
    print(f"Line items     : {len(invoice.items)}")
    print(f"Confidence     : {invoice.confidence}")

    assert invoice.document_type == "invoice"
    assert invoice.vendor_name == "Bright Spark Europe S.A.S."
    assert invoice.vendor_vat_id == "FR61954506077"
    assert invoice.invoice_total == Decimal("121.0")
    print("[PASS] Invoice extraction and mapping matches expected ground truth.\n")


def experiment_3_live_receipt_extraction() -> None:
    """Experiment 3: Live extraction and mapping for receipt document."""
    print("=================================================================")
    print("Experiment 3: Live Extraction & Mapping - Receipt (13-nl-fuel-receipt.png)")
    print("=================================================================")
    sample_path = PROJECT_ROOT / "samples" / "generated" / "13-nl-fuel-receipt.png"
    service = DocumentIntelligenceService()
    receipt = service.process_receipt(sample_path)

    print(f"Document Type   : {receipt.document_type}")
    print(f"Merchant Name   : {receipt.merchant_name}")
    merchant_addr = (
        receipt.merchant_address.replace("\n", ", ")
        if receipt.merchant_address
        else None
    )
    print(f"Merchant Address: {merchant_addr}")
    print(f"Transaction Date: {receipt.transaction_date}")
    print(f"Transaction Time: {receipt.transaction_time}")
    print(f"Receipt Type    : {receipt.receipt_type}")
    print(f"Subtotal        : {receipt.subtotal} {receipt.currency}")
    print(f"Total Tax       : {receipt.total_tax} {receipt.currency}")
    print(f"Total           : {receipt.total} {receipt.currency}")
    print(f"Line items      : {len(receipt.items)}")
    print(f"Tax details     : {len(receipt.tax_details)}")
    print(f"Confidence      : {receipt.confidence}")

    assert receipt.document_type == "receipt"
    assert "NORTH SEA FUEL" in (receipt.merchant_name or "").upper()
    assert receipt.total == Decimal("60.5")
    assert receipt.vendor_name == receipt.merchant_name
    assert receipt.invoice_total == receipt.total
    print("[PASS] Receipt extraction and mapping matches expected ground truth.\n")


def experiment_4_json_serialization() -> None:
    """Experiment 4: Validate clean JSON serialization for both models."""
    print("=================================================================")
    print("Experiment 4: JSON Serialization Verification")
    print("=================================================================")
    service = DocumentIntelligenceService()
    receipt_path = PROJECT_ROOT / "samples" / "generated" / "13-nl-fuel-receipt.png"
    receipt = service.process_receipt(receipt_path)

    json_output = json.dumps(receipt.model_dump(mode="json"), indent=2)
    parsed = json.loads(json_output)
    assert parsed["document_type"] == "receipt"
    assert parsed["currency"] == "EUR"
    print(f"JSON Output Size: {len(json_output)} chars")
    print("[PASS] JSON serialization works without error.\n")


def main() -> None:
    print("Starting Document Intelligence & Schema Experiments...\n")
    experiment_1_schema_direct_instantiation()
    experiment_2_live_invoice_extraction()
    experiment_3_live_receipt_extraction()
    experiment_4_json_serialization()
    print("=================================================================")
    print("ALL EXPERIMENTS COMPLETED SUCCESSFULLY!")
    print("=================================================================")


if __name__ == "__main__":
    main()
