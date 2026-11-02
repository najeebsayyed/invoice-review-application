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

Continue with the [online tutorial](https://learn.datalumina.com/docs/invoice-review).
