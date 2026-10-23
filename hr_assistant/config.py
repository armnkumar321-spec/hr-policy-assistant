import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:  # dotenv optional for tests
    pass


def _path(var, default):
    p = Path(os.getenv(var, default))
    return p if p.is_absolute() else ROOT / p


PDF_PATH = _path("PDF_PATH", "data/hr_manual.pdf")
CHROMA_DIR = _path("CHROMA_DIR", "chroma_db")
COLLECTION = "hr_manual"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
TOP_K = 5
NOT_FOUND = "Not found"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()


def gemini_key():
    """Read at call time so a key added to .env after start-up is picked up on restart. Never logged."""
    k = os.getenv("GEMINI_API_KEY", "").strip()
    return "" if (not k or k == "your_gemini_api_key_here") else k
