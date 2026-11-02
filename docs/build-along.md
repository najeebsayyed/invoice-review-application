# Build-along guide

The complete guided build lives at <https://learn.datalumina.com/docs/invoice-review>. This local guide records the first checkpoint represented by the `main` branch.

## Starter outcome

The repository installs reproducibly, starts a minimal FastAPI service and React interface, and includes the business brief plus fictional source documents.

## Why this boundary exists

The starter removes the completed workflow while preserving every prerequisite needed to build it. You begin with the user, the source documents, and explicit service boundaries instead of reverse-engineering a finished application.

## Commands

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile

cd ..
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
./scripts/dev.sh --check
./scripts/dev.sh
```

## Important locations

- `docs/client-brief.md`: the recurring finance problem and definition of done
- `docs/architecture.md`: the intended boundaries and data flow
- `samples/`: the fictional evaluation corpus and manifest
- `backend/app/main.py`: the initial API boundary
- `frontend/src/App.tsx`: the initial interface boundary

## What you should observe

- `GET http://localhost:8000/health` returns `{"status":"ok"}`.
- `http://localhost:5173` shows the Invoice Review starter screen.
- No Azure request occurs at this checkpoint.

## Checkpoint

- [ ] Locked backend and frontend installs succeed.
- [ ] Backend lint passes.
- [ ] Frontend type-check, lint, and production build pass.
- [ ] `./scripts/dev.sh --check` reports that Invoice Review is ready to start.
- [ ] The health endpoint and starter screen load locally.

## Working slice: Extraction schemas and mapping (invoices & receipts)

### Outcome

Strict, typed Pydantic v2 schemas in `app/schemas/invoice/` and `app/schemas/receipt/` to model Azure AI Document Intelligence extraction for invoices (`prebuilt-invoice`) and receipts (`prebuilt-receipt`). Both schemas support line items, tax breakdowns, confidence scoring, Decimal currency amounts, and unified document aliases.

### Why this boundary exists

Azure SDK objects must not leak across application layers. Isolating the extracted data into explicit Pydantic schemas provides type validation, deterministic field mapping, and safe serialization before passing to finance validation policies.

### Commands

```bash
cd backend
uv run --locked --no-sync ruff check app ../playground
uv run --locked --no-sync python ../playground/run_experiments.py
uv run --locked --no-sync python ../playground/run_invoice.py 01-en-happy-classic.pdf
uv run --locked --no-sync python ../playground/run_receipt.py 13-nl-fuel-receipt.png
```

### Observable result

- `run_experiments.py` runs and passes all 4 verification stages:
  1. Direct instantiation and alias verification of `InvoiceData` and `ReceiptData`.
  2. Live extraction of invoice `01-en-happy-classic.pdf` mapped into `InvoiceData`.
  3. Live extraction of receipt `13-nl-fuel-receipt.png` mapped into `ReceiptData`.
  4. JSON serialization via `model_dump(mode="json")`.

### Checkpoint

- [x] `app/schemas/invoice/` created with `InvoiceData`, `InvoiceItem`, and `InvoiceTaxDetail`.
- [x] `app/schemas/receipt/` created with `ReceiptData`, `ReceiptItem`, and `ReceiptTaxDetail`.
- [x] `DocumentIntelligenceService` updated with `process_receipt` and mapping for both models.
- [x] Ruff lint passes across `app` and `playground`.
- [x] Live experiments verify end-to-end extraction and mapping on sample documents.

## Working slice: OpenAI Document Extraction and Classification Service

### Outcome

A typed, structured `OpenAIService` in `app/services/openai_service.py` that mirrors `DocumentIntelligenceService` by accepting file paths, raw bytes, or binary streams of invoices and receipts (PDF, PNG, JPEG), extracting structured data via OpenAI Responses API, and returning normalized `InvoiceData` and `ReceiptData` domain models. Also provides document classification (`invoice` vs `receipt`) and automatic dispatch via `process_document`.

### Why this boundary exists

OpenAI SDK types and API interactions are encapsulated entirely inside the provider adapter service. Application domain code receives only validated, typed `InvoiceData` and `ReceiptData` models with Decimal amounts, parsed dates, and confidence scores, maintaining identical contracts across extraction providers.

### Commands

