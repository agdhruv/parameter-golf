# Human Directions

This file is owned by the human. The agent should read it at setup and revisit it periodically.

Use it to steer the experiment queue without changing the autoresearch machinery.

## Current Priorities

- Default operating mode: search on 1x H100 with 300-second runs.
- Favor ideas that are likely to transfer to later 8x H100 training.
- Use occasional 600-second confirmations for strong candidates, but keep most iterations short.

## Ideas To Consider From `records/`

- None specified yet.

## Ideas To Avoid

- None specified yet.

## Search Style

- Default balance: mix local refinement with occasional broader jumps.

## Notes

- Keep changes understandable unless the measured gain is clearly worth the added complexity.
