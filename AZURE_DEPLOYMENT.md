# Azure Deployment Guide: Invoice Review AI

This guide walks you step-by-step through deploying the **Invoice Review AI** application to **Microsoft Azure** using an **Azure for Students** subscription (or standard Azure subscription), maximizing free-tier allowances and keeping monthly costs at **\$0** or pennies.

---

## 1. Target Architecture & Free-Tier Map

| Component | Azure Service | Tier / SKU | Student / Free-Tier Benefit |
| :--- | :--- | :--- | :--- |
| **Frontend** | Azure Static Web Apps | **Free** | Unlimited bandwidth, custom domains, free auto-renewing SSL |
| **Backend** | Azure Container Apps | **Consumption (Serverless)** | 180,000 vCPU-seconds + 360,000 GiB-seconds free every month |
| **Container Registry** | Azure Container Registry | **Basic** | Low storage cost; included in student credit allowance |
| **Database** | Azure Database for PostgreSQL Flexible Server | **Burstable `Standard_B1ms`** | 12 months free on Azure for Students (up to 750 hrs/month + 32GB) |
| **File Storage** | Azure Blob Storage | **Standard LRS (Hot/Cool)** | 5GB LRS free storage for 12 months |
| **Document AI** | Azure AI Document Intelligence | **F0 (Free) or S0** | 500 pages free per month on F0 tier |
| **AI Review** | OpenAI API / Azure OpenAI | **Pay-as-you-go** | Consumes only input/output tokens per review |
| **Custom Domain** | `invoice-review-app.najeebsayyed.in` | **CNAME mapping** | Managed SSL certificate handled automatically by Azure |

---

## 2. Production Python Dependencies (Proposals)

The application code is designed with graceful fallbacks:
- If running without PostgreSQL or Azure Blob Storage drivers, the system uses **SQLite** and **local disk storage**.
- For production on Azure PostgreSQL and Azure Blob Storage, the following packages are proposed:

1. **`psycopg[binary]==3.2.5`**
   - *Reason:* High-performance, binary C-extension DBAPI driver for PostgreSQL required by SQLAlchemy 2.0 to communicate with Azure Database for PostgreSQL Flexible Server.
2. **`azure-storage-blob==12.24.1`**
   - *Reason:* Official Microsoft Azure Storage SDK providing resilient chunked upload/download and blob management for documents in Azure Container Apps.

To add them to the locked backend environment when ready:
```powershell
cd backend
uv add "psycopg[binary]==3.2.5" "azure-storage-blob==12.24.1"
```

---

## 3. Step-by-Step Deployment Walkthrough

### Prerequisites

1. Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli).
2. Authenticate with your Azure for Students account:
   ```bash
   az login
   ```
3. Verify your active subscription:
   ```bash
   az account show --output table
   ```

---

### Step 1: Create Resource Group & Define Variables

Set shell variables to keep resource names consistent and organized:

```bash
# Variables
RESOURCE_GROUP="rg-invoice-review"
LOCATION="eastus"              # 'eastus', 'centralus', or 'westeurope' have full free-tier coverage
ACR_NAME="acrinvoicereview$RANDOM"
STORAGE_ACCOUNT="stginvoicereview$RANDOM"
CONTAINER_APP_ENV="env-invoice-review"
CONTAINER_APP_NAME="invoice-review-api"
POSTGRES_SERVER="pg-invoice-review-$RANDOM"
DB_NAME="invoicedb"
DB_USER="northstar_admin"
DB_PASSWORD="ChangeThisPassword123!"  # Replace with a strong secret

# Create Resource Group
az group create --name $RESOURCE_GROUP --location $LOCATION
```

---

### Step 2: Provision Azure Blob Storage (Document Persistence)

Azure Container Apps containers have ephemeral disks. Persistent documents are stored in Azure Blob Storage:

```bash
# 1. Create Storage Account
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

# 3. Create 'invoices' Blob Container
az storage container create \
  --name invoices \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING"
```

---

### Step 3: Provision Azure Database for PostgreSQL (Flexible Server)

Azure for Students includes 750 hours/month of `Standard_B1ms` PostgreSQL with 32 GB storage:

```bash
# 1. Create PostgreSQL Flexible Server (Burstable B1ms)
az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --location $LOCATION \
  --admin-user $DB_USER \
  --admin-password "$DB_PASSWORD" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --database-name $DB_NAME \
  --yes

# 2. Allow Azure Internal Services Through Firewall (Required for Container Apps)
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --rule-name AllowAllAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# 3. Formulate Database URL
DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${POSTGRES_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require"
```

> [!TIP]
> To preserve student credits during long periods of inactivity, you can pause the PostgreSQL server:
> `az postgres flexible-server stop --resource-group $RESOURCE_GROUP --name $POSTGRES_SERVER`
> and resume when needed:
> `az postgres flexible-server start --resource-group $RESOURCE_GROUP --name $POSTGRES_SERVER`.

---

### Step 4: Build and Push Backend Container to Azure Container Registry (ACR)

```bash
# 1. Create Azure Container Registry (Basic SKU)
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true

# 2. Retrieve ACR Credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)

# 3. Build Container Image Directly in the Cloud (no local Docker required)
az acr build \
  --registry $ACR_NAME \
  --image invoice-review-backend:latest \
  --file backend/Dockerfile \
  backend/
```

---

### Step 5: Deploy Backend to Azure Container Apps (Serverless Consumption)