```bash
cd backend
uv run --locked --no-sync ruff check app ../playground
uv run --locked --no-sync python test.py
uv run --locked --no-sync python ../playground/run_openai.py 01-en-happy-classic.pdf
uv run --locked --no-sync python ../playground/run_openai.py 13-nl-fuel-receipt.png
```

### Observable result

- `test.py` initializes `OpenAIService` from `.env` (`OPENAI_API_KEY` and `OPENAI_MODEL`) and extracts sample invoice data.
- `run_openai.py` classifies the document, extracts structured fields using strict schema responses, and serializes clean JSON adhering to `InvoiceData` or `ReceiptData`.

### Checkpoint

- [x] `app/services/openai_service.py` created with `OpenAIService` and `OpenAISettings`.
- [x] Unified export in `app/services/__init__.py`.
- [x] Strict structured output parsing for `InvoiceData` and `ReceiptData`.
- [x] Document classification method `classify_document`.
- [x] Interactive playground script `playground/run_openai.py`.
- [x] Ruff checks pass across `app` and `playground`.

## Working slice: Pipeline Step 1 - LLM Document Classification

### Outcome

The initial stage of the document processing pipeline: an LLM-backed `DocumentClassifier` that inspects an uploaded PDF or image file and classifies it as either an `invoice` or `receipt` before deep extraction runs. Wrapped as `ClassificationStep` adhering to the `PipelineStep` protocol and updating an immutable `PipelineContext`.

### Why this boundary exists

Extracting structured financial documents requires different prebuilt models, schemas, and validation policies for invoices versus receipts. Classifying upfront routes the document efficiently, avoids unnecessary token/compute costs, and isolates classification logic from downstream extraction and accounting rules.

### Commands

```bash
cd backend
uv run --locked --no-sync ruff check app ../playground
uv run --locked --no-sync python ../playground/run_classifier.py 01-en-happy-classic.pdf
uv run --locked --no-sync python ../playground/run_classifier.py 13-nl-fuel-receipt.png
```

### Observable result

- `run_classifier.py` runs `ClassificationStep` inside `Pipeline` on sample documents.
- `01-en-happy-classic.pdf` is classified as `invoice` with confidence and reasoning.
- `13-nl-fuel-receipt.png` is classified as `receipt` with confidence and reasoning.
- `PipelineContext` is immutably updated via `model_copy(update={"classification": classification})`.

### Checkpoint

- [x] `app/pipeline/base.py` created with `PipelineContext`, `PipelineStep`, and `Pipeline`.
- [x] `app/pipeline/classification.py` created with `DocumentClassifier`, `DocumentClassification`, `DocumentKind`, and `ClassificationStep`.
- [x] Unified exports in `app/pipeline/__init__.py`.
- [x] `playground/run_classifier.py` playground script created and verified on sample invoices and receipts.
- [x] Ruff checks pass across `app` and `playground`.

## Working slice: Pipeline runner, routed extraction, and Northstar policy validation

### Outcome

A complete document review pipeline runner (`Pipeline`) coordinating:
1. `ClassificationStep`: LLM document classification into `invoice` vs `receipt`.
2. `ExtractionStep`: Dynamic routing to Document Intelligence (`prebuilt-invoice` or `prebuilt-receipt`) with secondary LLM fallback for missing fields, tracking provenance and conflicts.
3. `ValidationStep`: Pure deterministic Northstar finance policy rules (`app/invoices/validation.py`) checking EU VAT via `python-stdnum`, Northstar customer VAT, mandatory fields, math reconciliation within EUR 0.01, duplicate detection, and warning thresholds.

### Why this boundary exists

- Business rules remain pure, testable, and isolated in `app/invoices/validation.py` without leaking Azure or OpenAI SDK dependencies.
- Extraction models are routed dynamically by document kind, preventing mismatched schema parsing and unnecessary cloud compute.
- The pipeline runner threads state via an immutable `PipelineContext`, keeping stages decoupled, inspectable, and extensible for future stages.

### Commands

```bash
cd backend
uv run --locked --no-sync ruff check app ../playground
uv run --locked --no-sync python ../playground/run_pipeline.py 01-en-happy-classic.pdf
uv run --locked --no-sync python ../playground/run_pipeline.py 05-nl-missing-vendor-vat.pdf
uv run --locked --no-sync python ../playground/run_pipeline.py 10-de-duplicate.pdf
uv run --locked --no-sync python ../playground/run_pipeline.py 13-nl-fuel-receipt.png
```

