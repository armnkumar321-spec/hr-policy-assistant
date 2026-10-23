"""Grounded retrieval + answering. Returns exactly 'Not found' when the manual doesn't support an answer."""
import re

from . import config

STOP = set("""a an the of to in for on and or is are was what how many much does do per year
           company's company current given get any by with be at as it its this that employee employees""".split())

PROMPT = """You answer questions about the Enso Group HR Policy Manual using ONLY the excerpts below.
Rules:
- If the excerpts do not explicitly contain the answer, reply with exactly: Not found
- Never use outside knowledge (e.g. tax rates, laws) that is not in the excerpts.
- Otherwise answer in 1-2 sentences and end with the citation as [p. <page>, <section>].

Excerpts:
{context}

Question: {question}
Answer:"""


def keywords(q):
    words = re.findall(r"[A-Za-z]+", q.lower())
    return [w for w in words if w not in STOP and len(w) > 1]


def normalize(answer):
    a = (answer or "").strip()
    if not a or re.match(r"^\W*not\s+found\W*$", a, re.I) or a.lower().startswith("not found"):
        return config.NOT_FOUND
    return a


def _supported(question, docs):
    """Require the question's distinctive terms to actually occur in retrieved text."""
    kws = keywords(question)
    blob = set(re.findall(r"[a-z]+", " ".join(d.page_content.lower() for d in docs)))
    hits = [k for k in kws if k in blob]
    # every acronym/rare term (gst, pl, ...) must be present; and majority of others
    rare = [k for k in kws if len(k) <= 4]
    return all(k in blob for k in rare) and len(hits) >= max(1, round(0.6 * len(kws)))


def _best_sentence(question, docs):
    kws = keywords(question)
    best, best_score, best_doc = None, 0, None
    for d in docs:
        for s in re.split(r"(?<=[.;:])\s+|\n", d.page_content):
            s = s.strip()
            if len(s) < 15:
                continue
            low = set(re.findall(r"[a-z]+", s.lower()))
            score = sum(k in low for k in kws) + (1 if re.search(r"\d", s) else 0)
            if score > best_score:
                best, best_score, best_doc = s, score, d
    return best, best_doc


def cite(doc):
    m = doc.metadata
    return f"[p. {m.get('page')}, {m.get('section', 'Unknown section')}]"


FALLBACK_MODELS = ["gemini-2.5-flash-lite", "gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash"]
_working_model = None


def _gemini(model):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=model, google_api_key=config.gemini_key(), temperature=0)


class _Tracked:
    """Remembers the first model that answers, so later questions use it directly."""
    def __init__(self, model): self.model = model
    def invoke(self, prompt):
        global _working_model
        out = _gemini(self.model).invoke(prompt)
        _working_model = self.model
        return out


def _gemini_candidates():
    names = [_working_model] if _working_model else []
    names += [config.GEMINI_MODEL] + FALLBACK_MODELS
    seen = []
    for n in names:
        if n and n not in seen:
            seen.append(n)
    return [_Tracked(n) for n in seen]


def answer(question, store=None, llm=None):
    """Returns dict(answer, sources)."""
    question = (question or "").strip()
    if not question:
        return {"answer": config.NOT_FOUND, "sources": []}
    if store is None:
        from .ingest import get_store
        store = get_store()
    docs = store.similarity_search(question, k=config.TOP_K)
    if not docs or not _supported(question, docs):
        return {"answer": config.NOT_FOUND, "sources": []}

    sources = [{"page": d.metadata.get("page"), "section": d.metadata.get("section"),
                "snippet": d.page_content[:300]} for d in docs]
    if llm is None and config.gemini_key():
        llm = "gemini"
    if llm is not None:
        ctx = "\n\n".join(f"[p. {d.metadata['page']}, {d.metadata.get('section')}]\n{d.page_content}" for d in docs)
        prompt = PROMPT.format(context=ctx, question=question)
        errors = []
        for candidate in ([llm] if not isinstance(llm, str) else []) or _gemini_candidates():
            try:
                out = candidate.invoke(prompt)
                content = getattr(out, "content", out)
                if isinstance(content, list):  # newer Gemini responses can be content parts
                    content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                text = normalize(str(content))
                if text == config.NOT_FOUND:
                    return {"answer": text, "sources": []}
                text, sources_v = validate_citations(text, docs, sources)
                return {"answer": text, "sources": sources_v}
            except Exception as e:  # model retired/renamed, network, quota: try next, then fall back
                errors.append(type(e).__name__)
                if "NotFound" not in type(e).__name__:
                    break
        if True:
            warning = f"Gemini unavailable ({', '.join(errors)}); showing extractive answer."
            res = _extractive(question, docs, sources)
            res["warning"] = warning
            return res

    return _extractive(question, docs, sources)


