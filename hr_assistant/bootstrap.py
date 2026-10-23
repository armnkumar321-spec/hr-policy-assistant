"""Production bootstrap: fetch the publicly hosted manual and build the index when the server starts empty.

Hosts such as Streamlit Community Cloud have temporary disks, so the PDF and ChromaDB index are rebuilt after
each restart. The PDF is downloaded from the publisher's own URL (PDF_URL) and is never committed to git."""
import os
import urllib.request

from . import config

DEFAULT_PDF_URL = "https://www.ensogroup.com/wp-content/themes/ensogroup/assets/images/enso-images/hr_manual.pdf"


def pdf_url():
    return os.getenv("PDF_URL", DEFAULT_PDF_URL).strip()


def download_pdf(url=None, dest=None, timeout=60):
    """Download the manual to data/hr_manual.pdf. Validates it is a PDF; never overwrites an existing file."""
    dest = dest or config.PDF_PATH
    if dest.exists():
        return dest
    url = url or pdf_url()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (HR Policy Assistant)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"Downloaded file from {url} is not a PDF")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".download")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def ensure_ready():
    """Make sure the PDF exists and is indexed. Returns a short status string."""
    from .ingest import get_store, ingest
    steps = []
    if not config.PDF_PATH.exists() and os.getenv("AUTO_DOWNLOAD_PDF", "1") == "1":
        download_pdf()
        steps.append("downloaded manual")
    if config.PDF_PATH.exists() and get_store()._collection.count() == 0:
        res = ingest()
        steps.append(f"indexed {res['pages']} pages / {res['indexed']} chunks")
    return ", ".join(steps) or "ready"