### Observable result

- Individual documents are processed through classification, routed extraction, and Northstar policy validation.
- Valid documents produce `is_valid=True` and status `APPROVED`.
- Non-compliant documents produce typed `ValidationIssue` objects (`code`, `severity`, `field`, `message`) matching evaluation corpus ground truths.

### Checkpoint

- [x] `app/pipeline/base.py` updated with `PipelineContext`, `PipelineStep`, and sequential `Pipeline` runner.
- [x] `app/pipeline/extraction.py` created with `ExtractionStep`, document kind routing, and deterministic merging.
- [x] `app/invoices/validation.py` created with pure Northstar policy rules, EU VAT checksum verification (`python-stdnum`), and typed `ValidationIssue` models.
- [x] `app/pipeline/validation.py` created with `ValidationStep`.
- [x] Unified factory `create_pipeline` in `app/pipeline/__init__.py`.
- [x] `playground/run_pipeline.py` created with single-document and batch evaluation modes.
- [x] Ruff lint checks pass across `app` and `playground`.

## Working slice: General Ledger account categorization step (10-account catalog)

### Outcome

A structured pipeline step (`GlCategorizationStep`) that evaluates normalized invoice or receipt domain models and suggests the most appropriate General Ledger account from Northstar's fixed 10-account catalog (`6100` - `6190`). The suggestion includes an exact catalog enum code, a normalized confidence score (0.0 to 1.0), and a human-readable rationale that Maya (the finance reviewer) can inspect.

### Why this boundary exists

- The GL categorizer receives only normalized domain models (`InvoiceData` or `ReceiptData`), never raw PDF/image bytes or unparsed documents.
- Model output never becomes business policy: the catalog definition and code selection validation live in `app/accounting/catalog.py` and enforce that suggestions strictly match Northstar's chart of accounts.
- The pipeline context preserves the suggestion as advisory metadata (`ctx.gl_suggestion`), leaving final booking approval and override capability in the reviewer's hands.

### Commands

```bash
cd backend
uv run --locked --no-sync ruff check app ../playground
uv run --locked --no-sync python ../playground/run_pipeline.py 01-en-happy-classic.pdf
uv run --locked --no-sync python ../playground/run_pipeline.py 02-nl-happy-compact.pdf
uv run --locked --no-sync python ../playground/run_pipeline.py 13-nl-fuel-receipt.png
```

### Observable result

- Step 4 (`[Step 4: GL Account Suggestion]`) runs as the final pipeline stage.
- `01-en-happy-classic.pdf` (Bright Spark Europe) &rarr; `6110 - Building maintenance` (or electrical).
- `02-nl-happy-compact.pdf` (Helder Schoonmaak) &rarr; `6100 - Cleaning services` with high confidence.
- `13-nl-fuel-receipt.png` (North Sea Fuel) &rarr; `6170 - Travel and transport` with high confidence.
- Clear, readable reason strings explaining the selection rationale for human review.

### Checkpoint

- [x] Fixed 10-account Northstar GL catalog and selection validator created in `app/accounting/catalog.py`.
- [x] Pydantic suggestion and selection schemas created in `app/accounting/schemas.py`.
- [x] Accounting exports unified in `app/accounting/__init__.py`.
- [x] `GlCategorizer` and `GlCategorizationStep` implemented in `app/pipeline/gl_categorization.py`.
- [x] `PipelineContext` updated with `gl_suggestion: GlSuggestion | None`.
- [x] `create_pipeline` factory updated to include `GlCategorizationStep`.
- [x] `playground/run_pipeline.py` updated to display Step 4 GL suggestions.
- [x] Ruff lint checks pass cleanly across `app` and `playground`.

## Working slice: Vite React frontend, upload-to-processing workflow, and single dev script

### Outcome

