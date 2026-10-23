"""Integration: needs data/hr_manual.pdf and a completed ingest. Skipped otherwise.
Fill EXPECTED after verifying each answer against the PDF by hand."""
import pytest
from hr_assistant import config
from hr_assistant.questions import QUESTIONS

pytestmark = pytest.mark.skipif(not config.PDF_PATH.exists(), reason="hr_manual.pdf not present")


def test_gst_not_found():
    from hr_assistant.rag import answer
    assert answer(QUESTIONS[3])["answer"] == "Not found"


@pytest.mark.parametrize("q", [QUESTIONS[i] for i in (0, 1, 2, 4)])
def test_answers_are_cited_or_not_found(q):
    from hr_assistant.rag import answer
    a = answer(q)["answer"]
    assert a == "Not found" or "[p. " in a
