"""Page-level PDF helpers for the viewer and keyword search (reuses pypdf text extraction)."""
import re
import shutil
from functools import lru_cache

from . import config
from .sections import find_heading

STATIC_DIR = config.ROOT / "static"   # served by Streamlit at /app/static/ (enableStaticServing)


@lru_cache(maxsize=4)
def _pages_cached(path, mtime):
    from .ingest import load_pages
    from pathlib import Path
    pages = load_pages(Path(path))
    sections, current = [], "Unknown section"
    for _, text in pages:
        head = find_heading(text[:600])  # heading near the top of the page
        current = head or current
        sections.append(current)
    return [(n, t, sec) for (n, t), sec in zip(pages, sections)]


def pages(pdf_path=None):
    """[(page_no, text, section)] for the real PDF; raises IngestError if missing/unreadable."""
    p = pdf_path or config.PDF_PATH
    from .ingest import IngestError
    if not p.exists():
        raise IngestError(f"PDF not found at {p}")
    return _pages_cached(str(p), p.stat().st_mtime)


def page_count(pdf_path=None):
    return len(pages(pdf_path))


def page_text(n, pdf_path=None):
    ps = pages(pdf_path)
    if not 1 <= n <= len(ps):
        raise ValueError(f"Page {n} is outside 1–{len(ps)}")
    return ps[n - 1]


def search(query, pdf_path=None, limit=30, window=180):
    """Case-insensitive keyword search across pages. All words must appear on the page."""
    terms = [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) > 1]
    if not terms:
        return []
    results = []
    for n, text, sec in pages(pdf_path):
        flat = re.sub(r"\s+", " ", text)
        low = flat.lower()
        if not all(t in low for t in terms):
            continue
        i = low.find(terms[0])
        excerpt = flat[max(0, i - window): i + window].strip()
        score = sum(low.count(t) for t in terms)
        results.append({"page": n, "section": sec, "excerpt": excerpt, "score": score})
    results.sort(key=lambda r: (-r["score"], r["page"]))
    return results[:limit]


def highlight(text, terms):
    """HTML-escape text and wrap search terms in <mark>."""
    import html
    out = html.escape(text)
    for t in sorted({t for t in terms if len(t) > 2}, key=len, reverse=True):
        out = re.sub(f"({re.escape(html.escape(t))})", r"<mark>\1</mark>", out, flags=re.I)
    return out


def ensure_static_pdf(pdf_path=None):
    """Copy the current PDF into static/ so the browser's built-in viewer can open it at #page=N.
    Returns the URL path, or None if there is no PDF."""
    src = pdf_path or config.PDF_PATH
    if not src.exists():
        return None
    STATIC_DIR.mkdir(exist_ok=True)
    dst = STATIC_DIR / "hr_manual.pdf"
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime or dst.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dst)
    return f"/app/static/hr_manual.pdf?v={int(src.stat().st_mtime)}"


def clamp_page(page, n):
    """Keep a 1-based page number inside 1..n."""
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    return max(1, min(page, n)) if n else 1


def best_page(result):
    """Page to auto-open for an answer: the first cited source, else the top-ranked retrieved one.
    Returns None for 'Not found' or when there is no source. Pages are 1-based (pypdf index + 1 at ingest)."""
    if not result or result.get("answer") == config.NOT_FOUND:
        return None
    srcs = result.get("sources") or []
    cited = [s for s in srcs if s.get("cited")]
    pick = (cited or srcs or [None])[0]
    return int(pick["page"]) if pick and pick.get("page") else None


def viewer_src(url, page, zoom=100):
    """Browser PDF-viewer URL. The ?p= part changes per page so the iframe really reloads; #page is 1-based."""
    return f"{url}&p={int(page)}&z={int(zoom)}#page={int(page)}&zoom={int(zoom)}"


PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379"


def pdfjs_html(url, page, zoom, terms, theme, height=720):
    """Self-contained pdf.js page renderer with yellow highlights over words matching `terms`."""
    import json
    terms = [t.lower() for t in (terms or []) if len(t) > 2]
    return f"""<!doctype html><html><body style="margin:0;background:{theme['bg']};font-family:system-ui">
<div id="msg" style="padding:12px;color:{theme['muted']}">Loading page {int(page)}…</div>
<div id="wrap" style="position:relative;display:block;width:fit-content;margin:0 auto;box-shadow:0 1px 6px rgba(0,0,0,.15)">
<canvas id="cv"></canvas><div id="hl" style="position:absolute;left:0;top:0"></div></div>
<script type="module">
const msg = document.getElementById('msg');
try {{
  const pdfjs = await import('{PDFJS}/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc = '{PDFJS}/pdf.worker.min.mjs';
  const abs = new URL({json.dumps(url)}, document.baseURI).href;
  const doc = await pdfjs.getDocument(abs).promise;
  const n = Math.min(Math.max({int(page)}, 1), doc.numPages);   // 1-based, like the citations
  const pg = await doc.getPage(n);
  const width = Math.max(document.body.clientWidth - 4, 300);
  const base = pg.getViewport({{scale: 1}});
  const fit = Math.min(width / base.width, ({int(height)} - 40) / base.height);  // whole page visible at 100%
  const vp = pg.getViewport({{scale: fit * {int(zoom)} / 100}});
  const cv = document.getElementById('cv'), dpr = window.devicePixelRatio || 1;
  cv.width = vp.width * dpr; cv.height = vp.height * dpr; cv.style.width = vp.width + 'px'; cv.style.height = vp.height + 'px';
  await pg.render({{canvasContext: cv.getContext('2d'), viewport: vp, transform: [dpr,0,0,dpr,0,0]}}).promise;
  const terms = {json.dumps(terms)};
  if (terms.length) {{
    const tc = await pg.getTextContent(); const hl = document.getElementById('hl'); let hits = 0;
    for (const it of tc.items) {{
      if (!terms.some(t => it.str.toLowerCase().includes(t))) continue;
      const [a,b,c,d,e,f] = pdfjs.Util.transform(vp.transform, it.transform);
      const h = Math.hypot(c, d), w = it.width * vp.scale;
      const box = document.createElement('div');
      box.style.cssText = `position:absolute;left:${{e}}px;top:${{f-h}}px;width:${{w}}px;height:${{h*1.15}}px;background:rgba(250,204,21,.38);border-radius:2px`;
      hl.appendChild(box); hits++;
    }}
    msg.textContent = `Page ${{n}} of ${{doc.numPages}} · ${{hits}} highlighted match(es)`;
  }} else msg.textContent = `Page ${{n}} of ${{doc.numPages}}`;
  document.body.dataset.renderedPage = n; document.body.dataset.info = msg.textContent; msg.style.display = 'none';
}} catch (e) {{ msg.textContent = 'Could not render the PDF page: ' + e; msg.style.color = '{theme['err']}'; }}
</script></body></html>"""


def unique_pages(sources):
    """One source card per page, keeping rank order (and 'cited' if any chunk on that page was cited)."""
    out, seen = [], {}
    for s in sources or []:
        p = s.get("page")
        if p in seen:
            seen[p]["cited"] = seen[p].get("cited") or s.get("cited")
            continue
        seen[p] = dict(s)
        out.append(seen[p])
    return out
