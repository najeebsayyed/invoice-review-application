# Azure Infrastructure & Deployment Status: Invoice Review AI

This document records the **active deployed Azure infrastructure** and provides the remaining steps for frontend deployment and custom domain setup.

---

## 1. Live Infrastructure Overview

| Component | Azure Resource Name | Type / SKU | Live Endpoint / Value |
| :--- | :--- | :--- | :--- |
| **Subscription** | Azure for Students | Enabled | Active 1-year student benefit |
| **Resource Group** | `rg-invoice-review` | Standard | Location: `centralindia` |
| **PostgreSQL Server** | `invoice-review-db` | Burstable `Standard_B1ms` (32 GB) | `invoice-review-db.postgres.database.azure.com:5432` |
| **Application DB** | `invoice_review` | UTF-8, en_US.utf8 | Verified with `documents` schema |
| **Container Registry** | `acrinvoicereview` | Basic SKU | `acrinvoicereview.azurecr.io` |
| **Container Apps Env** | `env-invoice-review` | Serverless / Consumption | Central India (`greenmushroom-2b5a71a4`) |
| **Backend API** | `invoice-review-api` | 0.25 vCPU, 0.5 GiB (0–2 replicas) | **`https://invoice-review-api.greenmushroom-2b5a71a4.centralindia.azurecontainerapps.io`** |
| **Blob Storage** | `stginvoicereview` | Standard LRS (Hot) | Private container: `invoices` |
| **Frontend** | `invoice-review-frontend` | Azure Static Web Apps (Free) | *(Ready for deployment once pushed)* |
| **Custom Domain** | `invoice-review-app.najeebsayyed.in` | CNAME via Cloudflare | *(Ready for DNS validation)* |

---

## 2. Backend Health & Verification

The live backend has been verified in Azure:
```bash
# Health check
curl -i "https://invoice-review-api.greenmushroom-2b5a71a4.centralindia.azurecontainerapps.io/health"
# Status: HTTP 200 OK {"status": "ok"}

# General Ledger Accounts
curl -s "https://invoice-review-api.greenmushroom-2b5a71a4.centralindia.azurecontainerapps.io/api/accounting/gl-accounts"
# Returns all 10 Northstar General Ledger accounts

# Workspace-Scoped Query (Live PostgreSQL Flexible Server)
curl -s -H "X-Workspace-ID: 11111111-1111-4111-8111-111111111111" "https://invoice-review-api.greenmushroom-2b5a71a4.centralindia.azurecontainerapps.io/api/documents"
# Returns []
```

---

## 3. Remaining Frontend Deployment Steps

Your backend is live and waiting. Follow these simple steps to deploy your frontend and attach your custom domain:

### Step 1: Review and Push Changes to GitHub

Review your changes and push them to your repository:
```powershell
git add .
git commit -m "feat: complete Azure cloud deployment for backend API"
git push origin main
```

---

### Step 2: Deploy Frontend to Azure Static Web Apps (Free Tier)

You can deploy the frontend via the **Azure Portal** (recommended with GitHub Actions) or via **Azure CLI**:

#### Option A: GitHub Actions via Azure Portal (Continuous Deployment)
1. In the [Azure Portal](https://portal.azure.com), search for **Static Web Apps** and click **+ Create**.
2. Select:
   - **Subscription:** `Azure for Students`
   - **Resource Group:** `rg-invoice-review`
   - **Name:** `invoice-review-frontend`
   - **Plan type:** `Free`
   - **Region:** `Central India` (or nearest available)
3. Under **Deployment details**:
   - Source: **GitHub** (sign in and select your repository `invoice-review`, branch `main`).
   - Build Presets: **Custom**
   - **App location:** `/frontend`
   - **Api location:** *(leave empty)*
   - **Output location:** `dist`
4. Click **Review + create**, then **Create**.
5. Once created, in the Azure Portal open your Static Web App -> **Environment variables** (or in GitHub repo secrets):
   - Add: `VITE_API_BASE_URL` = `https://invoice-review-api.greenmushroom-2b5a71a4.centralindia.azurecontainerapps.io`
   - Save. GitHub Actions will build and deploy your site in ~1 minute.

#### Option B: Deploy via Azure CLI (Immediate Local Deploy)
```powershell
# 1. Create Static Web App resource in Azure
az staticwebapp create `
  --name "invoice-review-frontend" `
  --resource-group "rg-invoice-review" `
  --location "centralindia" `
  --sku Free

# 2. Retrieve Deployment Token
$SWA_TOKEN = (az staticwebapp secrets list `
  --name "invoice-review-frontend" `
  --resource-group "rg-invoice-review" `
  --query properties.apiKey -o tsv)

# 3. Deploy pre-built production dist folder
npx @azure/static-web-apps-cli deploy ./frontend/dist `
  --deployment-token "$SWA_TOKEN" `
  --env production
```

---

### Step 3: Link Custom Domain (`invoice-review-app.najeebsayyed.in`)

1. **Add CNAME Record in Cloudflare (or your DNS manager):**
   Log into Cloudflare for `najeebsayyed.in` and add:
   - **Type:** `CNAME`
   - **Name / Host:** `invoice-review-app`
   - **Target / Value:** `<your-app-name>.azurestaticapps.net` *(the default hostname of your Static Web App)*
   - **Proxy status:** **DNS Only** (Gray cloud — required during Azure validation)
   - **TTL:** Auto

2. **Add Custom Domain in Azure:**
   - In Azure Portal, open **Static Web Apps** -> `invoice-review-frontend` -> **Custom domains** -> **+ Add**.
   - Select **Custom domain on other DNS**.
   - Enter `invoice-review-app.najeebsayyed.in` and click **Validate**.
   - Azure validates the CNAME and automatically requests and installs a free DigiCert TLS/SSL certificate.

3. *(Optional)* In Cloudflare, once validated and active, you can re-enable the Orange cloud (Proxied) for CDN acceleration.

---

## 4. Cost Optimization & Management Tips

- **Container Apps Autoscaling:** `invoice-review-api` is configured with `min-replicas: 0`. When no visitor is using the application, the backend scales to 0 instances and consumes **\$0**.
- **PostgreSQL Flexible Server:** To preserve student credits when not demoing the portfolio app:
  ```powershell
  # Stop server when not in use:
  az postgres flexible-server stop --resource-group rg-invoice-review --name invoice-review-db

  # Start server before testing / demoing:
  az postgres flexible-server start --resource-group rg-invoice-review --name invoice-review-db
  ```
- **Storage:** Azure Storage Account `stginvoicereview` uses Standard LRS with public access disabled, well within the 5 GB student tier.
