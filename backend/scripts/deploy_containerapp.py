"""Deploy Invoice Review backend to Azure Container Apps with secretrefs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent

# Read existing backend/.env to get live credentials
env_path = backend_root / ".env"
if not env_path.exists():
    print("ERROR: backend/.env not found!")
    sys.exit(1)

env_dict: dict[str, str] = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env_dict[k.strip()] = v.strip()

database_url = env_dict.get("DATABASE_URL")
doc_endpoint = env_dict.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
doc_key = env_dict.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")
openai_key = env_dict.get("OPENAI_API_KEY")
openai_model = env_dict.get("OPENAI_MODEL", "gpt-5.6-terra")

if not database_url:
    print("ERROR: DATABASE_URL missing from backend/.env!")
    sys.exit(1)

# Retrieve ACR credentials
print("Retrieving ACR credentials...")
acr_res = subprocess.run(
    ["az.cmd", "acr", "credential", "show", "--name", "acrinvoicereview", "-o", "json"],
    capture_output=True,
    text=True,
    shell=True,
    check=True,
)
acr_creds = json.loads(acr_res.stdout)
acr_username = acr_creds["username"]
acr_password = acr_creds["passwords"][0]["value"]
acr_login_server = "acrinvoicereview.azurecr.io"

# Retrieve Storage Account connection string
print("Retrieving Azure Storage connection string...")
stg_res = subprocess.run(
    [
        "az.cmd",
        "storage",
        "account",
        "show-connection-string",
        "--name",
        "stginvoicereview",
        "--resource-group",
        "rg-invoice-review",
        "--query",
        "connectionString",
        "-o",
        "tsv",
    ],
    capture_output=True,
    text=True,
    shell=True,
    check=True,
)
stg_conn_string = stg_res.stdout.strip()

# Build deploy command
allowed_origins = (
    "http://localhost:5173,"
    "http://localhost:4173,"
    "https://invoice-review-app.najeebsayyed.in"
)

print("Deploying Azure Container App 'invoice-review-api' (Consumption tier, min-replicas 0)...")
cmd = [
    "az.cmd",
    "containerapp",
    "create",
    "--name",
    "invoice-review-api",
    "--resource-group",
    "rg-invoice-review",
    "--environment",
    "env-invoice-review",
    "--image",
    f"{acr_login_server}/invoice-review-backend:latest",
    "--registry-server",
    acr_login_server,
    "--registry-username",
    acr_username,
    "--registry-password",
    acr_password,
    "--target-port",
    "8000",
    "--ingress",
    "external",
    "--min-replicas",
    "0",
    "--max-replicas",
    "2",
    "--cpu",
    "0.25",
    "--memory",
    "0.5Gi",
    "--secrets",
    f"db-url={database_url}",
    f"stg-conn={stg_conn_string}",
    f"doc-key={doc_key}",
    f"openai-key={openai_key}",
    "--env-vars",
    "PORT=8000",
    f"ALLOWED_ORIGINS={allowed_origins}",
    "AZURE_STORAGE_CONTAINER_NAME=invoices",
    f"AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT={doc_endpoint}",
    f"OPENAI_MODEL={openai_model}",
    "DATABASE_URL=secretref:db-url",
    "AZURE_STORAGE_CONNECTION_STRING=secretref:stg-conn",
    "AZURE_DOCUMENT_INTELLIGENCE_KEY=secretref:doc-key",
    "OPENAI_API_KEY=secretref:openai-key",
]

res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
if res.returncode != 0:
    print(f"Deployment failed:\n{res.stderr}")
    sys.exit(res.returncode)

# Parse output to get FQDN
try:
    data = json.loads(res.stdout)
    fqdn = data["properties"]["configuration"]["ingress"]["fqdn"]
    print(f"SUCCESS: Container App live at: https://{fqdn}")
except Exception:
    print("Container App created successfully!")
