"""Best-effort detection of the policy/section heading a chunk belongs to."""
import re

_HEADING = re.compile(
    r"^\s*((\[[A-Z]\]\s+[A-Z][\w &/\-()]{2,60})|(\d+(\.\d+)*\.?\s+[A-Z][^\n]{2,80})|([A-Z][A-Z &/,\-()]{4,80})|"
    r"([A-Z][\w &/\-()]{2,60}\s+(Policy|Leave|Rules?|Benefits?|Scheme|Procedure)))\s*$"
)


_NOT_HEADINGS = re.compile(
    r"(eligibility\s+entitlement|scope\s*&\s*eligibility|policy features|^remarks$|^hr manual\b)", re.I)


def find_heading(text):
    """Return the last heading-looking line in text, or None."""
    last = None
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 5 or line.endswith((".", ",", ";")) and not re.match(r"^\d", line):
            continue
        if _NOT_HEADINGS.search(line):
            continue
        if _HEADING.match(line):
            last = re.sub(r"\s+", " ", line)
    return last
