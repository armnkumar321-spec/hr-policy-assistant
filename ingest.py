from hr_assistant.ingest import ingest, IngestError
import sys
if __name__ == "__main__":
    try:
        print(ingest())
    except IngestError as e:
        sys.exit(f"Ingestion failed: {e}")
