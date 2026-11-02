"""Playground script to test LLM document classification and the ClassificationStep pipeline."""

import json
import subprocess
import sys
from pathlib import Path

# Paths
PLAYGROUND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PLAYGROUND_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"

# If invoked with system python, automatically delegate to backend virtual environment python
if VENV_PYTHON.is_file() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    sys.exit(subprocess.call([str(VENV_PYTHON), *sys.argv]))

# Ensure backend directory is in sys.path
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.pipeline import ClassificationStep, Pipeline, PipelineContext  # noqa: E402


def resolve_document_path() -> Path:
    """Resolve sample document path from command line arguments or default sample."""
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if target.is_file():
            return target
        candidate = PROJECT_ROOT / "samples" / "generated" / sys.argv[1]
        if candidate.is_file():
            return candidate

    # Default to 01-en-happy-classic.pdf
    default_sample = PROJECT_ROOT / "samples" / "generated" / "01-en-happy-classic.pdf"
    if not default_sample.is_file():
        raise FileNotFoundError(f"Sample document not found at {default_sample}")
    return default_sample


def main() -> None:
    sample_file = resolve_document_path()
    print("=== Pipeline Step 1: LLM Document Classifier ===")
    print(f"Document File: {sample_file.resolve()}\n")

    # 1. Initialize PipelineContext with the uploaded file
    context = PipelineContext(document_path=sample_file)
    print(f"Initial Context: document_path='{context.document_path.name}'")

    # 2. Build pipeline with ClassificationStep as step 1
    classification_step = ClassificationStep()
    pipeline = Pipeline(steps=[classification_step])
    print(f"Configured Pipeline with steps: {[step.name for step in pipeline.steps]}")

    # 3. Execute pipeline
    print("\nRunning pipeline...")
    result_context = pipeline.run(context)

    # 4. Inspect classification result
    classification = result_context.classification
    if classification:
        print("\n--- Classification Result ---")
        print(f"Document Kind : {classification.document_kind}")
        print(f"Document Type : {classification.document_type}")
        print(f"Confidence    : {classification.confidence}")
        print(f"Reasoning     : {classification.reasoning}")

        print("\n--- Pipeline Context JSON ---")
        print(json.dumps(result_context.model_dump(mode="json"), indent=2))
        print("\n[PASS] Pipeline step 1 (Classification) executed successfully!")
    else:
        print("\n[FAIL] No classification returned in pipeline context.")
        sys.exit(1)


if __name__ == "__main__":
    main()
