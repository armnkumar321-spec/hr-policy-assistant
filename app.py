"""HR Policy Assistant — Streamlit dashboard (RAG over the Enso Group HR manual)."""
import html

import streamlit as st
import streamlit.components.v1 as components

import importlib
import os

import hr_assistant.config, hr_assistant.sections, hr_assistant.ingest, hr_assistant.pdf_tools  # noqa: E401
import hr_assistant.history, hr_assistant.rag, hr_assistant.bootstrap  # noqa: E401


@st.cache_resource
def _module_mtimes():
    return {}


# Streamlit only re-runs app.py on edits; reload our own modules when their files change (no restart needed).
_seen = _module_mtimes()
for _m in (hr_assistant.config, hr_assistant.sections, hr_assistant.ingest, hr_assistant.pdf_tools,
           hr_assistant.history, hr_assistant.rag):
    _t = os.path.getmtime(_m.__file__)
    if _m.__name__ in _seen and _seen[_m.__name__] != _t:
        importlib.reload(_m)
    _seen[_m.__name__] = _t

from hr_assistant import config, history, pdf_tools  # noqa: E402
from hr_assistant.ingest import IngestError, ingest, last_ingest  # noqa: E402
from hr_assistant.questions import QUESTIONS

st.set_page_config(page_title="HR Policy Assistant", page_icon="📘", layout="wide")


@st.cache_resource(show_spinner="Preparing the HR manual (first start downloads and indexes it, ~1–2 min)…")
def _bootstrap():
    try:
        return hr_assistant.bootstrap.ensure_ready()
    except Exception as e:  # app still opens; Upload & Ingest remains available
        return f"setup failed: {type(e).__name__}: {e}"


BOOT_STATUS = _bootstrap()

# ---------------------------------------------------------------- state & theme
S = st.session_state
S.setdefault("view", "chat")
S.setdefault("page", 1)
S.setdefault("zoom", 100)
S.setdefault("hl_terms", [])
S.setdefault("last", None)          # last answer {question, answer, sources, warning}
S.setdefault("pending_q", "")
if "theme" not in S:  # persisted in the URL (?theme=dark) so it survives refreshes
    S.theme = st.query_params.get("theme", "light")

THEMES = {
    "light": dict(bg="#f5f7fb", panel="#ffffff", side="#ffffff", text="#0f172a", muted="#64748b",
                  border="#e2e8f0", accent="#2563eb", accent_soft="#eff6ff", ok="#16a34a", ok_soft="#f0fdf4",
                  warn="#d97706", warn_soft="#fffbeb", err="#dc2626", input="#ffffff", mark="#fde68a"),
    "dark": dict(bg="#0b1120", panel="#111827", side="#0f172a", text="#e5e7eb", muted="#94a3b8",
                 border="#1f2937", accent="#3b82f6", accent_soft="#172554", ok="#22c55e", ok_soft="#052e16",
                 warn="#f59e0b", warn_soft="#2a1d05", err="#f87171", input="#1e293b", mark="#a16207"),
}
T = THEMES.get(S.theme, THEMES["light"])
st.markdown(f"""<style>
:root {{ --bg:{T['bg']}; --panel:{T['panel']}; --text:{T['text']}; --muted:{T['muted']}; --border:{T['border']};
        --accent:{T['accent']}; --accent-soft:{T['accent_soft']}; --ok:{T['ok']}; --ok-soft:{T['ok_soft']};
        --warn:{T['warn']}; --warn-soft:{T['warn_soft']}; --err:{T['err']}; --input:{T['input']}; }}
.stApp, [data-testid="stHeader"] {{ background: var(--bg) !important; color: var(--text); }}
[data-testid="stSidebar"] > div:first-child {{ background: {T['side']} !important; border-right: 1px solid var(--border); }}
.stApp p, .stApp li, .stApp label, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
[data-testid="stSidebar"] * {{ color: var(--text); }}
.stApp [data-testid="stCaptionContainer"] *, .muted {{ color: var(--muted) !important; }}
.stApp input, .stApp textarea, [data-baseweb="select"] > div, [data-baseweb="input"] {{
   background: var(--input) !important; color: var(--text) !important; border-color: var(--border) !important; }}
.stApp button[kind="secondary"], [data-testid="stSidebar"] button {{ background: var(--panel) !important;
   color: var(--text) !important; border: 1px solid var(--border) !important; border-radius: 10px !important; }}
.stApp button[kind="primary"], .stApp button[kind="primaryFormSubmit"] {{ background: var(--accent) !important;
   border-color: var(--accent) !important; color: #fff !important; border-radius: 10px !important; }}
.stApp button[kind="primary"] *, .stApp button[kind="primaryFormSubmit"] * {{ color:#fff !important; }}
[data-testid="stSidebar"] button:hover, .stApp button[kind="secondary"]:hover {{ border-color: var(--accent) !important; }}
[data-testid="stExpander"], [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {{
   background: var(--panel); border-color: var(--border) !important; border-radius: 14px; }}
.stApp pre, .stApp code {{ background: var(--input) !important; color: var(--text) !important; }}
.card {{ background: var(--panel); border:1px solid var(--border); border-radius:14px; padding:18px 20px;
        box-shadow: 0 1px 2px rgba(0,0,0,.05); margin-bottom: 12px; }}
.answer {{ border-left: 4px solid var(--accent); }}
.answer.nf {{ border-left-color: var(--warn); background: var(--warn-soft); }}
.label {{ font-size:.75rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); font-weight:600; }}
.pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:.78rem; font-weight:600; }}
.pill.ok {{ background:var(--ok-soft); color:var(--ok); }} .pill.warn {{ background:var(--warn-soft); color:var(--warn); }}
.pill.blue {{ background:var(--accent-soft); color:var(--accent); }}
.src-title {{ font-weight:600; }} .excerpt {{ color:var(--muted); font-size:.9rem; margin-top:4px; }}
.pagetext {{ white-space: pre-wrap; font-size:.9rem; line-height:1.55; max-height: 520px; overflow:auto; }}
mark {{ background:{T['mark']}; color:inherit; padding:0 2px; border-radius:3px; }}
.brand {{ font-size:1.25rem; font-weight:700; }} .brand span {{ color: var(--accent); }}
[data-testid="stHeader"] {{ height: 0; min-height: 0; }}
.block-container {{ padding-top: 1.2rem !important; padding-bottom: 1rem !important; }}
@media (max-width: 800px) {{ .card {{ padding: 14px; }} }}
</style>""", unsafe_allow_html=True)


