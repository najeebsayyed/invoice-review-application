"""Playground runner to execute the end-to-end Invoice Review pipeline.

Runs:
1. ClassificationStep (LLM-backed classifier)
2. ExtractionStep (Document Intelligence / OpenAI routed extraction)
3. ValidationStep (Deterministic Northstar policy validation)
"""

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

from app.pipeline import (  # noqa: E402
    DocumentKind,
    PipelineContext,
    create_pipeline,
)


def load_manifest() -> list[dict]:
    """Load evaluation corpus manifest."""
    manifest_path = PROJECT_ROOT / "samples" / "manifest.json"
    if not manifest_path.is_file():
        return []
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def run_single_document(file_path: Path, manifest_entry: dict | None = None) -> bool:
    """Execute pipeline on a single document and print detailed audit output."""
    print("=================================================================")
    print(f"PIPELINE RUN: {file_path.name}")
    print("=================================================================")

    # In manifest evaluation, 10-de-duplicate tests duplicate rejection against an existing record
    existing_invoices = (
        [("Rhein Wartung GmbH", "DE-2026-3098")]
        if file_path.name.startswith("10-de-duplicate")
        else []
    )

    pipeline = create_pipeline(existing_invoices=existing_invoices)
    context = PipelineContext(document_path=file_path)

    result_ctx = pipeline.run(context)

    # 1. Classification
    classification = result_ctx.classification
    print("\n[Step 1: Classification]")
    if classification:
        print(f"  Kind      : {classification.document_kind}")
        print(f"  Confidence: {classification.confidence}")
        print(f"  Reasoning : {classification.reasoning}")
    else:
        print("  [ERROR] Classification missing.")

    # 2. Extraction
    print("\n[Step 2: Extraction]")
    is_receipt = bool(
        result_ctx.classification
        and result_ctx.classification.document_kind == DocumentKind.receipt
    )
    if is_receipt:
        receipt = result_ctx.receipt_data
        if receipt:
            print(f"  Merchant  : {receipt.merchant_name}")
            print(f"  Date      : {receipt.transaction_date}")
            print(f"  Total     : {receipt.total} {receipt.currency}")
            print(f"  VAT Total : {receipt.total_tax} {receipt.currency}")
            print(f"  Line Items: {len(receipt.items)}")
        else:
            print("  [ERROR] Receipt extraction data missing.")
    else:
        invoice = result_ctx.invoice_data
        if invoice:
            print(f"  Vendor    : {invoice.vendor_name}")
            print(f"  Vendor VAT: {invoice.vendor_vat_id}")
            print(f"  Customer  : {invoice.customer_name}")
            print(f"  Cust. VAT : {invoice.customer_vat_id}")
            print(f"  Invoice # : {invoice.invoice_number}")
            print(f"  Total     : {invoice.invoice_total} {invoice.currency}")
            print(f"  PO Number : {invoice.purchase_order}")
            print(f"  Line Items: {len(invoice.items)}")
        else:
            print("  [ERROR] Invoice extraction data missing.")

    # 3. Validation
    print("\n[Step 3: Validation (Northstar Policy)]")
    print(f"  Valid Status: {'APPROVED' if result_ctx.is_valid else 'BLOCKED'}")
    print(f"  Issues Count: {len(result_ctx.validation_issues)}")
    for issue in result_ctx.validation_issues:
        badge = f"[{issue.severity.upper()}]"
        print(f"    {badge:<9} {issue.code} ({issue.field}): {issue.message}")

    # 4. GL Account Suggestion
    print("\n[Step 4: GL Account Suggestion]")
    gl = result_ctx.gl_suggestion
    if gl:
        print(f"  Account   : {gl.account_code.value} - {gl.account_name}")
        print(f"  Confidence: {gl.confidence:.2f}")
        print(f"  Reasoning : {gl.reasoning}")
    else:
        print("  [ERROR] GL suggestion missing.")

    # 5. Manifest check if entry provided
    if manifest_entry:
        expected_codes = set(manifest_entry.get("expected_issue_codes", []))
        actual_codes = set(result_ctx.issue_codes)
        matches = expected_codes == actual_codes
        status_str = "MATCH" if matches else "MISMATCH"
        print(f"\n[Manifest Verification: {status_str}]")
        print(f"  Expected Codes: {sorted(expected_codes)}")
        print(f"  Actual Codes  : {sorted(actual_codes)}")
        return matches

    return result_ctx.is_valid


def main() -> None:
    manifest = load_manifest()
    manifest_by_filename = {entry["filename"]: entry for entry in manifest}

    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        print("=== Running Full Pipeline on All 13 Evaluation Documents ===")
        successes = 0
        total = len(manifest)

        for entry in manifest:
            sample_path = PROJECT_ROOT / "samples" / "generated" / entry["filename"]
            if not sample_path.is_file():
                print(f"[SKIP] File not found: {sample_path}")
                continue

            passed = run_single_document(sample_path, manifest_entry=entry)
            if passed:
                successes += 1
            print()

        print("=================================================================")
        print(f"PIPELINE EVALUATION SUMMARY: {successes}/{total} documents passed manifest check.")
        print("=================================================================")
        if successes != total:
            sys.exit(1)
        return

    # Single document execution
    target_filename = sys.argv[1] if len(sys.argv) > 1 else "01-en-happy-classic.pdf"
    target_path = Path(target_filename)
    if not target_path.is_file():
        target_path = PROJECT_ROOT / "samples" / "generated" / target_filename

    if not target_path.is_file():
        raise FileNotFoundError(f"Target document not found at: {target_path}")

    manifest_entry = manifest_by_filename.get(target_path.name)
    run_single_document(target_path, manifest_entry=manifest_entry)


if __name__ == "__main__":
    main()
