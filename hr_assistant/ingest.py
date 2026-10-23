"""PDF -> page-aware chunks -> ChromaDB (local, persistent, idempotent)."""
import hashlib
import json
import sys
from datetime import datetime

from langchain_text_splitters import RecursiveCharacterTextSplitter

from . import config
from .sections import find_heading


class IngestError(Exception):
    pass


def load_pages(pdf_path):
    if not pdf_path.exists():
        raise IngestError(f"PDF not found at {pdf_path}. Put hr_manual.pdf in data/ (or upload it in the app).")
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as e:
        raise IngestError(f"Could not read PDF: {e}") from e
    pages = [(i + 1, (p.extract_text() or "")) for i, p in enumerate(reader.pages)]
    if not any(t.strip() for _, t in pages):
        raise IngestError("PDF has no extractable text (scanned?). OCR it first.")
    return pages


def build_chunks(pages, source="hr_manual.pdf"):
    """Return (texts, metadatas, ids). Section carries over from earlier pages."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)
    texts, metas, ids = [], [], []
    current_section = "Unknown section"
    for page_no, text in pages:
        for idx, chunk in enumerate(splitter.split_text(text)):
            # heading appearing at the top of this chunk applies to it; otherwise inherit
            head = find_heading(chunk)
            section = head or current_section
            if head:
                current_section = head
            digest = hashlib.sha1(f"{source}|{page_no}|{idx}|{chunk}".encode()).hexdigest()[:20]
            texts.append(chunk)
            metas.append({"source": source, "page": page_no, "section": section, "chunk": idx})
            ids.append(digest)
    return texts, metas, ids


def get_store():
    from langchain_chroma import Chroma
    from .embeddings import LocalMiniLM
    return Chroma(collection_name=config.COLLECTION, embedding_function=LocalMiniLM(),
                  persist_directory=str(config.CHROMA_DIR),
                  collection_metadata={"hnsw:space": "cosine"})


def ingest(pdf_path=None):
    pdf_path = pdf_path or config.PDF_PATH
    texts, metas, ids = build_chunks(load_pages(pdf_path), source=pdf_path.name)
    store = get_store()
    # Drop chunks from any previously ingested (different/old) PDF so answers only come from this one.
    current = set(ids)
    stale = [i for i in store.get(include=[])["ids"] if i not in current]
    if stale:
        store.delete(ids=stale)
    existing = set(store.get(ids=ids)["ids"])
    new = [i for i, cid in enumerate(ids) if cid not in existing]
    # upsert everything (ids are content hashes, so no duplicates; metadata such as section names stays current)
    for start in range(0, len(ids), 200):
        store.add_texts(texts[start:start + 200], metadatas=metas[start:start + 200], ids=ids[start:start + 200])
    result = {"pages": len({m["page"] for m in metas}), "chunks": len(ids), "indexed": store._collection.count(),
              "added": len(new), "skipped": len(ids) - len(new), "removed_old": len(stale),
              "completed_at": datetime.now().isoformat(timespec="seconds"), "file": pdf_path.name}
    try:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        (config.CHROMA_DIR / "last_ingest.json").write_text(json.dumps(result))
    except OSError:
        pass
    return result


def last_ingest():
    try:
        return json.loads((config.CHROMA_DIR / "last_ingest.json").read_text())
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    try:
        print(ingest())
    except IngestError as e:
        print(f"Ingestion failed: {e}", file=sys.stderr)
        sys.exit(1)
