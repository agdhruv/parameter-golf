#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path


@dataclass
class ResultRow:
    index: int
    commit: str
    run_id: str
    val_bpb: float | None
    artifact_bytes: int | None
    peak_vram_mb: int | None
    nproc_per_node: int | None
    max_wallclock_seconds: int | None
    status: str
    description: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize and visualize autoresearch/results.tsv.")
    parser.add_argument(
        "--results",
        default="autoresearch/results.tsv",
        help="TSV path relative to repo root or absolute.",
    )
    parser.add_argument(
        "--output-dir",
        default="autoresearch",
        help="Directory for progress.svg, summary.json, and summary.md.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else repo_root() / path


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def read_results(path: Path) -> list[ResultRow]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows: list[ResultRow] = []
        for idx, row in enumerate(reader):
            rows.append(
                ResultRow(
                    index=idx,
                    commit=(row.get("commit") or "").strip(),
                    run_id=(row.get("run_id") or "").strip(),
                    val_bpb=parse_float(row.get("val_bpb", "")),
                    artifact_bytes=parse_int(row.get("artifact_bytes", "")),
                    peak_vram_mb=parse_int(row.get("peak_vram_mb", "")),
                    nproc_per_node=parse_int(row.get("nproc_per_node", "")),
                    max_wallclock_seconds=parse_int(row.get("max_wallclock_seconds", "")),
                    status=(row.get("status") or "").strip().upper(),
                    description=(row.get("description") or "").strip(),
                )
            )
        return rows


def first_valid(rows: list[ResultRow]) -> ResultRow | None:
    for row in rows:
        if row.val_bpb is not None and row.val_bpb > 0:
            return row
    return None


def format_float(value: float | None, digits: int = 8) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def same_track(row: ResultRow, baseline: ResultRow | None) -> bool:
    if baseline is None:
        return True
    return (
        row.nproc_per_node == baseline.nproc_per_node
        and row.max_wallclock_seconds == baseline.max_wallclock_seconds
    )


def build_summary(rows: list[ResultRow]) -> dict:
    counts = Counter(row.status for row in rows)
    baseline = first_valid(rows)
    primary_rows = [row for row in rows if same_track(row, baseline)]
    kept = [row for row in primary_rows if row.status == "KEEP" and row.val_bpb is not None and row.val_bpb > 0]
    best = min(kept, key=lambda row: row.val_bpb) if kept else baseline

    n_keep = counts.get("KEEP", 0)
    n_discard = counts.get("DISCARD", 0)
    n_crash = counts.get("CRASH", 0)
    n_timeout = counts.get("TIMEOUT", 0)
    n_decided = n_keep + n_discard
    keep_rate = (n_keep / n_decided) if n_decided else None

    hits = []
    for prev, curr in zip(kept, kept[1:]):
        if prev.val_bpb is None or curr.val_bpb is None:
            continue
        hits.append(
            {
                "run_id": curr.run_id,
                "description": curr.description,
                "val_bpb": curr.val_bpb,
                "delta": prev.val_bpb - curr.val_bpb,
            }
        )
    hits.sort(key=lambda hit: hit["delta"], reverse=True)

    return {
        "total_experiments": len(rows),
        "counts": {
            "keep": n_keep,
            "discard": n_discard,
            "crash": n_crash,
            "timeout": n_timeout,
        },
        "keep_rate": keep_rate,
        "baseline": {
            "run_id": baseline.run_id if baseline else None,
            "val_bpb": baseline.val_bpb if baseline else None,
            "description": baseline.description if baseline else None,
            "nproc_per_node": baseline.nproc_per_node if baseline else None,
            "max_wallclock_seconds": baseline.max_wallclock_seconds if baseline else None,
        },
        "best": {
            "run_id": best.run_id if best else None,
            "val_bpb": best.val_bpb if best else None,
            "description": best.description if best else None,
            "commit": best.commit if best else None,
        },
        "primary_track": {
            "nproc_per_node": baseline.nproc_per_node if baseline else None,
            "max_wallclock_seconds": baseline.max_wallclock_seconds if baseline else None,
            "rows_in_track": len(primary_rows),
            "rows_outside_track": len(rows) - len(primary_rows),
        },
        "total_improvement": (
            baseline.val_bpb - best.val_bpb
            if baseline and best and baseline.val_bpb is not None and best.val_bpb is not None
            else None
        ),
        "top_hits": hits[:10],
    }


def render_summary_markdown(rows: list[ResultRow], summary: dict) -> str:
    lines = ["# Parameter Golf Autoresearch Summary", ""]
    lines.append(f"- Total experiments: {summary['total_experiments']}")
    lines.append(f"- Kept: {summary['counts']['keep']}")
    lines.append(f"- Discarded: {summary['counts']['discard']}")
    lines.append(f"- Crashed: {summary['counts']['crash']}")
    lines.append(f"- Timed out: {summary['counts']['timeout']}")
    if summary["keep_rate"] is not None:
        lines.append(f"- Keep rate: {summary['keep_rate']:.1%}")
    lines.append("")

    baseline = summary["baseline"]
    best = summary["best"]
    primary_track = summary["primary_track"]
    lines.append("## Frontier")
    lines.append("")
    if primary_track["nproc_per_node"] is not None:
        lines.append(
            f"- Primary track: {primary_track['nproc_per_node']} GPU, {primary_track['max_wallclock_seconds']}s runs"
        )
    lines.append(f"- Baseline val_bpb: {format_float(baseline['val_bpb'])}")
    lines.append(f"- Best val_bpb: {format_float(best['val_bpb'])}")
    if summary["total_improvement"] is not None:
        lines.append(f"- Total improvement: {summary['total_improvement']:.8f}")
    if best["description"]:
        lines.append(f"- Best experiment: {best['description']}")
    if primary_track["rows_outside_track"]:
        lines.append(
            f"- Off-track runs excluded from frontier math: {primary_track['rows_outside_track']}"
        )
    lines.append("")

    kept_rows = [
        row for row in rows
        if same_track(row, first_valid(rows)) and row.status == "KEEP" and row.val_bpb is not None and row.val_bpb > 0
    ]
    lines.append("## Kept Runs")
    lines.append("")
    if kept_rows:
        for row in kept_rows:
            lines.append(
                f"- #{row.index} {format_float(row.val_bpb)} {row.run_id} {row.description}"
            )
    else:
        lines.append("- None yet.")
    lines.append("")

    lines.append("## Top Hits")
    lines.append("")
    if summary["top_hits"]:
        for hit in summary["top_hits"]:
            lines.append(
                f"- {hit['delta']:+.8f} -> {hit['val_bpb']:.8f} {hit['run_id']} {hit['description']}"
            )
    else:
        lines.append("- None yet.")
    lines.append("")
    lines.append("![Progress](progress.svg)")
    lines.append("")
    return "\n".join(lines)


def svg_circle(x: float, y: float, r: float, fill: str, opacity: float, stroke: str = "none") -> str:
    return (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
        f'fill="{fill}" opacity="{opacity:.3f}" stroke="{stroke}" />'
    )


def svg_line(x1: float, y1: float, x2: float, y2: float, color: str, width: float, opacity: float = 1.0) -> str:
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{color}" stroke-width="{width:.1f}" opacity="{opacity:.3f}" />'
    )


