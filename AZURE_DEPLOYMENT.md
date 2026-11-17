# Azure Deployment Guide: Invoice Review AI

This guide documents the exact deployment procedure for the **Invoice Review AI** application to **Microsoft Azure** using your **Azure for Students** subscription, maximizing free-tier allowances and keeping monthly costs at **\$0** or pennies.

---

## 1. Discovered & Target Infrastructure Architecture

| Component | Azure Service | Discovered / Target Name | Tier / SKU | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Subscription** | Azure for Students | `Azure for Students` | Active | 1-year student credit & services |
| **Resource Group** | Resource Group | `rg-invoice-review` | Standard | Located in `centralindia` |
| **Database Server** | Azure Database for PostgreSQL | `invoice-review-db` | Burstable `Standard_B1ms` (32 GB) | Flexible Server v16 in `centralindia` |
| **Application DB** | PostgreSQL Database | `invoice_review` | UTF-8, en_US.utf8 | Created and verified |
| **Admin User** | PostgreSQL Admin | `Najeeb` | Password Auth | SSL enforced (`sslmode=require`) |
| **Frontend** | Azure Static Web Apps | `invoice-review-frontend` | **Free Tier** | Custom domain & auto-renewing SSL |
| **Custom Domain** | DNS (Cloudflare / Namecheap) | `invoice-review-app.najeebsayyed.in` | CNAME record | Automatic DigiCert SSL certificate |
| **Backend API** | Azure Container Apps | `invoice-review-api` | **Consumption (Serverless)** | 0 to 2 replicas (scales to \$0 when idle) |
| **Container Registry** | Azure Container Registry | `acrinvoicereview` (or custom) | **Basic** | Builds and hosts container image |
| **File Storage** | Azure Blob Storage | `stginvoicereview` (or local disk) | Standard LRS | For persistent invoice storage |
| **AI Extraction** | Azure Document Intelligence | Existing instance | Free / S0 | Prebuilt invoice & receipt models |
| **AI Review** | OpenAI / Azure OpenAI | Existing API key | `gpt-5.6-terra` | Structured document review |

---

## 2. PostgreSQL Connection & Local Setup

### Connection String Format

```text
postgresql+psycopg://Najeeb:<PASSWORD>@invoice-review-db.postgres.database.azure.com:5432/invoice_review?sslmode=require
```

> **Security Notice:** The password must never be committed to Git, printed to console logs, or shared in chats.

### Automated Local Database Setup & Migration

A dedicated setup script is provided in the repository to safely prompt for your database password, verify SSL connectivity, create all SQLAlchemy tables in `invoice_review`, verify CRUD operations, and write `DATABASE_URL` to your ignored `backend/.env` file:

```powershell
cd backend
uv run --locked --no-sync python scripts/setup_postgres.py
```

---

## 3. Step-by-Step Deployment Walkthrough

### Step 1: Azure Container Registry (ACR) Setup

```bash
# 1. Variables
RESOURCE_GROUP="rg-invoice-review"
LOCATION="centralindia"
ACR_NAME="acrinvoicereview$RANDOM"

# 2. Create ACR (Basic SKU)
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true

# 3. Retrieve ACR Credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)

# 4. Build and Push Backend Image using Azure Cloud Build (no local Docker required)
az acr build \
  --registry $ACR_NAME \
  --image invoice-review-backend:latest \
  --file backend/Dockerfile \
  backend/
```

---

### Step 2: Azure Blob Storage (Document Persistence in Cloud)

Azure Container Apps containers have ephemeral disks. Persistent documents are stored in Azure Blob Storage:

```bash
STORAGE_ACCOUNT="stginvoicereview$RANDOM"

# 1. Create Storage Account (Standard LRS)
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false

# 2. Retrieve Connection String
AZURE_STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --query connectionString -o tsv)

# 3. Create Private Container
az storage container create \
  --name invoices \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING"
```

---

### Step 3: Configure Database Firewall for Azure Container Apps

Allow Azure services to connect to PostgreSQL:

```bash
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --server-name invoice-review-db \
  --name AllowAllAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

*(Note: `0.0.0.0` to `0.0.0.0` is the special Azure rule that enables internal Azure-to-Azure communication between Azure Container Apps and PostgreSQL, without opening the server to the public internet).*

---

### Step 4: Deploy Backend to Azure Container Apps (Consumption Tier)

```bash
CONTAINER_APP_ENV="env-invoice-review"
CONTAINER_APP_NAME="invoice-review-api"

