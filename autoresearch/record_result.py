#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


HEADER = [
    "commit",
    "run_id",
    "val_bpb",
    "artifact_bytes",
    "peak_vram_mb",
    "status",
    "description",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append one run summary to autoresearch/results.tsv.")
    parser.add_argument("--summary", required=True, help="Path to a run summary.json produced by run_experiment.py.")
    parser.add_argument(
        "--status",
        required=True,
        choices=["keep", "discard", "crash", "timeout"],
        help="Final disposition for this run.",
    )
    parser.add_argument("--description", required=True, help="Short description of the experiment.")
    parser.add_argument(
        "--results",
        default="autoresearch/results.tsv",
        help="TSV path relative to repo root or absolute.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else repo_root() / path


def ensure_results_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(HEADER)


def sanitize_description(text: str) -> str:
    return " ".join(text.replace("\t", " ").replace("\n", " ").split())


def main() -> int:
    args = parse_args()
    summary_path = resolve_repo_path(args.summary)
    results_path = resolve_repo_path(args.results)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    ensure_results_file(results_path)
    row = {
        "commit": summary.get("commit") or "unknown",
        "run_id": summary.get("run_id") or summary_path.parent.name,
        "val_bpb": f"{float(summary['val_bpb']):.8f}" if summary.get("val_bpb") is not None else "0.00000000",
        "artifact_bytes": str(int(summary["artifact_bytes"])) if summary.get("artifact_bytes") is not None else "0",
        "peak_vram_mb": str(int(summary["peak_vram_mb"])) if summary.get("peak_vram_mb") is not None else "0",
        "status": args.status,
        "description": sanitize_description(args.description),
    }

    with results_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER, delimiter="\t")
        writer.writerow(row)

    print(f"results_path: {results_path}")
    print(f"run_id: {row['run_id']}")
    print(f"status: {row['status']}")
    print(f"val_bpb: {row['val_bpb']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
