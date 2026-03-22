#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


FINAL_BPB_RE = re.compile(
    r"final_int8_zlib_roundtrip_exact val_loss:(?P<val_loss>[-+0-9.eE]+) "
    r"val_bpb:(?P<val_bpb>[-+0-9.eE]+)"
)
ARTIFACT_RE = re.compile(r"Total submission size int8\+zlib: (?P<artifact_bytes>\d+) bytes")
PEAK_VRAM_RE = re.compile(
    r"peak memory allocated: (?P<peak_vram_mb>\d+) MiB reserved: (?P<peak_reserved_mb>\d+) MiB"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and parse one parameter-golf autoresearch experiment.")
    parser.add_argument("--description", required=True, help="Short label for this run.")
    parser.add_argument(
        "--candidate",
        default="autoresearch/candidate/train_gpt.py",
        help="Path to the editable training script, relative to repo root.",
    )
    parser.add_argument("--nproc-per-node", type=int, default=1, help="torchrun worker count.")
    parser.add_argument(
        "--max-wallclock-seconds",
        type=float,
        default=600.0,
        help="Value to pass as MAX_WALLCLOCK_SECONDS to the training script.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=1800.0,
        help="Kill the run if wall time exceeds this limit.",
    )
    parser.add_argument("--run-id", default="", help="Optional explicit run id.")
    parser.add_argument("--seed", type=int, default=None, help="Optional SEED override.")
    return parser.parse_args()


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text.strip()).strip("_").lower()
    return cleaned or "run"


def last_match(pattern: re.Pattern[str], text: str) -> dict[str, str] | None:
    matches = list(pattern.finditer(text))
    return matches[-1].groupdict() if matches else None


def git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            text=True,
        ).strip()
    except subprocess.SubprocessError:
        return "unknown"


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    candidate_path = (repo_root / args.candidate).resolve()
    if not candidate_path.exists():
        raise FileNotFoundError(f"Candidate script not found: {candidate_path}")

    run_id = args.run_id or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slugify(args.description)}"
    runs_root = repo_root / "autoresearch" / "runs"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    log_path = run_dir / "run.log"
    summary_path = run_dir / "summary.json"

    env = os.environ.copy()
    env.setdefault("DATA_PATH", str((repo_root / "data" / "datasets" / "fineweb10B_sp1024").resolve()))
    env.setdefault(
        "TOKENIZER_PATH",
        str((repo_root / "data" / "tokenizers" / "fineweb_1024_bpe.model").resolve()),
    )
    env.setdefault("VOCAB_SIZE", "1024")
    env.setdefault("RUN_ID", run_id)
    env["MAX_WALLCLOCK_SECONDS"] = str(args.max_wallclock_seconds)
    if args.seed is not None:
        env["SEED"] = str(args.seed)

    command = [
        sys.executable,
        "-m",
        "torch.distributed.run",
        "--standalone",
        f"--nproc_per_node={args.nproc_per_node}",
        str(candidate_path),
    ]

    started_at = time.time()
    timed_out = False
    exit_code: int | None = None

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"# run_id={run_id}\n")
        log_file.write(f"# description={args.description}\n")
        log_file.write(f"# candidate={candidate_path}\n")
        log_file.write(f"# command={' '.join(command)}\n")
        log_file.flush()
        try:
            completed = subprocess.run(
                command,
                cwd=run_dir,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=args.timeout_seconds,
                check=False,
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            log_file.write(f"\n# timeout after {args.timeout_seconds:.1f} seconds\n")
            exit_code = None

    wall_seconds = time.time() - started_at
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    bpb_match = last_match(FINAL_BPB_RE, log_text)
    artifact_match = last_match(ARTIFACT_RE, log_text)
    peak_match = last_match(PEAK_VRAM_RE, log_text)

    if timed_out:
        status = "timeout"
    elif exit_code == 0 and bpb_match is not None:
        status = "ok"
    else:
        status = "crash"

    summary = {
        "status": status,
        "description": args.description,
        "run_id": run_id,
        "repo_root": str(repo_root),
        "run_dir": str(run_dir),
        "log_path": str(log_path),
        "summary_path": str(summary_path),
        "candidate_path": str(candidate_path),
        "command": command,
        "commit": git_commit(repo_root),
        "nproc_per_node": args.nproc_per_node,
        "max_wallclock_seconds": args.max_wallclock_seconds,
        "wall_seconds": round(wall_seconds, 3),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "val_loss": float(bpb_match["val_loss"]) if bpb_match else None,
        "val_bpb": float(bpb_match["val_bpb"]) if bpb_match else None,
        "artifact_bytes": int(artifact_match["artifact_bytes"]) if artifact_match else None,
        "peak_vram_mb": int(peak_match["peak_vram_mb"]) if peak_match else None,
        "peak_reserved_mb": int(peak_match["peak_reserved_mb"]) if peak_match else None,
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"status: {summary['status']}")
    print(f"run_id: {summary['run_id']}")
    print(f"run_dir: {summary['run_dir']}")
    print(f"log_path: {summary['log_path']}")
    print(f"summary_path: {summary['summary_path']}")
    print(f"candidate_path: {summary['candidate_path']}")
    print(f"commit: {summary['commit']}")
    print(f"nproc_per_node: {summary['nproc_per_node']}")
    print(f"max_wallclock_seconds: {summary['max_wallclock_seconds']}")
    print(f"wall_seconds: {summary['wall_seconds']}")
    print(f"exit_code: {summary['exit_code']}")
    if summary["val_bpb"] is not None:
        print(f"val_bpb: {summary['val_bpb']:.8f}")
    if summary["artifact_bytes"] is not None:
        print(f"artifact_bytes: {summary['artifact_bytes']}")
    if summary["peak_vram_mb"] is not None:
        print(f"peak_vram_mb: {summary['peak_vram_mb']}")

    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
