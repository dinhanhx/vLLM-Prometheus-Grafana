# vLLM - Prometheus - Grafana - K8S

This is a simple example that shows you how to connect vLLM metric logging to the Prometheus Grafana stack. It's also to demonstrate K8S.

## Download model

This will save model to `${PWD}/.cache/huggingface`. Please edit `HF_TOKEN` in the script,
```bash
sh download_model.sh Qwen/Qwen3-4B-Instruct-2507-FP8 # in: text, out: text
sh download_model.sh Qwen/Qwen3.5-0.8B # in: image+text, out: text
sh download_model.sh rednote-hilab/dots.mocr # in: image+text, out: text
```

## Docker

###  Create volume

Persistent volumes for prometheus and grafana data,
```bash
docker volume create prometheus-data
docker volume create grafana-storage
```

### Deploy vLLM

Create file and folder `vllm/.env` to put env of vllm. For example,
```bash
HUGGING_FACE_HUB_TOKEN="your token"
```

`command` of `vllm-openai` of `compose.yaml` should be gone through first
```bash
docker compose up
```

Example:
```
Qwen/Qwen3.5-0.8B
--max-model-len 16384
--max_num_batched_tokens 128
--max-num-seqs 1
--gpu-memory-utilization 0.8
--no-enable-prefix-caching
--trust-remote-code
--limit-mm-per-prompt '{"image":1, "video": 0, "audio": 0}'
```

```
Qwen/Qwen3-4B-Instruct-2507-FP8
--max-model-len 16384
--max-num-seqs 1
--gpu-memory-utilization 0.9
--enable-auto-tool-choice
--tool-call-parser hermes
--enable-prefix-caching
```

```
rednote-hilab/dots.mocr
--max-model-len 2048
--max_num_batched_tokens 2048
--max-num-seqs 1
--gpu-memory-utilization 0.8
--no-enable-prefix-caching
--chat-template-content-format string
--trust-remote-code
--limit-mm-per-prompt '{"image":1, "video": 0, "audio": 0}'
```

Go to `http://localhost:8809` to visit your Grafana, and import `vLLM-Grafana-dashboard.json`

You can call model at `http://localhost:8791` with 
`openai` client,
```bash
python scripts/test_image.py
```
```bash
python scripts/test_table.py
```
`llm-sandbox` for Docker sandbox,
```bash
python scripts/test_sandbox.py
```

## Minikube

- [MINIKUBE_MIGRATION_PLAN.md](MINIKUBE_MIGRATION_PLAN.md) — the full compose→k8s migration plan and manifest contents for this repo.

- [MINIKUBE_CHEATSHEET.md](MINIKUBE_CHEATSHEET.md) — the full usage for this repo.