A modern, responsive React single-page interface using Vite, TypeScript strict, and Tailwind CSS v4 that connects to the backend API:
- `WelcomePortal`: Guides Maya through the review workflow with "Review a document" and "View history" actions.
- `UploadStep`: Drag-and-drop document upload with instant browser client-side preview (`DocumentPreview` via `FileReader` data URLs for PDF and images) and 4 MB validation before server submission.
- `ProcessingStep`: Real-time visual progress indicator illustrating pipeline stages (Classification → Extraction → Policy validation → GL suggestion).
- `DocumentReview`: Full split-screen view showing original document binary on the left and extracted data, Northstar policy issues (errors/warnings), and GL account selection on the right.
- `DocumentInbox`: Persistent review history with status badges, amount formatting, and document deletion.
- Unified dev scripts (`scripts/dev.sh` and `scripts/dev.ps1`) to run both the FastAPI backend and Vite frontend concurrently in a single terminal.

### Why this boundary exists

- The frontend reads the backend URL exclusively through `src/lib/env.ts` (`VITE_API_BASE_URL`).
- All HTTP requests go through a typed API client (`src/lib/api.ts`) using native `fetch`.
- Complex multi-step review workflow is driven by pure state machines in React (`useState`, `useCallback`) without external state bloat.

### Commands

```bash
# Frontend validation
cd frontend
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build

# Run both backend and frontend concurrently
cd ..
./scripts/dev.sh          # Linux / macOS / Git Bash
.\scripts\dev.ps1         # Windows PowerShell
```

### Observable result

- Vite frontend starts on `http://localhost:5173` and connects to FastAPI backend on `http://localhost:8000`.
- Uploading a PDF or image renders a live preview, dispatches `POST /api/documents` to run the 4-step pipeline, and opens the interactive review screen.
- The reviewer can inspect findings, change the GL account from the Northstar catalog, approve or reject, and review past history.

### Checkpoint

- [x] HTML entry point created at `frontend/index.html` with favicon in `frontend/public/favicon.svg`.
- [x] Tailwind CSS v4 styling configured in `frontend/src/index.css`.
- [x] Environment configuration established in `frontend/src/lib/env.ts` and `frontend/.env`.
- [x] Type definitions in `frontend/src/lib/types.ts` matching backend responses.
- [x] Native `fetch` API client created in `frontend/src/lib/api.ts`.
- [x] Reusable UI components created in `frontend/src/components/ui/` (`Button`, `Card`, `Badge`, `Dialog`, `ConfirmDialog`).
- [x] Step components created: `WelcomePortal`, `UploadStep`, `ProcessingStep`, `DocumentPreview`, `DocumentReview`, `DocumentInbox`.
- [x] Root workflow assembled in `frontend/src/App.tsx`.
- [x] Concurrent development scripts created in `scripts/dev.sh` and `scripts/dev.ps1`.
- [x] TypeScript compilation, ESLint, and production build pass with zero errors.

## Working slice: Human review flow, hybrid extraction with provenance, and corpus evaluators

### Outcome

A comprehensive human-in-the-loop review workflow empowering Maya to inspect evidence, correct extracted fields, generate supplier correction emails, and evaluate the full golden corpus:
- **Field Provenance & Conflicts**: Every extracted field displays its origin pill (`Doc Intelligence` primary, `OpenAI fallback` secondary, or `Manual edit` user) with conflict badges when readings differed.
- **Inline Field Corrections & Revalidation**: Reviewers can edit extracted fields directly in the UI. Saving dispatches `PUT /api/documents/{id}/corrections`, which updates `ReviewData`, tags field provenance as `user`, re-runs pure Northstar validation rules, and clears resolved errors in real time.
- **On-Demand Supplier Correction Email Drafting**: Reviewers can click "Draft correction email" to invoke Azure OpenAI (`POST /api/documents/{id}/correction-email`) with strict structured outputs, producing a polite, professional email detailing the exact discrepancies found with Copy Subject, Copy Body, and Copy Entire Email actions. The app never connects to email infrastructure or sends emails automatically.
- **Corpus Evaluation Goal**: Created `backend/scripts/evaluate_corpus.py` and `backend/scripts/evaluate_hybrid.py` to benchmark all 13 multilingual documents against `samples/manifest.json`.

### Why this boundary exists

