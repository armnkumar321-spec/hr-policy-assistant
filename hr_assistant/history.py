"""Local Q&A history in data/history.json (never stores keys or settings)."""
import json
from datetime import datetime

from . import config

HISTORY_PATH = config.ROOT / "data" / "history.json"
MAX_ITEMS = 200


def load(path=None):
    try:
        return json.loads((path or HISTORY_PATH).read_text())
    except (OSError, ValueError):
        return []


def add(question, answer, sources, path=None):
    path = path or HISTORY_PATH
    items = load(path)
    items.insert(0, {"question": question, "answer": answer,
                     "sources": [{"page": s.get("page"), "section": s.get("section")} for s in sources],
                     "time": datetime.now().isoformat(timespec="seconds")})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items[:MAX_ITEMS], indent=1))
    return items[0]


def clear(path=None):
    (path or HISTORY_PATH).parent.mkdir(parents=True, exist_ok=True)
    (path or HISTORY_PATH).write_text("[]")
