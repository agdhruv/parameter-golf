# Human Directions

This file is owned by the human. The agent should read it at setup and revisit it periodically.

Use it to steer the experiment queue without changing the autoresearch machinery.

## Current Priorities

- Objective: beat the current README SOTA, not just improve over the local baseline.
- Default scout track: 1x H100 with 600-second runs.
- Source-of-truth track: 8x H100 with 600-second runs for strong candidates.
- Favor ideas that are likely to transfer to 8x H100.
- Strategy: combine the best portable ideas from many strong submissions instead of betting on a single isolated approach.
- Use the repo-local `gh-cli` and `runpodctl` skills plus the `runpod-8xh100-playbook.md` file when available.

## Ideas To Consider From `records/`

- Look for ideas that appear in both local `records/` and recent upstream PRs.
- Prioritize combinations of strong ideas from different authors when the interactions seem plausible.

## Ideas To Avoid

- None specified yet.

## Search Style

- Default balance: scout locally on 1 GPU, mine top records and important PRs continuously, then confirm promising wins on 8 GPUs.

## Notes

- Keep changes understandable unless the measured gain is clearly worth the added complexity.
- The current machine is the orchestrator. The 8x pod is a temporary worker, not a place to run a second autonomous research loop.