def go(view, **kw):
    S.view = view
    for k, v in kw.items():
        S[k] = v


def pdf_ok():
    return config.PDF_PATH.exists()


def total_pages():
    try:
        return pdf_tools.page_count()
    except Exception:
        return 0


def index_count():
    try:
        from hr_assistant.rag import index_count as ic
        return ic()
    except Exception:
        return 0


def view_page_button(page, key, terms=None, label="View page"):
    if st.button(f"{label} {page}", key=key, icon=":material/description:"):
        go("viewer", page=int(page), hl_terms=terms or [], back="chat")
        st.rerun()


def source_cards(sources, prefix, terms=None):
    if not sources:
        return
    st.markdown('<div class="label">Source references</div>', unsafe_allow_html=True)
    for i, s in enumerate(sources):
        with st.container(border=True):
            c1, c2 = st.columns([5, 1.3], vertical_alignment="center")
            tag = '<span class="pill ok">cited</span> ' if s.get("cited") else '<span class="pill blue">retrieved</span> '
            c1.markdown(f'{tag}<span class="src-title">Page {s["page"]} — {html.escape(str(s.get("section") or "Unknown section"))}</span>'
                        f'<div class="excerpt">{html.escape((s.get("snippet") or "")[:240])}…</div>', unsafe_allow_html=True)
            with c2:
                view_page_button(s["page"], key=f"{prefix}_{i}", terms=terms)


# ---------------------------------------------------------------- sidebar
NAV = [("chat", "Chat / Ask", ":material/chat:"), ("viewer", "Document Viewer", ":material/picture_as_pdf:"),
       ("search", "Search Policy", ":material/search:"), ("upload", "Upload & Ingest", ":material/upload_file:"),
       ("summary", "Summary", ":material/summarize:"), ("samples", "Sample Questions", ":material/help:"),
       ("history", "Chat History", ":material/history:"), ("settings", "Settings", ":material/settings:")]
