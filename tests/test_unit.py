"""Fast tests: no PDF, no model download needed."""
from pathlib import Path
import pytest
from langchain_core.documents import Document

from hr_assistant import config
from hr_assistant.ingest import build_chunks, load_pages, IngestError
from hr_assistant.rag import answer, normalize


class FakeStore:
    def __init__(self, docs): self.docs = docs
    def similarity_search(self, q, k=5): return self.docs[:k]


DOCS = [Document(page_content="Leave Policy\nPermanent employees are entitled to 30 days of Privilege Leave (PL) per year.",
                 metadata={"page": 12, "section": "Leave Policy"})]


def test_missing_pdf():
    with pytest.raises(IngestError):
        load_pages(Path("/nonexistent/hr_manual.pdf"))


def test_chunks_keep_pages_and_stable_ids():
    pages = [(1, "1. Leave Policy\n" + "word " * 400), (2, "More text here about benefits.")]
    t1, m1, i1 = build_chunks(pages)
    t2, m2, i2 = build_chunks(pages)
    assert i1 == i2 and len(set(i1)) == len(i1)
    assert {m["page"] for m in m1} == {1, 2}
    assert m1[0]["section"].startswith("1. Leave Policy")


def test_not_found_exact():
    assert answer("What is the current GST rate in India?", store=FakeStore(DOCS))["answer"] == "Not found"
    assert answer("", store=FakeStore(DOCS))["answer"] == "Not found"
    assert normalize("not found.") == "Not found"


def test_supported_answer_has_citation():
    a = answer("How many days of Privilege Leave (PL) does a permanent employee get per year?", store=FakeStore(DOCS))["answer"]
    assert "30 days" in a and "[p. 12, Leave Policy]" in a


def test_llm_not_found_is_normalized():
    class LLM:
        def invoke(self, p): return type("R", (), {"content": "Not found."})()
    r = answer("How many days of Privilege Leave (PL) per year?", store=FakeStore(DOCS), llm=LLM())
    assert r == {"answer": "Not found", "sources": []}


def test_llm_error_falls_back_to_grounded_extractive():
    class Broken:
        def invoke(self, p): raise RuntimeError("no network")
    r = answer("How many days of Privilege Leave (PL) per year?", store=FakeStore(DOCS), llm=Broken())
    assert "30 days" in r["answer"] and "warning" in r


def test_placeholder_key_is_not_a_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_api_key_here")
    assert config.gemini_key() == ""


def test_real_pdf_loading(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter(); w.add_blank_page(width=200, height=200)
    p = tmp_path / "blank.pdf"; w.write(str(p))
    with pytest.raises(IngestError):  # no extractable text
        load_pages(p)
