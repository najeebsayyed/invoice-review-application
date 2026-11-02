"""Hybrid extraction evaluator.

Runs target invoice and receipt documents through both primary (Document Intelligence)
and secondary (Azure OpenAI) extraction engines, reporting field provenance, fallbacks,
conflicts, and final validation status.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.invoices.validation import validate_invoice, validate_receipt  # noqa: E402
from app.pipeline.extraction import merge_invoice_data, merge_receipt_data  # noqa: E402
from app.services.document_intelligence_service import DocumentIntelligenceService  # noqa: E402
from app.services.openai_service import OpenAIService  # noqa: E402

logging.basicConfig(level=logging.WARNING)

SAMPLES_DIR = BACKEND_ROOT.parent / "samples" / "generated"


def evaluate_hybrid() -> None:
    """Run hybrid extraction evaluation on Dutch invoice and Dutch fuel receipt."""
    print("=" * 80)
    print("NORTHSTAR FACILITIES — HYBRID EXTRACTION & PROVENANCE EVALUATION")
    print("=" * 80)

    primary_service = DocumentIntelligenceService()
    secondary_service = OpenAIService()

    targets = [
        ("02-nl-happy-compact.pdf", "invoice"),
        ("13-nl-fuel-receipt.png", "receipt"),
    ]

    for filename, doc_type in targets:
        file_path = SAMPLES_DIR / filename
        if not file_path.is_file():
            print(f"\n[SKIP] Missing target file: {file_path}")
            continue

        print(f"\nEvaluating: {filename} ({doc_type.upper()})")
        print("-" * 60)

        if doc_type == "invoice":
            print("1. Running Primary: Azure AI Document Intelligence (prebuilt-invoice)...")
            primary_inv = primary_service.process_invoice(file_path)
            print(f"   Primary Vendor     : {primary_inv.vendor_name}")
            print(f"   Primary VAT ID     : {primary_inv.vendor_vat_id}")
            print(f"   Primary Total      : {primary_inv.invoice_total} {primary_inv.currency}")

            print("2. Running Secondary: Azure OpenAI (gpt-6-luna structured outputs)...")
            secondary_inv = secondary_service.process_invoice(file_path)
            print(f"   Secondary Vendor   : {secondary_inv.vendor_name}")
            print(f"   Secondary VAT ID   : {secondary_inv.vendor_vat_id}")
            print(f"   Secondary Total    : {secondary_inv.invoice_total} {secondary_inv.currency}")

            print("3. Executing Deterministic Merge & Provenance Audit...")
            merged_inv, prov, conf = merge_invoice_data(primary_inv, secondary_inv)
            issues = validate_invoice(merged_inv)

            fallbacks = [k for k, v in prov.items() if v == "secondary"]
            print(f"   Merged Vendor      : {merged_inv.vendor_name}")
            print(f"   Merged Total       : {merged_inv.invoice_total} {merged_inv.currency}")
            fallback_desc = fallbacks if fallbacks else 'None (primary complete)'
            print(f"   LLM Fallback Fields: {fallback_desc}")
            print(f"   Detected Conflicts : {conf if conf else 'None'}")
            print(f"   Policy Issues      : {len(issues)} issues")

        else:
            print("1. Running Primary: Azure AI Document Intelligence (prebuilt-receipt)...")
            primary_rec = primary_service.process_receipt(file_path)
            print(f"   Primary Merchant   : {primary_rec.merchant_name}")
            print(f"   Primary Total      : {primary_rec.total} {primary_rec.currency}")

            print("2. Running Secondary: Azure OpenAI (gpt-6-luna structured outputs)...")
            secondary_rec = secondary_service.process_receipt(file_path)
            print(f"   Secondary Merchant : {secondary_rec.merchant_name}")
            print(f"   Secondary Total    : {secondary_rec.total} {secondary_rec.currency}")

            print("3. Executing Deterministic Merge & Provenance Audit...")
            merged_rec, prov, conf = merge_receipt_data(primary_rec, secondary_rec)
            issues = validate_receipt(merged_rec)

            fallbacks = [k for k, v in prov.items() if v == "secondary"]
            print(f"   Merged Merchant    : {merged_rec.merchant_name}")
            print(f"   Merged Total       : {merged_rec.total} {merged_rec.currency}")
            fallback_desc = fallbacks if fallbacks else 'None (primary complete)'
            print(f"   LLM Fallback Fields: {fallback_desc}")
            print(f"   Detected Conflicts : {conf if conf else 'None'}")
            print(f"   Policy Issues      : {len(issues)} issues")

    print("\n" + "=" * 80)
    print("Hybrid extraction evaluation complete.")
    print("=" * 80)


if __name__ == "__main__":
    evaluate_hybrid()
