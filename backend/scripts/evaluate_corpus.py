"""Golden evaluation corpus runner.

Evaluates the 13-document multilingual evaluation corpus against Document Intelligence
and Northstar validation policies, comparing results against samples/manifest.json.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.pipeline import PipelineContext, create_pipeline  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("evaluate_corpus")

SAMPLES_DIR = BACKEND_ROOT.parent / "samples"
MANIFEST_PATH = SAMPLES_DIR / "manifest.json"
GENERATED_DIR = SAMPLES_DIR / "generated"


def load_manifest() -> list[dict[str, Any]]:
    """Load evaluation manifest."""
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Manifest not found at: {MANIFEST_PATH}")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def evaluate() -> int:
    """Run corpus evaluation across all manifest entries."""
    print("=" * 80)
    print("NORTHSTAR FACILITIES — GOLDEN CORPUS EVALUATION")
    print("=" * 80)

    manifest = load_manifest()
    total_docs = len(manifest)
    passed_docs = 0

    print(f"Loaded {total_docs} documents from manifest.json.\n")
    header = f"{'Filename':<30} {'Type':<8} {'Field Acc':<12} {'Issues Exp/Obs':<20} {'Result'}"
    print(header)
    print("-" * 80)

    for entry in manifest:
        filename = entry["filename"]
        file_path = GENERATED_DIR / filename
        if not file_path.is_file():
            print(f"{filename:<30} MISSING FILE")
            continue

        expected_type = entry.get("document_type")
        expected_fields = entry.get("expected", {})
        expected_issues = set(entry.get("expected_issue_codes", []))

        # Handle duplicate scenario for 10-de-duplicate
        existing_invoices = (
            [("Rhein Wartung GmbH", "DE-2026-3098")]
            if filename.startswith("10-de-duplicate")
            else []
        )

        pipeline = create_pipeline(existing_invoices=existing_invoices)
        context = PipelineContext(document_path=file_path)

        try:
            result_ctx = pipeline.run(context)
        except Exception as err:
            print(f"{filename:<30} CRASHED: {err}")
            continue

        actual_type = (
            result_ctx.classification.document_kind.value
            if result_ctx.classification
            else "unknown"
        )
        type_match = actual_type == expected_type

        # Check fields
        doc_data = (
            result_ctx.receipt_data
            if actual_type == "receipt"
            else result_ctx.invoice_data
        )

        field_matches = 0
        field_checks = 0

        if doc_data:
            data_dict = doc_data.model_dump()
            for key, exp_val in expected_fields.items():
                if exp_val is None:
                    continue
                field_checks += 1
                act_val = data_dict.get(key)
                if act_val is not None and str(act_val).strip() == str(exp_val).strip():
                    field_matches += 1

        accuracy_str = f"{field_matches}/{field_checks}" if field_checks else "N/A"

        # Check issues
        actual_issues = {issue.code for issue in result_ctx.validation_issues}
        issues_match = expected_issues.issubset(actual_issues)

        # Overall document pass/fail
        doc_passed = type_match and issues_match and (field_matches >= field_checks * 0.75)
        if doc_passed:
            passed_docs += 1

        result_tag = "PASS" if doc_passed else "FAIL"
        issues_tag = f"{len(expected_issues)} exp / {len(actual_issues)} obs"

        print(
            f"{filename:<30} {actual_type:<8} {accuracy_str:<12} {issues_tag:<26} {result_tag}",
            flush=True,
        )

    print("-" * 80)
    print(f"Summary: {passed_docs}/{total_docs} documents passed evaluation.")
    print("=" * 80)
    return 0 if passed_docs == total_docs else 1


if __name__ == "__main__":
    sys.exit(evaluate())
