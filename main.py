# Root-level shim — lets you run `python -m uvicorn main:app` from the project root.
# The actual FastAPI app lives in ./python_backend/main.py.
# This file is NOT deployed to Vercel (see .vercelignore).
from python_backend.main import app  # noqa: F401  (re-exported for uvicorn)
