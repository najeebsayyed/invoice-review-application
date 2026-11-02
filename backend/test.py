"""Quick verification script for OpenAI connection and OpenAIService."""

from pathlib import Path

from dotenv import load_dotenv

from app.services.openai_service import OpenAIService, OpenAISettings

# Load variables from backend .env
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_FILE)

settings = OpenAISettings()

# Validate configuration
if not settings.openai_api_key or settings.openai_api_key == "your_openai_api_key":
    raise ValueError("Please set your actual OPENAI_API_KEY in .env")

if not settings.openai_model or settings.openai_model == "model_to_use":
    raise ValueError("Please set a valid OPENAI_MODEL in .env")

# Initialize OpenAIService
service = OpenAIService()
print(f"OpenAI service initialized successfully using model: {service.model}")

# Run a quick extraction test on the sample invoice if available
sample_invoice = Path(__file__).resolve().parents[1] / "samples" / "generated" / "01-en-happy-classic.pdf"
if sample_invoice.is_file():
    print(f"\nExtracting sample invoice: {sample_invoice.name}...")
    invoice = service.process_invoice(sample_invoice)
    print(f"Vendor Name   : {invoice.vendor_name}")
    print(f"Vendor VAT ID : {invoice.vendor_vat_id}")
    print(f"Invoice Total : {invoice.invoice_total} {invoice.currency}")
    print(f"Line Items    : {len(invoice.items)}")
    print(f"Confidence    : {invoice.confidence}")
    print("\nExtraction test PASSED!")
else:
    print(f"Sample file not found at {sample_invoice}, skipping document extraction test.")