_CITE = re.compile(r"\[p\.?\s*(\d+)[^\]]*\]")


def validate_citations(text, docs, sources):
    """Keep only citations whose page was actually retrieved; order sources with cited pages first."""
    retrieved = {d.metadata.get("page") for d in docs}
    cited = [int(m) for m in _CITE.findall(text)]
    valid = [p for p in cited if p in retrieved]
    if cited and not valid:  # model cited pages we never gave it: replace with the top retrieved chunk
        text = _CITE.sub("", text).strip() + " " + cite(docs[0])
        valid = [docs[0].metadata.get("page")]
    elif not cited:
        text = text + " " + cite(docs[0])
        valid = [docs[0].metadata.get("page")]
    else:
        text = _CITE.sub(lambda m: m.group(0) if int(m.group(1)) in retrieved else "", text).strip()
    ordered = [s for s in sources if s["page"] in valid] + [s for s in sources if s["page"] not in valid]
    for s in ordered:
        s["cited"] = s["page"] in valid
    return text, ordered


SUMMARY_PROMPT = """Summarise what the Enso Group HR Policy Manual says about: {topic}
Use ONLY the excerpts below. If they do not cover the topic, reply exactly: Not found
{style}
Cite pages like [p. <page>]. Do not add anything that is not in the excerpts.

Excerpts:
{context}

Summary:"""


def summarize(topic, detailed=False, store=None, llm=None):
    """Grounded summary of a policy topic. Returns dict(summary, sources, mode)."""
    topic = (topic or "").strip()
    if not topic:
        return {"summary": config.NOT_FOUND, "sources": [], "mode": "none"}
    if store is None:
        from .ingest import get_store
        store = get_store()
    docs = store.similarity_search(topic, k=8 if detailed else 4)
    if not docs or not _supported(topic, docs):
        return {"summary": config.NOT_FOUND, "sources": [], "mode": "none"}
    sources = [{"page": d.metadata.get("page"), "section": d.metadata.get("section"),
                "snippet": d.page_content[:300]} for d in docs]
    style = ("Write a detailed summary as bullet points covering eligibility, entitlement and procedure."
             if detailed else "Write 2-4 concise sentences.")
    ctx = "\n\n".join(f"[p. {d.metadata['page']}, {d.metadata.get('section')}]\n{d.page_content}" for d in docs)
    candidates = [llm] if llm is not None else (_gemini_candidates() if config.gemini_key() else [])
    for c in candidates:
        try:
            out = c.invoke(SUMMARY_PROMPT.format(topic=topic, style=style, context=ctx))
            content = getattr(out, "content", out)
            if isinstance(content, list):
                content = "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
            text = normalize(str(content))
            if text == config.NOT_FOUND:
                return {"summary": text, "sources": [], "mode": "gemini"}
            text, sources = validate_citations(text, docs, sources)
            return {"summary": text, "sources": sources, "mode": "gemini"}
        except Exception as e:
            if "NotFound" not in type(e).__name__:
                break
    # no LLM: show the retrieved policy text itself, clearly labelled as excerpts
    return {"summary": "\n\n".join(f"{cite(d)} {d.page_content.strip()}" for d in docs[: (4 if detailed else 2)]),
            "sources": sources, "mode": "excerpts"}


def _extractive(question, docs, sources):
    sent, doc = _best_sentence(question, docs)
    if not sent:
        return {"answer": config.NOT_FOUND, "sources": []}
    return {"answer": f"{sent} {cite(doc)}", "sources": sources}


def index_count():
    from .ingest import get_store
    return get_store()._collection.count()
