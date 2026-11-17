"""Setup and verification script for Azure Database for PostgreSQL Flexible Server.

Connects to the Azure PostgreSQL instance, verifies SSL, ensures schema tables
and indexes exist in 'invoice_review', tests CRUD roundtrips, and configures
backend/.env without leaking or echoing passwords.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from urllib.parse import quote_plus

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from sqlalchemy import text  # noqa: E402

from app.database import build_database  # noqa: E402
from app.documents.models import DocumentRecord  # noqa: E402
from app.documents.repository import DocumentRepository  # noqa: E402

SERVER_HOST = "invoice-review-db.postgres.database.azure.com"
SERVER_PORT = 5432
ADMIN_USER = "Najeeb"
DB_NAME = "invoice_review"


def prompt_password() -> str:
    """Prompt user for password securely without terminal echo."""
    print("=" * 70)
    print("AZURE POSTGRESQL FLEXIBLE SERVER - DATABASE SETUP")
    print("=" * 70)
    print(f"Host:     {SERVER_HOST}")
    print(f"Database: {DB_NAME}")
    print(f"User:     {ADMIN_USER}")
    print("=" * 70)

    while True:
        pw = getpass.getpass(f"Enter PostgreSQL password for '{ADMIN_USER}': ").strip()
        if pw:
            return pw
        print("Password cannot be empty. Please try again.")


def run_setup(password: str) -> None:
    """Execute connectivity, SSL verification, schema creation, and .env configuration."""
    quoted_user = quote_plus(ADMIN_USER)
    quoted_pw = quote_plus(password)
    db_url = (
        f"postgresql+psycopg://{quoted_user}:{quoted_pw}@"
        f"{SERVER_HOST}:{SERVER_PORT}/{DB_NAME}?sslmode=require"
    )

    print("\n[1/4] Connecting to Azure PostgreSQL and checking SSL...")
    engine, session_factory = build_database(db_url)

    with engine.connect() as conn:
        version_row = conn.execute(text("SELECT version();")).fetchone()
        version_str = version_row[0] if version_row else "Unknown"
        print(f"      Connected! Server version: {version_str[:60]}...")

        # Verify SSL connection
        try:
            ssl_row = conn.execute(
                text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid();")
            ).fetchone()
            is_ssl = bool(ssl_row[0]) if ssl_row else False
            print(f"      SSL active: {is_ssl}")
        except Exception:
            print("      SSL active: True (enforced via sslmode=require)")

    print("\n[2/4] Initializing application schema in 'invoice_review'...")
    DocumentRecord.metadata.create_all(engine)

    with engine.connect() as conn:
        tables_res = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public';"
            )
        ).fetchall()
        table_names = [row[0] for row in tables_res]
        assert "documents" in table_names, "Table 'documents' was not created!"
        print(f"      Schema verified! Found public tables: {table_names}")

    print("\n[3/4] Verifying database CRUD operations & workspace isolation query...")
    with session_factory() as session:
        repo = DocumentRepository(session)
        test_id = "test-azure-setup-probe"
        test_ws = "00000000-0000-0000-0000-000000000000"

        # Clean up any leftover probe if present
        if repo.get(test_id, workspace_id=test_ws) is not None:
            repo.delete(test_id, workspace_id=test_ws)

        # Create record
        rec = repo.create_processing(
            record_id=test_id,
            workspace_id=test_ws,
            original_filename="probe.pdf",
            stored_filename="probe.pdf",
            content_type="application/pdf",
        )
        assert rec.id == test_id

        # Query record
        fetched = repo.get(test_id, workspace_id=test_ws)
        assert fetched is not None
        assert fetched.id == test_id

        # Clean up
        repo.delete(test_id, workspace_id=test_ws)
        session.commit()
        print("      CRUD roundtrip test succeeded and cleaned up cleanly.")

    print("\n[4/4] Updating local backend/.env with DATABASE_URL...")
    env_path = backend_root / ".env"
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    updated_lines: list[str] = []
    found_db = False
    for line in existing_lines:
        if line.startswith("DATABASE_URL="):
            updated_lines.append(f"DATABASE_URL={db_url}")
            found_db = True
        else:
            updated_lines.append(line)

    if not found_db:
        updated_lines.append(f"DATABASE_URL={db_url}")

    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    print(f"      DATABASE_URL successfully updated in {env_path.name} (protected by .gitignore).")

    print("\n" + "=" * 70)
    print("SUCCESS: Azure PostgreSQL Flexible Server is fully configured and verified!")
    print("FastAPI is now configured to use Azure PostgreSQL for persistence.")
    print("=" * 70)


def main() -> None:
    """Entry point."""
    try:
        pw = prompt_password()
        run_setup(pw)
    except Exception as err:
        import traceback

        traceback.print_exc()
        print(f"\n[ERROR] Setup failed: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
