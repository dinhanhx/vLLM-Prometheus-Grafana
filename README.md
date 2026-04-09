# vLLM - Prometheus - Grafana

This is a simple example that shows you how to connect vLLM metric logging to the Prometheus/Grafana stack. 

## Download model

This will save model to `${PWD}/.cache/huggingface`. Please edit `HF_TOKEN` in the script,
```bash
sh download_model.sh Qwen/Qwen3-4B-Instruct-2507-FP8 # in: text, out: text
sh download_model.sh Qwen/Qwen3.5-2B # in: image+text, out: text
```

## Create volume

Persistent volumes for prometheus and grafana data,
```bash
docker volume create prometheus-data
docker volume create grafana-storage
```

## Deploy vLLM

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
Qwen/Qwen3.5-2B
--max-model-len 16384
--max-num-seqs 1
--gpu-memory-utilization 0.9
--enable-prefix-caching
--limit-mm-per-prompt "{\"images\":1}"
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

Go to `http://localhost:8809` to visit your Grafana, and import `vLLM-Grafana-dashboard.json`

You can call model at `http://localhost:8791` with `openai` client and `llm-sandbox` for Docker sandbox,
```bash
python scripts/test_sandbox.py
```