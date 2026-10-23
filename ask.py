"""CLI: python ask.py "question"   or   python ask.py --eval  (runs the five assignment questions)."""
import sys

from hr_assistant import config
from hr_assistant.questions import QUESTIONS

if __name__ == "__main__":
    if not config.PDF_PATH.exists():
        sys.exit(f"hr_manual.pdf not found. Put it at {config.PDF_PATH} and run: python ingest.py")
    from hr_assistant.rag import answer, index_count
    if index_count() == 0:
        sys.exit("Index is empty. Run: python ingest.py")
    print("Mode:", f"Gemini ({config.GEMINI_MODEL})" if config.gemini_key() else "extractive (no GEMINI_API_KEY)")
    qs = QUESTIONS if (len(sys.argv) < 2 or sys.argv[1] == "--eval") else [" ".join(sys.argv[1:])]
    for i, q in enumerate(qs, 1):
        r = answer(q)
        print(f"\nQ{i}: {q}\nA{i}: {r['answer']}" + (f"\n   ({r['warning']})" if r.get("warning") else ""))