# 1. Create Managed Environment
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# 2. Deploy Container App with Autoscaling (0 to 2 replicas for $0 idle cost)
az containerapp create \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image "${ACR_LOGIN_SERVER}/invoice-review-backend:latest" \
  --registry-server $ACR_LOGIN_SERVER \
  --registry-username $ACR_USERNAME \
  --registry-password "$ACR_PASSWORD" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 2 \
  --cpu 0.25 \
  --memory 0.5Gi \
  --env-vars \
    PORT="8000" \
    ALLOWED_ORIGINS="http://localhost:5173,http://localhost:4173,https://invoice-review-app.najeebsayyed.in" \
    DATABASE_URL="postgresql+psycopg://Najeeb:<PASSWORD>@invoice-review-db.postgres.database.azure.com:5432/invoice_review?sslmode=require" \
    AZURE_STORAGE_CONNECTION_STRING="$AZURE_STORAGE_CONNECTION_STRING" \
    AZURE_STORAGE_CONTAINER_NAME="invoices" \
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="<your-endpoint>" \
    AZURE_DOCUMENT_INTELLIGENCE_KEY="<your-key>" \
    OPENAI_API_KEY="<your-openai-key>" \
    OPENAI_MODEL="gpt-5.6-terra"

# 3. Get Backend Public URL
BACKEND_URL=$(az containerapp show \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn -o tsv)

echo "Backend Live at: https://${BACKEND_URL}"
curl -s "https://${BACKEND_URL}/health"
```

---

### Step 5: Deploy Frontend to Azure Static Web Apps (Free Tier)

```bash
# 1. Build Frontend Locally with Backend FQDN
cd frontend
export VITE_API_BASE_URL="https://${BACKEND_URL}"
pnpm build
cd ..

# 2. Create Static Web App Resource
az staticwebapp create \
  --name "invoice-review-frontend" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Free

# 3. Retrieve Deployment Token
SWA_TOKEN=$(az staticwebapp secrets list \
  --name "invoice-review-frontend" \
  --resource-group $RESOURCE_GROUP \
  --query properties.apiKey -o tsv)

# 4. Deploy using Azure SWA CLI
npx @azure/static-web-apps-cli deploy ./frontend/dist \
  --deployment-token "$SWA_TOKEN" \
  --env production
```

---

### Step 6: Configure Custom Domain (`invoice-review-app.najeebsayyed.in`)

1. In your DNS manager for `najeebsayyed.in` (e.g. Cloudflare, Namecheap, GoDaddy):
   - Add a **CNAME** record:
     - **Name / Host:** `invoice-review-app`
     - **Target / Value:** `<your-static-web-app-name>.azurestaticapps.net`
     - **TTL:** Automatic / 3600
     - *(If using Cloudflare: set Proxy status to **DNS Only** (Gray Cloud) during domain validation).*
2. In the Azure Portal:
   - Navigate to **Static Web Apps** -> `invoice-review-frontend` -> **Custom domains** -> **+ Add**.
   - Select **Custom domain on other DNS**, enter `invoice-review-app.najeebsayyed.in`.
   - Click **Validate**. Azure validates the CNAME and automatically provisions a DigiCert TLS/SSL certificate with automatic renewal.

---

## 4. Verification & Testing Checklist

- [x] **PostgreSQL Connectivity**: TCP port 5432 verified from current workstation (`TcpTestSucceeded: True`).
- [x] **Application Database**: Database `invoice_review` created in `invoice-review-db` with UTF-8 charset.
- [x] **Database Drivers**: `psycopg[binary]==3.2.5` and pure-Python `pg8000==1.31.2` installed in `pyproject.toml` and `uv.lock`.
- [x] **Firewall Protection**: Azure PostgreSQL firewall restricted to your specific workstation subnet (`152.56.5.0/24`), protecting the server from unauthorized public internet traffic.
- [x] **Health Check**: `GET /health` endpoint ready for Container Apps liveness/startup probes.
- [x] **CORS Configuration**: Dynamic origin resolution supporting `localhost`, `invoice-review-app.najeebsayyed.in`, and `*.azurestaticapps.net`.
- [x] **Client-Side SPA Routing**: `staticwebapp.config.json` configured to prevent 404 errors on page reload.