def svg_text(x: float, y: float, text: str, size: int, fill: str, anchor: str = "start") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}">{escape(text)}</text>'


def render_progress_svg(rows: list[ResultRow], output_path: Path) -> None:
    width, height = 1600, 900
    margin_left, margin_right, margin_top, margin_bottom = 100, 60, 80, 100
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    baseline = first_valid(rows)
    valid = [
        row for row in rows
        if same_track(row, baseline) and row.val_bpb is not None and row.val_bpb > 0 and row.status not in {"CRASH", "TIMEOUT"}
    ]
    kept = [row for row in valid if row.status == "KEEP"]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f5ef" />',
        svg_text(width / 2, 42, "Parameter Golf Autoresearch Progress", 28, "#1f2937", "middle"),
    ]

    if not valid or baseline is None:
        parts.append(svg_text(width / 2, height / 2, "No experiment rows yet in autoresearch/results.tsv", 26, "#6b7280", "middle"))
        parts.append("</svg>")
        output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
        return

    best_bpb = min(row.val_bpb for row in kept) if kept else min(row.val_bpb for row in valid)
    max_bpb = max(row.val_bpb for row in valid)
    y_min = min(best_bpb, baseline.val_bpb)
    y_max = max(max_bpb, baseline.val_bpb)
    if y_max - y_min < 1e-9:
        y_min -= 0.001
        y_max += 0.001
    pad = (y_max - y_min) * 0.1
    y_min -= pad
    y_max += pad

    def x_for(i: int) -> float:
        if len(valid) == 1:
            return margin_left + plot_w / 2
        return margin_left + (i / (len(valid) - 1)) * plot_w

    def y_for(v: float) -> float:
        return margin_top + (y_max - v) / (y_max - y_min) * plot_h

    parts.append(svg_line(margin_left, margin_top + plot_h, margin_left + plot_w, margin_top + plot_h, "#374151", 2.0))
    parts.append(svg_line(margin_left, margin_top, margin_left, margin_top + plot_h, "#374151", 2.0))

    for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y_val = y_min + frac * (y_max - y_min)
        y = y_for(y_val)
        parts.append(svg_line(margin_left, y, margin_left + plot_w, y, "#d1d5db", 1.0, 0.7))
        parts.append(svg_text(margin_left - 12, y + 5, f"{y_val:.6f}", 14, "#4b5563", "end"))

    for idx, row in enumerate(valid):
        x = x_for(idx)
        y = y_for(row.val_bpb)
        color = "#2e8b57" if row.status == "KEEP" else "#9ca3af"
        radius = 8 if row.status == "KEEP" else 4
        opacity = 0.95 if row.status == "KEEP" else 0.55
        stroke = "#111827" if row.status == "KEEP" else "none"
        parts.append(svg_circle(x, y, radius, color, opacity, stroke))
        if row.status == "KEEP":
            label = row.description if len(row.description) <= 44 else row.description[:41] + "..."
            parts.append(svg_text(x + 8, y - 8, label, 14, "#166534"))

    if kept:
        frontier = []
        running = kept[0].val_bpb
        for row in valid:
            if row.status == "KEEP":
                running = min(running, row.val_bpb)
            frontier.append(running)
        prev_x = prev_y = None
        for idx, frontier_bpb in enumerate(frontier):
            x = x_for(idx)
            y = y_for(frontier_bpb)
            if prev_x is not None:
                parts.append(svg_line(prev_x, prev_y, x, prev_y, "#15803d", 4.0, 0.85))
                parts.append(svg_line(x, prev_y, x, y, "#15803d", 4.0, 0.85))
            prev_x, prev_y = x, y

    counts = Counter(row.status for row in rows)
    track_label = ""
    if baseline and baseline.nproc_per_node is not None:
        track_label = f" | plotted track: {baseline.nproc_per_node} GPU, {baseline.max_wallclock_seconds}s"
    subtitle = (
        f"{len(rows)} experiments, "
        f"{counts.get('KEEP', 0)} kept, "
        f"{counts.get('DISCARD', 0)} discarded, "
        f"{counts.get('CRASH', 0)} crashed, "
        f"{counts.get('TIMEOUT', 0)} timed out"
        f"{track_label}"
    )
    parts.append(svg_text(width / 2, 72, subtitle, 18, "#4b5563", "middle"))
    parts.append(svg_text(width / 2, height - 28, "Experiment index", 18, "#1f2937", "middle"))
    parts.append(svg_text(26, height / 2, "val_bpb (lower is better)", 18, "#1f2937"))
    parts.append("</svg>")
    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    results_path = resolve_repo_path(args.results)
    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_results(results_path)
    summary = build_summary(rows)
    summary_path = output_dir / "summary.json"
    markdown_path = output_dir / "summary.md"
    svg_path = output_dir / "progress.svg"

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_summary_markdown(rows, summary) + "\n", encoding="utf-8")
    render_progress_svg(rows, svg_path)

    print(f"results_path: {results_path}")
    print(f"summary_path: {summary_path}")
    print(f"markdown_path: {markdown_path}")
    print(f"progress_svg: {svg_path}")
    print(f"total_experiments: {summary['total_experiments']}")
    print(f"keep: {summary['counts']['keep']}")
    print(f"discard: {summary['counts']['discard']}")
    print(f"crash: {summary['counts']['crash']}")
    print(f"timeout: {summary['counts']['timeout']}")
    if summary["best"]["val_bpb"] is not None:
        print(f"best_val_bpb: {summary['best']['val_bpb']:.8f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