```bash
# 1. Create Container Apps Managed Environment
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# 2. Deploy Container App with Autoscaling (0 to 2 replicas for zero-cost idle)
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
    DATABASE_URL="$DATABASE_URL" \
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

### Step 6: Deploy Frontend to Azure Static Web Apps (Free Tier)

Azure Static Web Apps provides global CDN distribution and native SSL at \$0/month.

#### Option A: Deploy via Azure CLI

```bash
# 1. Build the Frontend Locally with Production API Base URL
cd frontend
# Set VITE_API_BASE_URL to point to your live Container App:
export VITE_API_BASE_URL="https://${BACKEND_URL}"
pnpm build
cd ..

# 2. Create the Static Web App Resource
az staticwebapp create \
  --name "invoice-review-frontend" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Free

# 3. Retrieve Deployment Token
SWA_DEPLOYMENT_TOKEN=$(az staticwebapp secrets list \
  --name "invoice-review-frontend" \
  --resource-group $RESOURCE_GROUP \
  --query properties.apiKey -o tsv)

# 4. Deploy Dist Directory using SWA CLI
npx @azure/static-web-apps-cli deploy ./frontend/dist \
  --deployment-token "$SWA_DEPLOYMENT_TOKEN" \
  --env production
```

#### Option B: Deploy via GitHub Actions (Recommended for CI/CD)

1. In the **Azure Portal**, go to **Static Web Apps** -> **Create**.
2. Select your Resource Group, Subscription, and choose **Free** plan.
3. Link your GitHub repository (`invoice-review`).
4. In **Build Details**:
   - **App location**: `/frontend`
   - **Api location**: *(leave empty)*
   - **Output location**: `dist`
5. In your GitHub repository settings, under **Secrets and variables** -> **Actions** -> **Environment variables**:
   - Add `VITE_API_BASE_URL` = `https://<your-container-app-fqdn>`
6. The GitHub Actions workflow will automatically build and publish your frontend on every push to `main`.

---

### Step 7: Configure Custom Domain (`invoice-review-app.najeebsayyed.in`)

To point `invoice-review-app.najeebsayyed.in` to Azure Static Web Apps:

#### 1. In Azure Portal / Azure CLI
Run:
```bash
az staticwebapp hostname set \
  --name "invoice-review-frontend" \
  --resource-group $RESOURCE_GROUP \
  --hostname "invoice-review-app.najeebsayyed.in"
```
Or in the Azure Portal:
1. Open your **Static Web App** (`invoice-review-frontend`).
2. Click **Custom domains** in the sidebar.
3. Click **+ Add** -> select **Custom domain on other DNS**.
4. Enter `invoice-review-app.najeebsayyed.in` and click **Next**.

#### 2. Configure DNS Records in your DNS Provider (Cloudflare / Namecheap / GoDaddy)

Add the following record in your DNS manager for `najeebsayyed.in`:

| Type | Name / Host | Target / Value | TTL | Proxy Status |
| :--- | :--- | :--- | :--- | :--- |
| **CNAME** | `invoice-review-app` | `<your-static-web-app-name>.azurestaticapps.net` | Auto / 3600 | DNS Only (Gray Cloud if Cloudflare) |

*(If Azure asks for validation token before CNAME propagation)*:
| Type | Name / Host | Value | TTL |
| :--- | :--- | :--- | :--- |
| **TXT** | `_dnsauth.invoice-review-app` | `<validation-code-provided-by-azure>` | Auto / 3600 |

#### 3. Automatic SSL Certificate
Once the CNAME record is validated:
- Azure automatically requests and provisions a DigiCert TLS/SSL certificate.
- Status changes to **Validated** with **Auto-renewing SSL certificate**.
- Your app is now live with HTTPS at `https://invoice-review-app.najeebsayyed.in`!

---

## 4. Production Security & CORS Checklist

- [x] **Origins Allowed**: The backend allows `https://invoice-review-app.najeebsayyed.in`, `http://localhost:5173`, and any `*.azurestaticapps.net` URL via regex.
- [x] **Workspace Isolation**: `X-Workspace-ID` header is passed on every fetch and allowed across CORS preflights (`OPTIONS`).
- [x] **Database Security**: PostgreSQL Flexible Server firewall only permits internal Azure traffic (`0.0.0.0`) and requires SSL encryption (`sslmode=require`).
- [x] **Secrets Management**: No API keys or connection strings are stored in code or Docker images (`.dockerignore` blocks `.env`).
- [x] **Storage Privacy**: Azure Blob container `invoices` has public access disabled; files can only be accessed through the authenticated workspace API.
- [x] **SPA Routing**: `frontend/public/staticwebapp.config.json` routes all client-side navigation (`/history`, `/`, etc.) to `/index.html` without 404 errors.

---

## 5. Verification & Testing Checklist

Once deployed, run through this verification checklist:

1. **Backend Health Check**:
   ```bash
   curl -i "https://${BACKEND_URL}/health"
   # Expected: HTTP 200 OK {"status":"ok"}
   ```
2. **Frontend Availability**:
   Open `https://invoice-review-app.najeebsayyed.in` in your browser. Confirm the dashboard loads and displays Northstar branding.
3. **Workspace Isolation Test**:
   - Open `https://invoice-review-app.najeebsayyed.in` in a standard browser window (Device A).
   - Upload a sample invoice. Observe AI processing, classification, and validation.
   - Open `https://invoice-review-app.najeebsayyed.in` in an Incognito / Private window (Device B).
   - Check the **History** tab: Device B sees an empty history. Device A's invoice is completely isolated.
4. **Decisions & Corrections**:
   - On Device A, select a GL account, approve or reject an invoice, and test **Draft Correction Email**.
   - Verify changes persist across page refresh.

---

## 6. Resource Clean-Up Commands

If you ever wish to tear down all resources to prevent any accidental charges:

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```
