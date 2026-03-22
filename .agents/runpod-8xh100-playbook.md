# RunPod 8x H100 Runbook

Use this file as an instruction sheet for an agentic loop that needs to:

1. create an `8x H100` pod
2. SSH into it
3. clone the repo
4. download tokenizer and dataset files into the repo checkout
5. run an experiment
6. stop the run if needed
7. delete the pod immediately after finishing

## 1. Create the pod

Check capacity:

```bash
runpodctl get cloud 8
runpodctl get cloud 8 -s
```

Create the pod with the command that worked in this environment:

```bash
runpodctl create pod \
  --name parameter-golf-h100x8 \
  --imageName runpod/parameter-golf:latest \
  --gpuCount 8 \
  --gpuType 'NVIDIA H100 80GB HBM3' \
  --startSSH \
  --secureCloud
```

If that fails with a no-capacity error, retry once. Then try:

```bash
runpodctl create pod \
  --name parameter-golf-h100x8 \
  --imageName runpod/parameter-golf:latest \
  --gpuCount 8 \
  --gpuType 'NVIDIA H100 NVL' \
  --startSSH \
  --secureCloud
```

## 2. Get the pod ID and podHostId

List pods:

```bash
runpodctl get pod
```

Fetch the RunPod GraphQL metadata to get `podHostId` for SSH:

```bash
curl -s https://api.runpod.io/graphql \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $(sed -n 's/^apikey = \"\\(.*\\)\"/\\1/p' ~/.runpod/config.toml)" \
  --data '{"query":"query { myself { pods { id name machine { podHostId } } } }"}'
```

Match the target pod by `id` or `name` and record:

- pod ID, for example `lu7t9f64kpdu1z`
- podHostId, for example `lu7t9f64kpdu1z-64410f71`

## 3. Ensure SSH works

If SSH auth is not already working, generate and register a local key:

```bash
ssh-keygen -t ed25519 -N '' -f /root/.runpod/ssh/codex-runpod-smoke
runpodctl ssh add-key --key-file /root/.runpod/ssh/codex-runpod-smoke.pub
```

Connect with:

```bash
ssh -tt -i /root/.runpod/ssh/codex-runpod-smoke \
  -o StrictHostKeyChecking=no \
  <podHostId>@ssh.runpod.io
```

Use `-tt`. The proxy SSH path required a PTY in this environment.

## 4. Prepare the repo and data inside the pod

Inside the pod shell:

```bash
cd /workspace
rm -rf parameter-golf-smoke
git clone --depth 1 https://github.com/agdhruv/parameter-golf.git parameter-golf-smoke
cd /workspace/parameter-golf-smoke
```

Download the tokenizer and dataset files into the repo checkout:

For a minimal smoke test:

```bash
python data/cached_challenge_fineweb.py --variant sp1024 --train-shards 1
```

For a 2-minute run that should not reuse a single training shard repeatedly:

```bash
python data/cached_challenge_fineweb.py --variant sp1024 --train-shards 14
```

These commands download into:

- `./data/datasets/fineweb10B_sp1024/`
- `./data/tokenizers/`

## 5. Run the experiment

Example 2-minute run on all 8 GPUs:

```bash
cd /workspace/parameter-golf-smoke
RUN_ID=smoke_h100x8_2min \
DATA_PATH=./data/datasets/fineweb10B_sp1024 \
TOKENIZER_PATH=./data/tokenizers/fineweb_1024_bpe.model \
VOCAB_SIZE=1024 \
MAX_WALLCLOCK_SECONDS=120 \
torchrun --standalone --nproc_per_node=8 train_gpt.py
```

The final metric to read is the `final_int8_zlib_roundtrip_exact` line.

## 6. Stop the experiment if needed

If attached over SSH, send `Ctrl-C`.

If controlling an attached exec session programmatically, write:

```text
\u0003
```

Wait until the worker shutdown messages complete and the shell prompt returns.

## 7. Tear down the pod

From the local machine, delete the pod immediately after the run:

```bash
runpodctl remove pod <pod_id>
runpodctl get pod
```

Confirm the `8x H100` pod is no longer listed.
