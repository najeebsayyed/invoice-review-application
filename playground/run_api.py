"""Demonstration and verification script for the Invoice Review FastAPI layer."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def main() -> None:
    client = TestClient(app)
    print("=================================================================")
    print("INVOICE REVIEW API VERIFICATION")
    print("=================================================================")

    # 1. Health check
    print("\n1. Testing GET /health...")
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print(f"   Status: {res.status_code}, Response: {res.json()}")

    # 2. GL Catalog
    print("\n2. Testing GET /api/accounting/gl-accounts...")
    res = client.get("/api/accounting/gl-accounts")
    assert res.status_code == 200, f"GL Accounts failed: {res.text}"
    accounts = res.json()
    print(f"   Status: {res.status_code}, Returned {len(accounts)} catalog accounts.")
    for acct in accounts[:3]:
        print(f"     - {acct['code']}: {acct['name']}")
    print("     ... (remaining 7 accounts)")

    # 3. Swagger documentation
    print("\n3. Testing Swagger UI (/docs) and OpenAPI schema (/openapi.json)...")
    res_docs = client.get("/docs")
    res_openapi = client.get("/openapi.json")
    assert res_docs.status_code == 200, "Swagger UI inaccessible"
    assert res_openapi.status_code == 200, "OpenAPI schema inaccessible"
    paths = list(res_openapi.json()["paths"].keys())
    print(f"   /docs status: {res_docs.status_code}")
    print(f"   /openapi.json status: {res_openapi.status_code}")
    print(f"   Registered routes ({len(paths)}): {paths}")

    # 4. Upload & process document
    sample_file = PROJECT_ROOT / "samples" / "generated" / "01-en-happy-classic.pdf"
    if not sample_file.is_file():
        print(f"\n[SKIP] Sample file not found at {sample_file}")
        return

    print(f"\n4. Testing POST /api/documents (Uploading {sample_file.name})...")
    with open(sample_file, "rb") as f:
        res = client.post(
            "/api/documents",
            files={"file": (sample_file.name, f, "application/pdf")},
        )
    assert res.status_code == 201, f"Upload failed: {res.text}"
    doc = res.json()
    doc_id = doc["id"]
    print(f"   Status: {res.status_code} CREATED")
    print(f"   Document ID : {doc_id}")
    print(f"   Status      : {doc['status']}")
    print(f"   Issues Count: {len(doc['issues'])}")
    if doc.get("gl_suggestion"):
        print(f"   Suggested GL: {doc['gl_suggestion']['account_code']}")
        print(f"   GL Reason   : {doc['gl_suggestion']['reasoning']}")

    # 5. List documents from SQLite
    print("\n5. Testing GET /api/documents (List from SQLite)...")
    res = client.get("/api/documents")
    assert res.status_code == 200
    docs = res.json()
    print(f"   Status: {res.status_code}, Found {len(docs)} document(s) in SQLite database.")
    assert any(d["id"] == doc_id for d in docs), "Uploaded document not found in database list"

    # 6. Retrieve single document
    print(f"\n6. Testing GET /api/documents/{doc_id}...")
    res = client.get(f"/api/documents/{doc_id}")
    assert res.status_code == 200
    print(f"   Status: {res.status_code}, Verified document record.")

    # 7. Select / override GL account
    print(f"\n7. Testing PUT /api/documents/{doc_id}/accounting (Selecting 6120)...")
    res = client.put(
        f"/api/documents/{doc_id}/accounting",
        json={"gl_account_code": "6120"},
    )
    assert res.status_code == 200
    coding = res.json()["accounting_coding"]
    print(f"   Status: {res.status_code}, Selected Code: {coding['selected_gl_account_code']}")
    print(f"   Overridden: {coding['overridden']}")

    # 8. Record approval decision
    print(f"\n8. Testing POST /api/documents/{doc_id}/decision (Approve)...")
    res = client.post(
        f"/api/documents/{doc_id}/decision",
        json={"decision": "approved"},
    )
    assert res.status_code == 200
    print(f"   Status: {res.status_code}, Final Document Status: {res.json()['status']}")

    # 9. Clean up test record
    print(f"\n9. Testing DELETE /api/documents/{doc_id}...")
    res = client.delete(f"/api/documents/{doc_id}")
    assert res.status_code == 204
    print(f"   Status: {res.status_code} NO CONTENT (Record and file cleaned up)")

    print("\n=================================================================")
    print("ALL API ENDPOINTS VERIFIED SUCCESSFULLY!")
    print("=================================================================")


if __name__ == "__main__":
    main()