- Document Intelligence remains primary; the secondary LLM fills missing fields without overwriting primary values.
- Model suggestions and email drafts remain advisory. A person decides whether to approve, reject, or request a supplier correction.
- Manual field corrections re-run pure Python validation rules deterministically without invoking cloud APIs or introducing side effects.
- Fictional corpus evaluators provide reproducible, live cloud verification without automated unit tests or test frameworks.

### Commands

```bash
# Backend code quality
cd backend
uv run --locked --no-sync ruff check app scripts ../playground

# Frontend verification
cd ../frontend
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build

# Corpus and hybrid evaluations
cd ../backend
uv run --locked --no-sync python scripts/evaluate_hybrid.py
uv run --locked --no-sync python scripts/evaluate_corpus.py
```

### Observable result

- Step 3 (Review screen) surfaces field provenance tags and conflict indicators on every document attribute.
- Editing an invalid field (e.g., correcting an invalid German VAT ID on `06-de-invalid-vendor-vat.pdf`) revalidates the document, clears the error, and transitions status from `needs_review` to `ready`.
- Clicking "Draft correction email" renders a dialog with an AI-crafted email addressing the specific validation findings with copy-to-clipboard functionality.
- `evaluate_hybrid.py` executes dual extraction against Document Intelligence and Azure OpenAI, reporting fallbacks and conflicts on `02-nl-happy-compact.pdf` and `13-nl-fuel-receipt.png`.

### Checkpoint

- [x] Schema extensions: `provenance` and `conflicts` in `ReviewData`, `FieldCorrectionRequest`, and `CorrectionEmailResponse`.
- [x] Backend domain & repository: `save_corrections` in repository and `apply_corrections` in `DocumentService` with pure revalidation.
- [x] Azure OpenAI email provider: `draft_correction_email` in `OpenAIService` using structured outputs.
- [x] API routes: `PUT /api/documents/{id}/corrections` and `POST /api/documents/{id}/correction-email`.
- [x] Frontend typed API client: `updateCorrections` and `draftCorrectionEmail` in `api.ts`.
- [x] Frontend UI: Inline field editing, provenance & conflict pills, and modal dialog for supplier correction emails in `DocumentReview.tsx`.
- [x] Golden corpus evaluators created: `backend/scripts/evaluate_corpus.py` and `backend/scripts/evaluate_hybrid.py`.
- [x] Ruff lint passes across `app`, `scripts`, and `playground`.
- [x] Frontend TypeScript typecheck, ESLint, and production build pass with zero errors.

## Hardened Validation, File Signatures, and Aggregate Metrics

### Outcome

Hardened backend file upload validation with magic-byte binary signature inspection, preventing spoofed MIME types. Added aggregate KPI metrics endpoint (`/api/documents/stats`) providing document counts by status and total approved spend in EUR. Extended `list_documents` with search, status filtering, sorting, and pagination.

### Why this boundary exists

- MIME type headers (`Content-Type`) sent by HTTP clients can easily be forged or spoofed. Magic-byte inspection verifies binary headers (`%PDF`, `\x89PNG`, `\xff\xd8\xff`) directly from the binary payload before passing it to parser services.
- Financial dashboards require high-level operational insights (KPIs like total documents, spend, and pending reviews) without pulling the entire database client-side.
- Clean database queries with deterministic sorting and filtering keep the API production-ready as document volumes grow.

### Commands

```bash
cd backend
uv run --locked --no-sync ruff check app scripts ../playground
```

### Observable result

- Corrupted files or spoofed extensions (e.g. text file renamed to `.pdf`) trigger a clear 422 HTTP validation error with the invalid magic signature detail.
- `GET /api/documents/stats` returns accurate aggregate counts (`total_documents`, `needs_review_count`, `ready_count`, `approved_count`, `rejected_count`, `total_spend`).
- `GET /api/documents?status=needs_review&search=euro` filters documents deterministically.

### Checkpoint

- [x] File signature verification function `validate_file_magic_bytes` in `routes.py`.
- [x] Aggregate metrics schema `DocumentStatsResponse` in `schemas.py`.
- [x] Aggregate metrics query `get_stats()` in `repository.py` and `service.py`.
- [x] Search, filter, and pagination parameters in `list()` and `GET /api/documents`.
- [x] Ruff lint passes across all backend code with zero warnings.

Continue with the [online tutorial](https://learn.datalumina.com/docs/invoice-review).
