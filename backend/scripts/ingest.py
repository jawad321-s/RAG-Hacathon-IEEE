"""Ingest every file in data/raw (sub-folder name -> `category`).

Usage:
    python -m scripts.ingest              # ingest data/raw (upsert)
    python -m scripts.ingest --reset      # wipe collection first
    python -m scripts.ingest --path some/folder
"""

import argparse
import json
import logging
from pathlib import Path

from app.config import get_settings
from app.ingestion.pipeline import ingest_directory
from app.retrieval.vectorstore import get_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=Path, default=None)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    if args.reset:
        get_store().reset()
    res = ingest_directory(args.path or get_settings().raw_docs_dir)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\nTotal chunks in collection: {get_store().count()}")
