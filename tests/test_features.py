"""Tests for search, viewer helpers, citation validation, summaries and history (no PDF/model needed)."""
from langchain_core.documents import Document

from hr_assistant import history, pdf_tools
from hr_assistant.rag import summarize, validate_citations
from hr_assistant.sections import find_heading

PAGES = [(1, "Leave Policy\nPrivilege Leave (PL) – 12 days per year.", "Leave Policy"),
         (2, "Probation Policy\nAll employees up to Sr. Manager: 3 months.", "Probation Policy")]


class FakeStore:
    def __init__(self, docs): self.docs = docs
    def similarity_search(self, q, k=5): return self.docs[:k]


DOCS = [Document(page_content="Maternity Leave: 12 weeks (90 days) with pay.", metadata={"page": 62, "section": "Maternity Leave"}),
        Document(page_content="Privilege Leave (PL) – 12 days", metadata={"page": 60, "section": "Leave Policy"})]
SRC = [{"page": 62, "section": "Maternity Leave", "snippet": ""}, {"page": 60, "section": "Leave Policy", "snippet": ""}]


def test_search_finds_pages_and_sections(monkeypatch):
    monkeypatch.setattr(pdf_tools, "pages", lambda pdf_path=None: PAGES)
    r = pdf_tools.search("privilege leave")
    assert [x["page"] for x in r] == [1] and r[0]["section"] == "Leave Policy" and "12 days" in r[0]["excerpt"]
    assert pdf_tools.search("gst") == [] and pdf_tools.search("") == []


def test_highlight_escapes_and_marks():
    out = pdf_tools.highlight("<b>Leave</b> rules", ["leave"])
    assert "&lt;b&gt;" in out and "<mark>Leave</mark>" in out


def test_invented_citation_is_replaced_with_retrieved_page():
    text, src = validate_citations("You get 90 days [p. 7, Made up]", DOCS, [dict(s) for s in SRC])
    assert "p. 7" not in text and "[p. 62, Maternity Leave]" in text and src[0]["cited"]


def test_valid_citation_kept_and_sources_ordered():
    text, src = validate_citations("12 days [p. 60, Leave Policy]", DOCS, [dict(s) for s in SRC])
    assert "[p. 60" in text and src[0]["page"] == 60 and src[0]["cited"] and not src[1]["cited"]


def test_summary_not_found_and_excerpt_mode(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert summarize("GST rate", store=FakeStore(DOCS))["summary"] == "Not found"
    r = summarize("maternity leave", store=FakeStore(DOCS))
    assert r["mode"] == "excerpts" and "[p. 62" in r["summary"]


def test_table_header_is_not_a_section():
    assert find_heading("Leave Type Eligibility Entitlement Encashment Procedure") is None
    assert find_heading("Probation Policy") == "Probation Policy"


def test_history_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    history.add("q?", "Not found", [], path=p)
    history.add("q2?", "12 days", [{"page": 60, "section": "Leave", "snippet": "x"}], path=p)
    items = history.load(p)
    assert items[0]["question"] == "q2?" and items[0]["sources"] == [{"page": 60, "section": "Leave"}]
    assert "GEMINI" not in p.read_text()
    history.clear(p)
    assert history.load(p) == []


def test_best_page_prefers_cited_and_ignores_not_found():
    assert pdf_tools.best_page({"answer": "Not found", "sources": []}) is None
    assert pdf_tools.best_page({"answer": "x", "sources": []}) is None
    r = {"answer": "12 days", "sources": [{"page": 61}, {"page": 60, "cited": True}]}
    assert pdf_tools.best_page(r) == 60
    assert pdf_tools.best_page({"answer": "x", "sources": [{"page": 42}, {"page": 43}]}) == 42


def test_clamp_and_viewer_src_are_one_based():
    assert pdf_tools.clamp_page(0, 79) == 1 and pdf_tools.clamp_page(80, 79) == 79 and pdf_tools.clamp_page("61", 79) == 61
    assert pdf_tools.viewer_src("/app/static/hr_manual.pdf?v=1", 61).endswith("#page=61&zoom=100")


def test_ingest_page_numbers_are_one_based(monkeypatch, tmp_path):
    import pypdf
    from hr_assistant.ingest import load_pages

    class P:
        def __init__(self, t): self.t = t
        def extract_text(self): return self.t

    class R:
        def __init__(self, path): self.pages = [P("first page"), P("second page")]

    monkeypatch.setattr(pypdf, "PdfReader", R)
    f = tmp_path / "x.pdf"; f.write_bytes(b"%PDF-1.4")
    assert load_pages(f) == [(1, "first page"), (2, "second page")]


def test_unique_pages_keeps_rank_and_cited():
    s = pdf_tools.unique_pages([{"page": 62}, {"page": 62, "cited": True}, {"page": 60}])
    assert [x["page"] for x in s] == [62, 60] and s[0]["cited"]


def test_lettered_policy_heading_detected():
    assert find_heading("HR Manual - 42\n[B] Probation Policy\nMeaning/Purpose") == "[B] Probation Policy"