with st.sidebar:
    st.markdown('<div class="brand">📘 HR Policy <span>Assistant</span></div>'
                '<div class="muted" style="font-size:.85rem">Enso Group HR Manual</div>', unsafe_allow_html=True)
    st.write("")
    for key, label, icon in NAV:
        if st.button(label, key=f"nav_{key}", icon=icon, use_container_width=True,
                     type="primary" if S.view == key else "secondary"):
            go(key)
            st.rerun()
    st.divider()
    n_pages, n_idx = total_pages(), index_count()
    if pdf_ok() and n_idx:
        st.markdown(f'<span class="pill ok">● Ready</span><div class="muted" style="font-size:.85rem;margin-top:6px">'
                    f'hr_manual.pdf · {n_pages} pages · {n_idx} chunks</div>', unsafe_allow_html=True)
    elif pdf_ok():
        st.markdown('<span class="pill warn">● Not indexed</span><div class="muted" style="font-size:.85rem">Open Upload & Ingest</div>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="pill warn">● No document</span><div class="muted" style="font-size:.85rem">Upload hr_manual.pdf</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="muted" style="font-size:.8rem;margin-top:8px">LLM: '
                f'{"Gemini · " + config.GEMINI_MODEL if config.gemini_key() else "none (extractive mode)"}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- header
h1, h2 = st.columns([6, 1.4], vertical_alignment="center")
h1.markdown(f"## {dict((k, l) for k, l, _ in NAV)[S.view]}")
with h2:
    dark = st.toggle("Dark mode", value=S.theme == "dark", key="theme_toggle")
    if dark != (S.theme == "dark"):
        S.theme = "dark" if dark else "light"
        st.query_params["theme"] = S.theme
        st.rerun()


def need_index():
    if not pdf_ok():
        st.warning(f"hr_manual.pdf is missing. Upload it in **Upload & Ingest** (it is saved to `{config.PDF_PATH}`).")
        return True
    if not index_count():
        st.warning("The manual has not been indexed yet. Open **Upload & Ingest** and click Ingest.")
        return True
    return False


# ---------------------------------------------------------------- views
def view_chat():
    st.caption("Answers come only from the HR Policy Manual. If the manual does not support an answer, the reply is exactly “Not found”.")
    if S.last and not (S.get("autosubmit")):
        _render_result()
        st.divider()
        st.markdown('<div class="label">Ask another question</div>', unsafe_allow_html=True)
    _ask_form()
    if S.get("_just_answered"):
        S._just_answered = False
        st.rerun()


def _ask_form():
    chips = [("Privilege Leave", QUESTIONS[0]), ("Probation Period", QUESTIONS[1]),
             ("Health Insurance Premium", QUESTIONS[2]), ("GST Rate", QUESTIONS[3]), ("Maternity Leave", QUESTIONS[4])]
    cols = st.columns(len(chips))
    for c, (label, q) in zip(cols, chips):
        if c.button(label, key=f"chip_{label}", use_container_width=True, help=q):
            S.pending_q, S.autosubmit = q, True
    with st.form("ask", border=True):
        q = st.text_input("Your question", value=S.pending_q, placeholder="e.g. How many days of Privilege Leave do I get?",
                          help="Press Enter to submit")
        sub = st.form_submit_button("Ask", type="primary", icon=":material/send:")
    if (sub and q.strip()) or (S.pending_q and S.get("autosubmit")):
        S.autosubmit = False
        q = (q or S.pending_q).strip()
        if not need_index():
            from hr_assistant.rag import answer, keywords
            with st.spinner("Searching the manual and asking Gemini…"):
                try:
                    res = answer(q)
                except Exception as e:
                    st.error(f"Could not answer: {type(e).__name__}: {e}")
                    res = None
            if res:
                S.last = {"question": q, **res, "terms": keywords(q)}
                S.hl_terms = keywords(q)
                target = pdf_tools.best_page(res)
                if target:
                    S.page = target
                history.add(q, res["answer"], res["sources"])
                S._just_answered = True


def _render_result():
    last = S.last
    nf = last["answer"] == config.NOT_FOUND or not last.get("sources")
    if nf:  # no evidence: never open a page
        st.markdown(f'<div class="card answer nf"><div class="label">Question</div><div>{html.escape(last["question"])}</div>'
                    f'<div class="label" style="margin-top:10px">Answer</div><div style="font-size:1.08rem">{html.escape(last["answer"])}</div></div>',
                    unsafe_allow_html=True)
        st.info("The HR manual has no supporting evidence for this question, so no PDF page is opened.")
        return
    left, right = st.columns([1, 1.15], gap="large")
    with left:
        if last.get("warning"):
            st.warning(last["warning"])
        top = last["sources"][0]
        st.markdown(f'<div class="card answer"><div class="label">Question</div>'
                    f'<div style="margin-bottom:10px">{html.escape(last["question"])}</div>'
                    f'<div class="label">Answer</div><div style="font-size:1.08rem">{html.escape(last["answer"])}</div>'
                    f'<div class="excerpt" style="margin-top:8px">Policy / section: {html.escape(str(top.get("section")))}</div></div>',
                    unsafe_allow_html=True)
        with st.expander("Copy answer"):
            st.code(last["answer"], language=None, wrap_lines=True)
        st.markdown('<div class="label">Source references</div>', unsafe_allow_html=True)
        for i, s_ in enumerate(pdf_tools.unique_pages(last["sources"])):
            active = s_["page"] == S.page
            with st.container(border=True):
                tag = '<span class="pill ok">cited</span> ' if s_.get("cited") else '<span class="pill blue">retrieved</span> '
                st.markdown(f'{tag}<span class="src-title">Page {s_["page"]} — {html.escape(str(s_.get("section")))}</span>'
                            f'<div class="excerpt">{html.escape((s_.get("snippet") or "")[:200])}…</div>', unsafe_allow_html=True)
                if st.button("Showing" if active else f"View page {s_['page']}", key=f"cs_{i}",
                             icon=":material/visibility:" if active else ":material/description:",
                             type="primary" if active else "secondary", disabled=active):
                    S.page = int(s_["page"]); st.rerun()
    with right:
        st.markdown('<div class="label">Original document · hr_manual.pdf</div>', unsafe_allow_html=True)
        pdf_panel("chatpdf", height=505, show_text=False)


def pdf_panel(prefix, height=720, show_text=True):
    """Real hr_manual.pdf in the browser's PDF viewer at S.page (1-based, as stored in chunk metadata)."""
    if not pdf_ok():
        st.warning("No document. Upload hr_manual.pdf in **Upload & Ingest**.")
        return
    try:
        n = pdf_tools.page_count()
    except Exception as e:
        st.error(f"Could not read the PDF: {e}")
        return
    S.page = pdf_tools.clamp_page(S.page, n)
    c = st.columns([1, 1, 1.4, 0.7, 0.7], vertical_alignment="bottom")
    if c[0].button("", icon=":material/chevron_left:", key=f"{prefix}_prev", help="Previous page",
                   disabled=S.page <= 1, use_container_width=True):
        S.page -= 1; st.rerun()
    if c[1].button("", icon=":material/chevron_right:", key=f"{prefix}_next", help="Next page",
                   disabled=S.page >= n, use_container_width=True):
        S.page += 1; st.rerun()
    newp = c[2].number_input(f"Page (of {n})", 1, n, S.page, key=f"{prefix}_pg_{S.page}", label_visibility="collapsed")
    if newp != S.page:
        S.page = int(newp); st.rerun()
    if c[3].button("", icon=":material/zoom_out:", key=f"{prefix}_zo", help="Zoom out", use_container_width=True):
        S.zoom = max(50, S.zoom - 25); st.rerun()
    if c[4].button("", icon=":material/zoom_in:", key=f"{prefix}_zi", help="Zoom in", use_container_width=True):
        S.zoom = min(250, S.zoom + 25); st.rerun()
    _, _, sec = pdf_tools.page_text(S.page)
    st.markdown(f'<span class="pill blue">Page {S.page} of {n}</span> <span class="muted" style="font-size:.85rem">'
                f'{html.escape(sec)} · zoom {S.zoom}%</span>', unsafe_allow_html=True)
    url = pdf_tools.ensure_static_pdf()
    # pdf.js renders the real page onto a canvas (Chrome's own PDF viewer is blocked inside Streamlit's sandboxed
    # component iframes). Page numbers are 1-based, same as the chunk metadata.
    components.html(pdf_tools.pdfjs_html(url, S.page, S.zoom, S.hl_terms, T, height), height=height + 12, scrolling=True)
    st.caption(f"[Open page {S.page} in a new tab]({url}#page={S.page})")
    if show_text:
        _, text, _ = pdf_tools.page_text(S.page)
        with st.expander(f"Extracted text of page {S.page}", expanded=False):
            find = st.text_input("Highlight", value=" ".join(S.hl_terms), key=f"{prefix}_find_{S.page}")
            st.markdown(f'<div class="pagetext">{pdf_tools.highlight(text, find.lower().split())}</div>', unsafe_allow_html=True)


def view_viewer():
    if S.get("back") == "chat" and S.last:
        if st.button("Back to answer", icon=":material/arrow_back:"):
            go("chat", back=None); st.rerun()
    pdf_panel("viewer", height=820)


def view_search():
    if not pdf_ok():
        st.warning("No document. Upload hr_manual.pdf in **Upload & Ingest**.")
        return
    with st.form("search"):
        q = st.text_input("Keywords", placeholder="e.g. maternity, probation, travel allowance")
        st.form_submit_button("Search", type="primary", icon=":material/search:")
    if q.strip():
        res = pdf_tools.search(q)
        st.caption(f"{len(res)} page(s) contain all of: {', '.join(q.split())}")
        terms = q.lower().split()
        for i, r in enumerate(res):
            with st.container(border=True):
                c1, c2 = st.columns([5, 1.3], vertical_alignment="center")
                c1.markdown(f'<span class="src-title">Page {r["page"]} — {html.escape(r["section"])}</span>'
                            f'<div class="excerpt">…{pdf_tools.highlight(r["excerpt"], terms)}…</div>', unsafe_allow_html=True)
                with c2:
                    if st.button(f"View page {r['page']}", key=f"sr_{i}", icon=":material/description:"):
                        go("viewer", page=r["page"], hl_terms=terms, back=None); st.rerun()


def view_upload():
    st.caption(f"The manual is stored at `{config.PDF_PATH}`. Uploading a new file replaces it and rebuilds the index without duplicates.")
    up = st.file_uploader("Choose a PDF", type=["pdf"])
    if up is not None:
        data = up.getvalue()
        st.markdown(f'**Selected:** {html.escape(up.name)} · {len(data)/1024/1024:.2f} MB')
        current = config.PDF_PATH.read_bytes() if pdf_ok() else b""
        if data == current:
            st.info("This file is already the current manual.")
        elif st.button("Save and ingest", type="primary", icon=":material/upload:"):
            if not data.startswith(b"%PDF"):
                st.error("That file is not a valid PDF.")
            else:
                tmp = config.PDF_PATH.with_suffix(".upload.pdf")
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_bytes(data)
                try:
                    from pypdf import PdfReader
                    pages = len(PdfReader(str(tmp)).pages)
                    if pages == 0:
                        raise ValueError("PDF has no pages")
                except Exception as e:
                    tmp.unlink(missing_ok=True)
                    st.error(f"Unreadable PDF, nothing was changed: {e}")
                else:
                    tmp.replace(config.PDF_PATH)
                    run_ingest()
    st.divider()
    c1, c2 = st.columns([1, 3])
    if c1.button("Re-ingest", icon=":material/refresh:", disabled=not pdf_ok()):
        run_ingest()
    li = last_ingest()
    if li:
        st.markdown('<div class="label">Last successful ingestion</div>', unsafe_allow_html=True)
        m = st.columns(6)
        for col, (k, lbl) in zip(m, [("pages", "Pages"), ("chunks", "Extracted chunks"), ("indexed", "Indexed chunks"),
                                     ("added", "Added"), ("skipped", "Unchanged"), ("removed_old", "Removed (old)")]):
            col.metric(lbl, li.get(k, "—"))
        st.caption(f"Completed {li.get('completed_at', '?')} · file {li.get('file', '')}")


def run_ingest():
    prog = st.status("Ingesting… (first run downloads a small embedding model)", expanded=True)
    try:
        prog.write("Reading PDF, chunking, embedding and writing to ChromaDB…")
        res = ingest()
        pdf_tools._pages_cached.cache_clear()
        prog.update(label=f"Ingestion complete: {res['pages']} pages, {res['indexed']} chunks indexed", state="complete")
    except IngestError as e:
        prog.update(label=f"Ingestion failed: {e}", state="error")
    except Exception as e:
        prog.update(label=f"Ingestion failed: {type(e).__name__}: {e}", state="error")


def view_summary():
    if need_index():
        return
    topics = ["Leave policy", "Maternity leave", "Probation policy", "Travel policy", "Code of conduct",
              "Disciplinary procedure", "Relocation policy", "Training and development"]
    c1, c2 = st.columns([3, 1])
    pick = c1.selectbox("Policy / section", topics + ["Other…"])
    topic = c1.text_input("Topic", value="" if pick == "Other…" else pick) if pick == "Other…" else pick
    detail = c2.radio("Length", ["Concise", "Detailed"], horizontal=True) == "Detailed"
    if st.button("Summarize", type="primary", icon=":material/summarize:") and topic:
        from hr_assistant.rag import summarize, keywords
        with st.spinner("Summarising from the manual…"):
            res = summarize(topic, detailed=detail)
        nf = res["summary"] == config.NOT_FOUND
        label = {"gemini": "Gemini summary of retrieved pages", "excerpts": "Retrieved policy text (no Gemini key)"}.get(res["mode"], "")
        st.markdown(f'<div class="card answer {"nf" if nf else ""}"><div class="label">{label or "Summary"}</div>'
                    f'<div style="white-space:pre-wrap">{html.escape(res["summary"])}</div></div>', unsafe_allow_html=True)
        source_cards(res["sources"], "sum", terms=keywords(topic))


SAMPLES = {
    "Leave Policies": [QUESTIONS[0], QUESTIONS[4], "How many days of Casual Leave are given?", "How many days of Sick Leave are given?"],
    "Employment and Probation": [QUESTIONS[1], "What happens at the end of the probation period?"],
    "Insurance and Benefits": [QUESTIONS[2], "Is travel insurance provided for leisure travel?"],
    "Compensation": ["Can Privilege Leave be encashed?"],
    "Other Policies": [QUESTIONS[3], "What is the relocation policy?"],
}


def view_samples():
    st.caption("Click a question to ask it. The answer is generated from the manual at that moment, never pre-written.")
    for cat, qs in SAMPLES.items():
        st.markdown(f"#### {cat}")
        for i, q in enumerate(qs):
            if st.button(q, key=f"sq_{cat}_{i}", icon=":material/arrow_forward:"):
                go("chat", pending_q=q, autosubmit=True); st.rerun()


def view_history():
    items = history.load()
    if not items:
        st.info("No questions asked yet.")
        return
    c1, c2 = st.columns([4, 1])
    c1.caption(f"{len(items)} saved interaction(s), stored locally in data/history.json")
    if c2.button("Clear history", icon=":material/delete:"):
        S.confirm_clear = True
    if S.get("confirm_clear"):
        st.warning("Delete all saved questions and answers?")
        a, b, _ = st.columns([1, 1, 4])
        if a.button("Yes, clear", type="primary"):
            history.clear(); S.confirm_clear = False; st.rerun()
        if b.button("Cancel"):
            S.confirm_clear = False; st.rerun()
    for i, it in enumerate(items):
        with st.container(border=True):
            st.markdown(f'<span class="muted" style="font-size:.8rem">{it["time"].replace("T", " ")}</span>'
                        f'<div class="src-title">{html.escape(it["question"])}</div>'
                        f'<div>{html.escape(it["answer"])}</div>'
                        f'<div class="excerpt">Sources: {", ".join("p. " + str(s["page"]) for s in it["sources"]) or "—"}</div>',
                        unsafe_allow_html=True)
            if st.button("Reopen", key=f"h_{i}", icon=":material/open_in_new:"):
                from hr_assistant.rag import keywords
                S.last = {"question": it["question"], "answer": it["answer"], "terms": keywords(it["question"]),
                          "sources": [{**s, "snippet": "", "cited": True} for s in it["sources"]]}
                go("chat"); st.rerun()


def view_settings():
    li = last_ingest()
    rows = [("Theme", S.theme.title() + " (saved in the page URL)"),
            ("Document", f"✅ {config.PDF_PATH}" if pdf_ok() else "❌ missing — upload hr_manual.pdf"),
            ("PDF pages", total_pages() or "—"),
            ("Indexed chunks (ChromaDB)", index_count() or "0 — not indexed"),
            ("ChromaDB location", str(config.CHROMA_DIR)),
            ("Gemini", f"✅ key set · model {config.GEMINI_MODEL}" if config.gemini_key()
             else "❌ no GEMINI_API_KEY in .env — extractive answers only"),
            ("Last successful ingestion", li.get("completed_at") if li else "—"),
            ("Startup check", BOOT_STATUS)]
    for k, v in rows:
        c1, c2 = st.columns([1, 3])
        c1.markdown(f"**{k}**")
        c2.markdown(str(v))
    st.caption("The API key itself is never displayed. Change it in the .env file and restart the app.")


{"chat": view_chat, "viewer": view_viewer, "search": view_search, "upload": view_upload, "summary": view_summary,
 "samples": view_samples, "history": view_history, "settings": view_settings}[S.view]()
