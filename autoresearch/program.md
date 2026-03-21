# parameter-golf autoresearch

This file adapts the `autoresearch` workflow to the Parameter Golf repo.

## Goal

Autonomously search for lower `val_bpb` on a dedicated research branch without corrupting the repo's evaluation logic.

Primary objective:
- Minimize the final `val_bpb` from `final_int8_zlib_roundtrip_exact`.

Hard constraint:
- `Total submission size int8+zlib` must stay strictly below `16000000` bytes.

Soft constraints:
- Prefer simpler changes when performance is equal.
- Avoid large VRAM regressions unless the quality gain is clearly worth it.

## Scope

You may read any file in the repo for context, especially:
- `README.md`
- `data/README.md`
- `autoresearch/program.md`
- `autoresearch/run_experiment.py`
- `autoresearch/record_result.py`
- `autoresearch/analyze_results.py`
- `autoresearch/candidate/train_gpt.py`
- `records/.../README.md` and prior record scripts for ideas

You may edit only:
- `autoresearch/candidate/train_gpt.py`

You must not edit:
- `train_gpt.py`
- `train_gpt_mlx.py`
- `data/*`
- `autoresearch/run_experiment.py`
- anything under `records/`
- repo docs or infra files unless the human explicitly asks

## Setup

1. Propose a fresh branch name `autoresearch/<tag>` and create it from the current branch.
2. Verify the dataset and tokenizer exist:
   - `data/datasets/fineweb10B_sp1024/`
   - `data/tokenizers/fineweb_1024_bpe.model`
   If missing, tell the human to run:

```bash
python3 data/cached_challenge_fineweb.py --variant sp1024
```

3. If `autoresearch/results.tsv` does not exist, initialize it from the template:

```bash
cp autoresearch/results.tsv.example autoresearch/results.tsv
```

4. Confirm setup, then begin the loop.

## Run Command

Use the fixed runner/parser:

```bash
python3 autoresearch/run_experiment.py --description "baseline"
```

If the active `python3` environment is missing `torch`, use:

```bash
.venv/bin/python autoresearch/run_experiment.py --description "baseline"
```

The runner:
- executes only `autoresearch/candidate/train_gpt.py`
- writes artifacts into `autoresearch/runs/<run_id>/`
- captures the full log
- prints parsed summary lines
- writes `summary.json`

## Result Fields

The runner prints parseable lines including:
- `status`
- `run_dir`
- `log_path`
- `summary_path`
- `commit`
- `wall_seconds`
- `exit_code`
- `val_bpb`
- `artifact_bytes`
- `peak_vram_mb`

Use those values when updating `autoresearch/results.tsv`.

## Results Table

`autoresearch/results.tsv` is tab-separated with this header:

```tsv
commit	run_id	val_bpb	artifact_bytes	peak_vram_mb	status	description
```

Status values:
- `keep`
- `discard`
- `crash`
- `timeout`

Use `0.00000000` for `val_bpb` and `0` for numeric fields when a run crashes before metrics are available.

## Experiment Loop

The first run must be the unmodified baseline from `autoresearch/candidate/train_gpt.py`.

Then loop:

1. Check the current branch and current best kept result.
2. Modify only `autoresearch/candidate/train_gpt.py`.
3. Commit the experimental change.
4. Run:

```bash
python3 autoresearch/run_experiment.py --description "<short description>"
```

5. If the run crashes or times out:
   - inspect the tail of the log
   - fix and retry only if the issue is trivial
   - otherwise record `crash` or `timeout`, then revert to the previous good commit
6. If the run succeeds, compare against the best kept run:
   - keep only if `val_bpb` is lower and `artifact_bytes < 16000000`
   - otherwise record `discard` and revert to the previous good commit
7. Record every attempted run with the fixed helper:

```bash
python3 autoresearch/record_result.py \
  --summary "<path to summary.json>" \
  --status "<keep|discard|crash|timeout>" \
  --description "<short description>"
```

8. Periodically regenerate the analysis artifacts:

```bash
python3 autoresearch/analyze_results.py
```

This writes:
- `autoresearch/progress.svg`
- `autoresearch/summary.json`
- `autoresearch/summary.md`

9. Continue without asking the human for permission after each experiment.

## Heuristics

- Start with cheap local edits: hyperparameters, warmdown, sequence length, width/depth tradeoffs, optimizer settings, tying, quantization-aware structure.
- Mine `records/` for ideas, but do not copy whole submissions blindly without understanding the artifact-size tradeoff.
- Prefer one clear idea per experiment.
- When a direction looks promising, do a few local refinements before switching themes.
- Before spending many runs on a complex idea, ask whether it improves the final compressed metric, not just pre-quant quality.

## Human Handoff

When asked for a summary, report:
- current best `val_bpb`
- best run directory
- notable winning ideas
- failed ideas worth avoiding
- whether the best candidate looks worth promoting into a real `records/` submission folder
