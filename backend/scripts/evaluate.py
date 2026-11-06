"""Run the evaluation set and print a summary.

    python -m scripts.evaluate                    # retrieval + generation (needs API key)
    python -m scripts.evaluate --retrieval-only   # free & fast: Hit@k, P@k, MRR
    python -m scripts.evaluate --tag chunk600     # label the run (compare configs!)
"""

import argparse
import json
import logging
from pathlib import Path

from app.evaluation.runner import run_eval

logging.basicConfig(level=logging.WARNING)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=None)
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    report = run_eval(a.file, with_generation=not a.retrieval_only, tag=a.tag)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("\nReports written to data/eval/results/ (latest.json + .md)")
