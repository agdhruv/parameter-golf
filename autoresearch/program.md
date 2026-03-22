# parameter-golf autoresearch

This file adapts the `autoresearch` workflow to the Parameter Golf repo.

## Goal

Autonomously search for lower `val_bpb` on a dedicated research branch without corrupting the repo's evaluation logic.

Primary objective:
- Minimize the final `val_bpb` from `final_int8_zlib_roundtrip_exact`.
- Beat the current SOTA recorded in the repo README, not merely improve over the local baseline.

Hard constraint:
- `Total submission size int8+zlib` must stay strictly below `16000000` bytes.

Soft constraints:
- Prefer simpler changes when performance is equal.
- Avoid large VRAM regressions unless the quality gain is clearly worth it.

## Hardware Context

- You have access to both **1x H100** and **8x H100** execution modes.
- The real target environment is **8x H100 for 600 seconds**.
- Treat 8x H100 runs as the source-of-truth track for serious conclusions.
- Use 1x H100 runs as a scout track for faster implementation/debugging feedback and coarse ranking.
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
MAX_WALLCLOCK_SECONDS=600
```

This default is the **1x H100 scout track**.

For an 8x H100 confirmation run, use:

```bash
python3 autoresearch/run_experiment.py \
  --description "8gpu confirm candidate" \
  --nproc-per-node 8 \
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

The first run must be the unmodified baseline from `autoresearch/candidate/train_gpt.py`, using the default 1x H100, 600-second scout track unless the human explicitly asks otherwise.

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

## Track Policy

- Default scout track: **1x H100 for 600 seconds**
- Source-of-truth track: **8x H100 for 600 seconds**
- Do not mix scout-track and 8x-track results when deciding whether a change improved the frontier.
- Use scout runs for:
  - code correctness
  - cheap pruning of bad ideas
  - rough local ranking
- Use 8x runs for:
  - any candidate that looks plausibly near or beyond the current frontier
  - periodic calibration of whether scout-track wins are actually portable
  - final decisions about whether a direction is submission-worthy
- In your reasoning, keep track of whether a win is:
  - scout-only
  - likely scale-portable
  - confirmed on 8x H100

## Competitive Intelligence

The target is to beat SOTA by assembling the best transferable ideas from the field, not by ignoring everyone else's work.

- Mine the local `records/` directory continuously.
- Also inspect the upstream `openai/parameter-golf` pull requests for claims of better-than-SOTA results, especially recent open PRs and recent merged PRs.
- If multiple competitors independently converge on similar ideas, raise the priority of testing that cluster.
- Favor cross-pollination: combine the strongest ideas from different submissions when the interactions look plausible.
- Do not copy blindly. Extract the mechanism, understand the cost, then test it in the current candidate.

Preferred CLI workflow for PR mining, if `gh` is installed and authenticated:

```bash
gh pr list --repo openai/parameter-golf --state open --limit 50
gh pr list --repo openai/parameter-golf --state merged --limit 50
gh pr view <number> --repo openai/parameter-golf
gh pr diff <number> --repo openai/parameter-golf
```

Use `gh` to identify:
- claimed SOTA improvements
- new architectural ideas
- repeated motifs across unrelated PRs
- promising code paths worth porting partially

If `gh` is unavailable or unauthenticated, tell the human clearly that the PR-mining path is blocked and continue using the local `records/` directory until that is fixed.

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
- Mine `records/` and upstream PRs for ideas, but do not copy whole submissions blindly without understanding the artifact-size tradeoff.
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
