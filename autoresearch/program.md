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

## Hardware Context

- The current autoresearch loop runs on **1x H100**.
- The final target environment for serious submission-quality validation is **8x H100**.
- Treat the single-GPU loop as an exploration environment, not the final truth about large-scale performance.
- Prefer ideas that are likely to transfer across scale:
  - architecture changes
  - optimizer and schedule changes
  - quantization and artifact-size improvements
  - evaluation-aware improvements that should still make sense on 8 GPUs
- Be more skeptical of ideas that only exploit quirks of a single card's memory, compilation behavior, or throughput profile.

## Scope

You may read any file in the repo for context, especially:
- `README.md`
- `data/README.md`
- `autoresearch/program.md`
- `autoresearch/directions.md`
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

Before the first experiment, also read `autoresearch/directions.md`. Treat it as the human's current steering memo.

## Run Command

Use the fixed runner/parser:

```bash
python3 autoresearch/run_experiment.py --description "baseline"
```

By default, the runner launches **1 process on 1 GPU** and sets:

```bash
MAX_WALLCLOCK_SECONDS=300
```

This is intentional: use short 5-minute iterations for faster research throughput on the current machine.

For a longer confirmation run, override it explicitly:

```bash
python3 autoresearch/run_experiment.py \
  --description "confirm candidate" \
  --max-wallclock-seconds 600
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
- `nproc_per_node`
- `max_wallclock_seconds`
- `wall_seconds`
- `exit_code`
- `val_bpb`
- `artifact_bytes`
- `peak_vram_mb`

Use those values when updating `autoresearch/results.tsv`.

## Results Table

`autoresearch/results.tsv` is tab-separated with this header:

```tsv
commit	run_id	val_bpb	artifact_bytes	peak_vram_mb	nproc_per_node	max_wallclock_seconds	status	description
```

Status values:
- `keep`
- `discard`
- `crash`
- `timeout`

Use `0.00000000` for `val_bpb` and `0` for numeric fields when a run crashes before metrics are available.

## Experiment Loop

The first run must be the unmodified baseline from `autoresearch/candidate/train_gpt.py`, using the default 300-second budget unless the human explicitly asks otherwise.

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
   - compare runs primarily within the same track: same `nproc_per_node` and same `max_wallclock_seconds`
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

## Time-Budget Policy

- Default search track: **300-second runs on 1x H100**
- Use this short-run track for most experiments so you can iterate quickly.
- Periodically run a longer **600-second confirmation** on especially promising candidates.
- Do not mix 300-second and 600-second results when deciding whether a change improved the current search track.
- The analysis tools treat the baseline track as the primary frontier and exclude off-track runs from the main frontier calculation.

## Scaling Policy

- Remember that the current 1x H100 search loop is a proxy for the eventual 8x H100 target.
- Favor modifications that should plausibly retain their benefit when scaled out.
- When a change looks promising in the 300-second single-GPU track, consider one or both of:
  - a 600-second single-GPU confirmation run
  - flagging it as a candidate worth later 8x H100 verification
- In your reasoning, keep track of whether a win is:
  - likely scale-portable
  - uncertain but worth later verification
  - probably just a single-GPU local optimum

## Records Mining

The `records/` directory is an important source of ideas. Use it deliberately, not just once.

- At setup time, read several recent high-performing `records/.../README.md` files and at least inspect the associated training scripts for the ideas that seem most transferable.
- Every few experiments, or whenever progress stalls, rescan recent `records/` entries for techniques you have not yet tested.
- Pay special attention to combinations that repeatedly show up across different submissions, not just one-off tricks.
- Distinguish between:
  - ideas that are likely portable into the current candidate with modest edits
  - ideas that are tightly coupled to a very different code path or too large to adopt incrementally
- Do not blindly paste whole record scripts into the candidate. Extract the idea, estimate the artifact-size and complexity cost, and test it incrementally.
- If new record folders appear while you are running, incorporate them into your next periodic scan.

When you mine `records/`, maintain a working shortlist in your own reasoning:
- promising ideas to test soon
- ideas already tried here
- ideas rejected because they are too large, too coupled, or likely to violate the 16MB limit

## Human Steering

The human may steer the search in two ways:

1. Update `autoresearch/directions.md`
2. Give you direct instructions in chat

Always treat the latest human instruction as highest priority. Re-read `autoresearch/directions.md` at setup time and again periodically, especially before choosing a new line of attack after a plateau.

`autoresearch/directions.md` is for things like:
- themes to prioritize
- themes to avoid
- ideas from `records/` that seem especially interesting
- requests to focus on simpler changes, riskier changes, or certain model tradeoffs
- requests to do broader exploration vs local refinement

If the human gives a concrete direction, bias the experiment queue accordingly while still obeying the hard metric and size constraints.

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
