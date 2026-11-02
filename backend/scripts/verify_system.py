"""End-to-end system verification script for Invoice Review backend.

Tests full HTTP lifecycle, file magic bytes, validation rules, GL catalog,
reviewer corrections, state machine transitions, and KPI statistics without
requiring live cloud credentials or external test harnesses.
"""

from __future__ import annotations

import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.accounting.catalog import NORTHSTAR_GL_CATALOG  # noqa: E402
from app.accounting.routes import router as accounting_router  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.database import build_database  # noqa: E402
from app.documents.models import DocumentRecord  # noqa: E402
from app.documents.repository import DocumentRepository  # noqa: E402
from app.documents.routes import router as document_router  # noqa: E402


def build_verification_app(temp_dir: Path) -> tuple[FastAPI, DocumentRepository]:
    """Construct an isolated test app instance backed by a temporary SQLite database."""
    db_path = temp_dir / "verify.db"
    upload_path = temp_dir / "uploads"
    upload_path.mkdir(parents=True, exist_ok=True)

    db_url = f"sqlite:///{db_path}"
    engine, session_factory = build_database(db_url)
    DocumentRecord.metadata.create_all(engine)

    config = AppConfig(
        database_url=db_url,
        upload_dir=upload_path,
        max_upload_bytes=4 * 1024 * 1024,
        expected_customer_name="Northstar Facilities B.V.",
        expected_customer_vat_id="NL00449544B01",
        min_field_confidence=0.8,
    )

    app = FastAPI(title="Verification App")
    app.state.config = config
    app.state.engine = engine
    app.state.session_factory = session_factory

    app.include_router(document_router)
    app.include_router(accounting_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    repository = DocumentRepository(session_factory())
    return app, repository


def run_verification() -> bool:
    """Execute end-to-end system verification checks."""
    print("=" * 70)
    print("INVOICE REVIEW - END-TO-END SYSTEM VERIFICATION")
    print("=" * 70)

    passed_checks = 0
    total_checks = 8

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        app, repository = build_verification_app(temp_dir)
        client = TestClient(app)
        try:
            # 1. Health check & GL catalog
            print("\n[1/8] Verifying Health Check & General Ledger Catalog...")
            res = client.get("/health")
            assert res.status_code == 200, f"Expected 200, got {res.status_code}"
            assert res.json() == {"status": "ok"}

            res = client.get("/api/accounting/gl-accounts")
            assert res.status_code == 200, f"Expected 200, got {res.status_code}"
            catalog_data = res.json()
            assert len(catalog_data) == len(NORTHSTAR_GL_CATALOG) == 10
            print(f"      PASS: GL catalog returned {len(catalog_data)} fixed accounts.")
            passed_checks += 1

            # 2. File upload validation & magic-byte enforcement
            print("\n[2/8] Verifying File Upload Validation & Magic-Byte Signatures...")
            # A: Disallowed MIME type
            res = client.post(
                "/api/documents",
                files={"file": ("malicious.exe", b"MZ...", "application/x-msdownload")},
            )
            assert res.status_code == 415, f"Expected 415, got {res.status_code}"

            # B: Empty file
            res = client.post(
                "/api/documents",
                files={"file": ("empty.pdf", b"", "application/pdf")},
            )
            assert res.status_code == 422, f"Expected 422, got {res.status_code}"

            # C: Spoofed PDF (content is plain text, not starting with %PDF)
            res = client.post(
                "/api/documents",
                files={"file": ("fake.pdf", b"Hello text file spoofed as pdf", "application/pdf")},
            )
            assert res.status_code == 422, f"Expected 422, got {res.status_code}"
            assert "Invalid file signature" in res.json().get("detail", "")
            print("      PASS: Blocked unsupported extensions and spoofed magic bytes.")
            passed_checks += 1

            # 3. Seed an initial document record with validation issues
            print("\n[3/8] Verifying Document Persistence & Schema...")
            doc_id = "doc-verify-001"
            test_file = temp_dir / "uploads" / f"{doc_id}.pdf"
            test_file.write_bytes(b"%PDF-1.4 dummy invoice binary content")

            with app.state.session_factory() as session:
                record = DocumentRecord(
                    id=doc_id,
                    original_filename="sample_invoice.pdf",
                    stored_filename=f"{doc_id}.pdf",
                    content_type="application/pdf",
                    status="needs_review",
                    normalized_vendor_name="acme cleaning bv",
                    normalized_invoice_number="inv2026001",
                    review_data={
                        "document_type": "invoice",
                        "vendor_name": "Acme Cleaning B.V.",
                        "vendor_vat_id": "DE123456789",  # Invalid DE VAT (bad checksum)
                        "customer_name": "Northstar Facilities B.V.",
                        "customer_vat_id": "NL00449544B01",
                        "invoice_number": "INV-2026-001",
                        "purchase_order": "PO-2026-001",
                        "invoice_date": "2026-03-01",
                        "due_date": "2026-03-31",
                        "currency": "EUR",
                        "subtotal": 1000.00,
                        "total_tax": 210.00,
                        "invoice_total": 1210.00,
                        "amount_due": 1210.00,
                        "line_items": [
                            {
                                "description": "Office sanitization",
                                "quantity": 1,
                                "unit_price": 1000.00,
                                "amount": 1000.00,
                            }
                        ],
                        "provenance": {"vendor_name": "primary", "invoice_total": "primary"},
                    },
                    accounting_coding={
                        "suggestion": {
                            "gl_account_code": "6110",
                            "category": "Building Maintenance",
                            "rationale": "Handyman work",
                            "confidence": 0.95,
                        },
                        "selected_gl_account_code": "6110",
                        "overridden": False,
                        "error_message": None,
                    },
                    issues=[
                        {
                            "code": "invalid_vendor_vat_id",
                            "field": "vendor_vat_id",
                            "severity": "error",
                            "message": "Invalid German VAT number format or checksum.",
                        }
                    ],
                )
                session.add(record)
                session.commit()

            res = client.get(f"/api/documents/{doc_id}")
            assert res.status_code == 200
            doc_json = res.json()
            assert doc_json["status"] == "needs_review"
            assert len(doc_json["issues"]) == 1
            assert doc_json["issues"][0]["code"] == "invalid_vendor_vat_id"
            print(f"      PASS: Document {doc_id} created and retrieved with issues.")
            passed_checks += 1

            # 4. GL Account selection and override
            print("\n[4/8] Verifying General Ledger Account Selection...")
            res = client.put(
                f"/api/documents/{doc_id}/accounting",
                json={"gl_account_code": "6100"},
            )
            assert res.status_code == 200
            coding = res.json()["accounting_coding"]
            assert coding["selected_gl_account_code"] == "6100"
            assert coding["overridden"] is True
            print("      PASS: Successfully selected and recorded GL account 6100.")
            passed_checks += 1

            # 5. Field correction and deterministic revalidation
            print("\n[5/8] Verifying Reviewer Field Correction & Pure Revalidation...")
            # Correct vendor VAT to a valid German VAT ID (DE136695976 has valid checksum)
            res = client.put(
                f"/api/documents/{doc_id}/corrections",
                json={"vendor_vat_id": "DE136695976"},
            )
            assert res.status_code == 200
            corrected_json = res.json()
            assert corrected_json["review_data"]["vendor_vat_id"] == "DE136695976"
            assert corrected_json["review_data"]["provenance"]["vendor_vat_id"] == "user"
            # Since invalid VAT was corrected and all required fields are present, issues cleared
            assert len(corrected_json["issues"]) == 0
            assert corrected_json["status"] == "ready"
            print("      PASS: Correction applied, pure revalidation cleared issues -> 'ready'.")
            passed_checks += 1

            # 6. Final reviewer decision
            print("\n[6/8] Verifying Final Review Decision State Machine...")
            res = client.post(
                f"/api/documents/{doc_id}/decision",
                json={"decision": "approved"},
            )
            assert res.status_code == 200
            assert res.json()["status"] == "approved"

            # Attempting modifications on approved document must return 409 Conflict
            conflict_res = client.put(
                f"/api/documents/{doc_id}/corrections",
                json={"vendor_name": "Changed Name"},
            )
            assert conflict_res.status_code == 409
            print("      PASS: Document approved; state immutability enforced (409 Conflict).")
            passed_checks += 1

            # 7. Aggregate KPI Metrics & Query Filtering
            print("\n[7/8] Verifying Aggregate KPI Metrics & Inbox Search/Filtering...")
            stats_res = client.get("/api/documents/stats")
            assert stats_res.status_code == 200
            stats = stats_res.json()
            assert stats["total_documents"] == 1
            assert stats["approved_count"] == 1
            assert stats["ready_count"] == 0
            assert stats["needs_review_count"] == 0
            assert Decimal(str(stats["total_spend"])) == Decimal("1210.00")

            # Query filter: status=approved
            approved_list = client.get("/api/documents?status=approved").json()
            assert len(approved_list) == 1

            # Query filter: status=needs_review (should be 0)
            review_list = client.get("/api/documents?status=needs_review").json()
            assert len(review_list) == 0

            # Query filter: search term
            search_match = client.get("/api/documents?search=acme").json()
            assert len(search_match) == 1
            search_nomatch = client.get("/api/documents?search=nonexistent").json()
            assert len(search_nomatch) == 0
            print("      PASS: KPI statistics and search/filter queries computed accurately.")
            passed_checks += 1

            # 8. Document Deletion & Cleanup
            print("\n[8/8] Verifying Document Deletion & Storage Cleanup...")
            del_res = client.delete(f"/api/documents/{doc_id}")
            assert del_res.status_code == 204
            assert not test_file.exists()

            get_res = client.get(f"/api/documents/{doc_id}")
            assert get_res.status_code == 404

            stats_after = client.get("/api/documents/stats").json()
            assert stats_after["total_documents"] == 0
            assert Decimal(str(stats_after["total_spend"])) == Decimal("0.00")
            print("      PASS: Document record and binary file deleted successfully.")
            passed_checks += 1
        finally:
            client.close()
            app.state.engine.dispose()

    print("\n" + "=" * 70)
    print(f"RESULT: {passed_checks}/{total_checks} CHECKS PASSED (100%)")
    print("All architectural boundaries, schemas, and security checks verified!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
