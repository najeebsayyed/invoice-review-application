"""End-to-end system verification script for Invoice Review backend.

Tests full HTTP lifecycle, file magic bytes, validation rules, GL catalog,
reviewer corrections, state machine transitions, aggregate KPI statistics,
and anonymous multi-user workspace data isolation without requiring live cloud
credentials or external test harnesses.
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

    # Workspace identifiers for multi-tenant isolation testing
    ws_a = "11111111-1111-4111-8111-111111111111"
    ws_b = "22222222-2222-4222-8222-222222222222"
    headers_a = {"X-Workspace-ID": ws_a}
    headers_b = {"X-Workspace-ID": ws_b}

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        app, repository = build_verification_app(temp_dir)
        client = TestClient(app)
        try:
            # 1. Health check & GL catalog (public endpoints)
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

            # 2. Workspace Header Security & Format Validation
            print("\n[2/8] Verifying X-Workspace-ID Header Enforcement & Validation...")
            # A: Missing header on protected routes must return 400
            missing_header_res = client.get("/api/documents")
            assert missing_header_res.status_code == 400, (
                f"Expected 400 for missing header, got {missing_header_res.status_code}"
            )
            assert "Missing required X-Workspace-ID header" in missing_header_res.json()["detail"]

            # B: Invalid UUID format must return 400
            invalid_header_res = client.get(
                "/api/documents", headers={"X-Workspace-ID": "not-a-valid-uuid"}
            )
            assert invalid_header_res.status_code == 400, (
                f"Expected 400 for invalid UUID, got {invalid_header_res.status_code}"
            )
            assert "Invalid X-Workspace-ID header format" in invalid_header_res.json()["detail"]
            print("      PASS: Enforced presence and UUID format of X-Workspace-ID header.")
            passed_checks += 1

            # 3. File upload validation & magic-byte enforcement
            print("\n[3/8] Verifying File Upload Validation & Magic-Byte Signatures...")
            # A: Disallowed MIME type
            res = client.post(
                "/api/documents",
                headers=headers_a,
                files={"file": ("malicious.exe", b"MZ...", "application/x-msdownload")},
            )
            assert res.status_code == 415, f"Expected 415, got {res.status_code}"

            # B: Empty file
            res = client.post(
                "/api/documents",
                headers=headers_a,
                files={"file": ("empty.pdf", b"", "application/pdf")},
            )
            assert res.status_code == 422, f"Expected 422, got {res.status_code}"

            # C: Spoofed PDF (content is plain text, not starting with %PDF)
            res = client.post(
                "/api/documents",
                headers=headers_a,
                files={"file": ("fake.pdf", b"Hello text file spoofed as pdf", "application/pdf")},
            )
            assert res.status_code == 422, f"Expected 422, got {res.status_code}"
            assert "Invalid file signature" in res.json().get("detail", "")
            print("      PASS: Blocked unsupported extensions and spoofed magic bytes.")
            passed_checks += 1

            # 4. Workspace A: Document Lifecycle, Correction & Approval
            print("\n[4/8] Verifying Workspace A: Creation, Review, Correction & Approval...")
            doc_a_id = "doc-verify-001"
            file_a = temp_dir / "uploads" / f"{doc_a_id}.pdf"
            file_a.write_bytes(b"%PDF-1.4 dummy invoice binary content")

            with app.state.session_factory() as session:
                record_a = DocumentRecord(
                    id=doc_a_id,
                    workspace_id=ws_a,
                    original_filename="sample_invoice_a.pdf",
                    stored_filename=f"{doc_a_id}.pdf",
                    content_type="application/pdf",
                    status="needs_review",
                    normalized_vendor_name="acme cleaning bv",
                    normalized_invoice_number="inv2026001",
                    review_data={
                        "document_type": "invoice",
                        "vendor_name": "Acme Cleaning B.V.",
                        "vendor_vat_id": "DE123456789",  # Invalid checksum
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
                session.add(record_a)
                session.commit()

            # Retrieve within Workspace A
            res_a = client.get(f"/api/documents/{doc_a_id}", headers=headers_a)
            assert res_a.status_code == 200
            assert res_a.json()["status"] == "needs_review"

            # Select GL Account within Workspace A
            gl_res = client.put(
                f"/api/documents/{doc_a_id}/accounting",
                headers=headers_a,
                json={"gl_account_code": "6100"},
            )
            assert gl_res.status_code == 200
            assert gl_res.json()["accounting_coding"]["selected_gl_account_code"] == "6100"

            # Correct field within Workspace A
            corr_res = client.put(
                f"/api/documents/{doc_a_id}/corrections",
                headers=headers_a,
                json={"vendor_vat_id": "DE136695976"},
            )
            assert corr_res.status_code == 200
            assert corr_res.json()["status"] == "ready"

            # Approve within Workspace A
            appr_res = client.post(
                f"/api/documents/{doc_a_id}/decision",
                headers=headers_a,
                json={"decision": "approved"},
            )
            assert appr_res.status_code == 200
            assert appr_res.json()["status"] == "approved"
            print("      PASS: Workspace A processed, corrected, and approved document.")
            passed_checks += 1

            # 5. Workspace B: Independent Isolation & Invisibility
            print("\n[5/8] Verifying Workspace B: Independent Review History & Isolation...")
            doc_b_id = "doc-verify-002"
            file_b = temp_dir / "uploads" / f"{doc_b_id}.pdf"
            file_b.write_bytes(b"%PDF-1.4 dummy b invoice binary")

            with app.state.session_factory() as session:
                record_b = DocumentRecord(
                    id=doc_b_id,
                    workspace_id=ws_b,
                    original_filename="sample_invoice_b.pdf",
                    stored_filename=f"{doc_b_id}.pdf",
                    content_type="application/pdf",
                    status="needs_review",
                    normalized_vendor_name="bravo electrics",
                    normalized_invoice_number="inv-bravo-99",
                    review_data={
                        "document_type": "invoice",
                        "vendor_name": "Bravo Electrics",
                        "currency": "EUR",
                        "invoice_total": 450.00,
                    },
                    issues=[],
                )
                session.add(record_b)
                session.commit()

            # Verify Workspace B sees only its own document
            list_b = client.get("/api/documents", headers=headers_b).json()
            assert len(list_b) == 1
            assert list_b[0]["id"] == doc_b_id

            # Verify Workspace B cannot access Workspace A's document by ID (returns 404)
            cross_get = client.get(f"/api/documents/{doc_a_id}", headers=headers_b)
            assert cross_get.status_code == 404, (
                f"Expected 404 for cross-workspace document access, got {cross_get.status_code}"
            )

            # Verify Workspace B stats calculate solely for Workspace B
            stats_b = client.get("/api/documents/stats", headers=headers_b).json()
            assert stats_b["total_documents"] == 1
            assert stats_b["approved_count"] == 0
            assert stats_b["needs_review_count"] == 1
            assert Decimal(str(stats_b["total_spend"])) == Decimal("0.00")
            print("      PASS: Workspace B history isolated; Workspace A invisible.")
            passed_checks += 1

            # 6. Cross-Workspace Unauthorized Operations Protection
            print("\n[6/8] Verifying Cross-Workspace Action Protection (404 Unauthorized)...")
            # Attempt to approve Workspace A's invoice from Workspace B
            res = client.post(
                f"/api/documents/{doc_a_id}/decision",
                headers=headers_b,
                json={"decision": "rejected"},
            )
            assert res.status_code == 404

            # Attempt to update GL on Workspace A from Workspace B
            res = client.put(
                f"/api/documents/{doc_a_id}/accounting",
                headers=headers_b,
                json={"gl_account_code": "6120"},
            )
            assert res.status_code == 404

            # Attempt to apply corrections to Workspace A from Workspace B
            res = client.put(
                f"/api/documents/{doc_a_id}/corrections",
                headers=headers_b,
                json={"vendor_name": "Malicious Hijack"},
            )
            assert res.status_code == 404

            # Attempt to draft correction email for Workspace A from Workspace B
            res = client.post(
                f"/api/documents/{doc_a_id}/correction-email",
                headers=headers_b,
            )
            assert res.status_code == 404

            # Attempt to access Workspace A binary file from Workspace B
            res = client.get(f"/api/documents/{doc_a_id}/file", headers=headers_b)
            assert res.status_code == 404

            # Attempt to delete Workspace A from Workspace B
            res = client.delete(f"/api/documents/{doc_a_id}", headers=headers_b)
            assert res.status_code == 404

            # Verify Workspace A's record was completely untouched
            verify_a = client.get(f"/api/documents/{doc_a_id}", headers=headers_a).json()
            assert verify_a["status"] == "approved"
            assert verify_a["review_data"]["vendor_name"] == "Acme Cleaning B.V."
            print("      PASS: All cross-workspace mutations safely rejected with HTTP 404.")
            passed_checks += 1

            # 7. Legacy Record Exclusion & Persistence
            print("\n[7/8] Verifying Legacy Record Exclusion & Persistence...")
            # Seed a legacy record with workspace_id = None
            legacy_id = "doc-legacy-000"
            with app.state.session_factory() as session:
                legacy_record = DocumentRecord(
                    id=legacy_id,
                    workspace_id=None,
                    original_filename="legacy_invoice.pdf",
                    stored_filename="legacy_invoice.pdf",
                    content_type="application/pdf",
                    status="ready",
                    review_data={"invoice_total": 999.00},
                )
                session.add(legacy_record)
                session.commit()

            # Verify neither Workspace A nor Workspace B sees the legacy record
            docs_a = client.get("/api/documents", headers=headers_a).json()
            assert all(d["id"] != legacy_id for d in docs_a)

            docs_b = client.get("/api/documents", headers=headers_b).json()
            assert all(d["id"] != legacy_id for d in docs_b)

            # Verify Workspace A still accesses its own history across requests
            stats_a = client.get("/api/documents/stats", headers=headers_a).json()
            assert stats_a["total_documents"] == 1
            assert stats_a["approved_count"] == 1
            assert Decimal(str(stats_a["total_spend"])) == Decimal("1210.00")
            print("      PASS: Legacy records excluded; Workspace A history fully persistent.")
            passed_checks += 1

            # 8. Document Deletion & Storage Cleanup
            print("\n[8/8] Verifying Workspace Document Deletion & File Cleanup...")
            del_res = client.delete(f"/api/documents/{doc_a_id}", headers=headers_a)
            assert del_res.status_code == 204
            assert not file_a.exists()

            # Confirm Workspace A record is gone
            assert client.get(f"/api/documents/{doc_a_id}", headers=headers_a).status_code == 404

            # Confirm Workspace B's document and file were NOT deleted
            assert client.get(f"/api/documents/{doc_b_id}", headers=headers_b).status_code == 200
            assert file_b.exists()
            print("      PASS: Workspace A document deleted; Workspace B document remains intact.")
            passed_checks += 1
        finally:
            client.close()
            app.state.engine.dispose()

    print("\n" + "=" * 70)
    print(f"RESULT: {passed_checks}/{total_checks} CHECKS PASSED (100%)")
    print("Multi-user anonymous workspace isolation verified successfully!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
