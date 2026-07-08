# Migration Plan: docker compose → Minikube

[Unverified] This plan is derived from reading the current `compose.yaml` and provisioning files in this repo. It has not been tested against a running minikube cluster since minikube is not installed on this machine — validate each step in your own environment.

## Current stack (from compose.yaml)

- `vllm`: GPU service (`runtime: nvidia`, 1 GPU reservation), port 8000→8791, reads `vllm/.env` (contains `HUGGING_FACE_HUB_TOKEN`), mounts `.cache/` for model cache, has an HTTP healthcheck at `/health`.
- `prometheus`: scrapes `vllm:8000`, port 9090→8808, config from `prometheus.yml`, persists to named volume `prometheus-data`.
- `grafana`: port 3000→8809, provisioned from `grafana-provisioning/` (mounted whole into `/etc/grafana/provisioning/`), split into `grafana-provisioning/datasources/datasource-provisioning.yml` and `grafana-provisioning/dashboards/` (`dashboard-provisioning.yml`, `vLLM-dashboard.json`), persists to named volume `grafana-storage`.

## Prerequisites

0. **Host requirements:**
   - Linux OS (Ubuntu 20.04+ recommended), NVIDIA GPU with drivers installed, root/admin access.
   - NVIDIA Container Toolkit installed on the host (required for GPU passthrough into containers/pods).
   - Docker usable without `sudo`: `sudo usermod -aG docker $USER && newgrp docker`.

1. **Install Minikube with GPU support:**
     ```bash
     curl -LO https://github.com/kubernetes/minikube/releases/latest/download/minikube-linux-amd64
     sudo install minikube-linux-amd64 /usr/local/bin/minikube && rm minikube-linux-amd64
     ```

     ```bash
     # make your life easier by adding the following to your shell config
     alias kubectl="minikube kubectl --"
     ```

     ```bash
     minikube start --driver=docker --container-runtime=docker --gpus=all
     minikube addons enable nvidia-device-plugin
     ```

2. **Install Helm** (recommended for templating the Prometheus/Grafana manifests instead of hand-written YAML):
   ```bash
   curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
   chmod 700 get_helm.sh
   ./get_helm.sh
   ```

3. **Verify the cluster is GPU-ready before deploying anything:**
   ```bash
   minikube status
   kubectl describe nodes | grep -i gpu
   kubectl run gpu-test --image=nvidia/cuda:12.2.0-runtime-ubuntu22.04 --rm -it --restart=Never -- nvidia-smi
   ```
   If the GPU operator deployment fails with "too many open files", see the [Kind known-issues doc](https://kind.sigs.k8s.io/docs/user/known-issues#pod-errors-due-to-too-many-open-files) (applies to minikube too — raise host `inotify`/file-descriptor limits).

## Step 1 — Namespace

```bash
kubectl create namespace vllm-deploy
```

## Step 2 — Secrets

Do not commit `vllm/.env` values into manifests. Create a Kubernetes Secret from the existing file:

```bash
kubectl create secret generic vllm-env \
  --from-env-file=vllm/.env \
  -n vllm-deploy
```

## Step 3 — Persistent storage

Replace bind mounts and named volumes with PVCs.

| compose volume | k8s equivalent |
|---|---|
| `${PWD}/.cache/` (vllm model cache) | PVC `vllm-cache` |
| `prometheus-data` (external volume) | PVC `prometheus-data` |
| `grafana-storage` (external volume) | PVC `grafana-storage` |
| config files (`prometheus.yml`, `grafana.ini`, `grafana-provisioning/datasources/*.yml`, `grafana-provisioning/dashboards/*.yml`, `grafana-provisioning/dashboards/*.json`) | ConfigMaps |

Example PVC (repeat for each, sizing per your model/data needs):

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: vllm-cache
  namespace: vllm-deploy
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 50Gi
```

Create ConfigMaps from existing files. Grafana provisioning is now split into two ConfigMaps, one per subfolder, so each can be mounted at its matching path under `/etc/grafana/provisioning/`:

```bash
kubectl create configmap prometheus-config --from-file=prometheus.yml -n vllm-deploy

kubectl create configmap grafana-ini --from-file=grafana.ini=grafana.ini -n vllm-deploy

kubectl create configmap grafana-datasources \
  --from-file=grafana-provisioning/datasources/ \
  -n vllm-deploy

kubectl create configmap grafana-dashboards \
  --from-file=grafana-provisioning/dashboards/ \
  -n vllm-deploy
```

## Step 4 — vLLM Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: vllm-deploy
spec:
  replicas: 1
  selector:
    matchLabels: { app: vllm }
  template:
    metadata:
      labels: { app: vllm }
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:v0.20.1
          args:
            - "Qwen/Qwen3.5-0.8B"
            - "--max-model-len=1024"
            - "--max_num_batched_tokens=1024"
            - "--max-num-seqs=1"
            - "--gpu-memory-utilization=0.9"
            - "--no-enable-prefix-caching"
            - "--trust-remote-code"
            - '--limit-mm-per-prompt={"image":0,"video":0,"audio":0}'
          envFrom:
            - secretRef: { name: vllm-env }
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: 1
          volumeMounts:
            - name: cache
              mountPath: /root/.cache
          readinessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 60
            periodSeconds: 30
            timeoutSeconds: 10
            failureThreshold: 10
          livenessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 60
            periodSeconds: 30
            timeoutSeconds: 10
            failureThreshold: 10
      volumes:
        - name: cache
          persistentVolumeClaim: { claimName: vllm-cache }
---
apiVersion: v1
kind: Service
metadata:
  name: vllm
  namespace: vllm-deploy
spec:
  selector: { app: vllm }
  ports:
    - port: 8000
      targetPort: 8000
```

Notes:
- `--limit-mm-per-prompt` uses JSON; quoting in a YAML args list differs from the shell `command:` string in compose — verify vLLM parses it correctly, e.g. by checking pod logs after apply.
- The compose `depends_on: condition: service_healthy` pattern has no direct k8s equivalent — Prometheus/Grafana pods should use `initContainers` (wait-for) or simply tolerate scrape failures until vLLM's readiness probe passes, since Kubernetes doesn't block cross-pod startup ordering natively.

## Step 5 — Prometheus Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: vllm-deploy
spec:
  replicas: 1
  selector:
    matchLabels: { app: prometheus }
  template:
    metadata:
      labels: { app: prometheus }
    spec:
      containers:
        - name: prometheus
          image: prom/prometheus
          ports:
            - containerPort: 9090
          volumeMounts:
            - name: config
              mountPath: /etc/prometheus/prometheus.yml
              subPath: prometheus.yml
            - name: data
              mountPath: /prometheus
      volumes:
        - name: config
          configMap: { name: prometheus-config }
        - name: data
          persistentVolumeClaim: { claimName: prometheus-data }
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: vllm-deploy
spec:
  selector: { app: prometheus }
  ports:
    - port: 9090
      targetPort: 9090
```

Update `prometheus.yml` scrape target from `vllm:8000` to the k8s Service DNS name — since the Service is also named `vllm` in the same namespace, `vllm:8000` (or `vllm.vllm-deploy.svc.cluster.local:8000`) continues to work unchanged.

## Step 6 — Grafana Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: vllm-deploy
spec:
  replicas: 1
  selector:
    matchLabels: { app: grafana }
  template:
    metadata:
      labels: { app: grafana }
    spec:
      containers:
        - name: grafana
          image: grafana/grafana-enterprise
          ports:
            - containerPort: 3000
          volumeMounts:
            - name: storage
              mountPath: /var/lib/grafana
            - name: grafana-ini
              mountPath: /etc/grafana/grafana.ini
              subPath: grafana.ini
            - name: datasources
              mountPath: /etc/grafana/provisioning/datasources
            - name: dashboards
              mountPath: /etc/grafana/provisioning/dashboards
      volumes:
        - name: storage
          persistentVolumeClaim: { claimName: grafana-storage }
        - name: grafana-ini
          configMap: { name: grafana-ini }
        - name: datasources
          configMap: { name: grafana-datasources }
        - name: dashboards
          configMap: { name: grafana-dashboards }
---
apiVersion: v1
kind: Service
metadata:
  name: grafana
  namespace: vllm-deploy
spec:
  selector: { app: grafana }
  ports:
    - port: 3000
      targetPort: 3000
```

The datasource provisioning file points at `http://prometheus:9090` — unchanged, since the Service name matches.

## Step 7 — Expose services locally

Compose used host port mappings (8791, 8808, 8809). Minikube equivalents:

```bash
kubectl -n vllm-deploy port-forward svc/vllm 8791:8000
kubectl -n vllm-deploy port-forward svc/prometheus 8808:9090
kubectl -n vllm-deploy port-forward svc/grafana 8809:3000
```

Or use `minikube service <name> -n vllm-deploy` for NodePort-style access if the Services are changed to `type: NodePort`.

## Step 8 — Apply and verify

```bash
kubectl apply -f k8s/
kubectl -n vllm-deploy get pods -w
kubectl -n vllm-deploy logs deploy/vllm
kubectl -n vllm-deploy describe pod -l app=vllm   # check GPU scheduling if pod is Pending
```

Verify:
- vLLM pod reaches `Running`/`Ready` and `/health` responds via port-forward.
- Prometheus target `vllm:8000` shows as `UP` in the Prometheus UI (`/targets`).
- Grafana dashboard loads with the provisioned vLLM dashboard and data flowing from Prometheus.

## Getting a locally git-cloned model onto the cluster (before vLLM starts)

If a model is git-cloned to a local folder (e.g. `git-clone-models/<model-name>`) rather than pulled by vLLM/HF Hub at container startup, it needs to land on the `vllm-cache` PVC (mounted at `/root/.cache` per Step 4) — and ideally *before* the vLLM Deployment (Step 4) is applied, so the first pod start already has the model instead of failing/pulling on demand.

**Option 1 — pre-seed the PVC with a throwaway helper pod (recommended):**

`kubectl cp` requires a pod that mounts the target PVC — there's no way to copy into a PVC with zero pods. So run this after Steps 1–3 (namespace, secret, PVCs) but before Step 4 (vLLM Deployment):

```bash
kubectl run model-seed -n vllm-deploy --image=busybox --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"model-seed","image":"busybox","command":["sleep","3600"],"volumeMounts":[{"name":"cache","mountPath":"/root/.cache"}]}],"volumes":[{"name":"cache","persistentVolumeClaim":{"claimName":"vllm-cache"}}]}}'
kubectl wait --for=condition=Ready pod/model-seed -n vllm-deploy --timeout=60s

kubectl cp git-clone-models/<model-name> vllm-deploy/model-seed:/root/.cache/<model-name>

kubectl delete pod model-seed -n vllm-deploy
# now apply the vLLM Deployment (Step 4) — model is already on the PVC
```

No manifest changes to the vLLM Deployment itself required — the copy lands directly on the PVC it will mount. `kubectl cp` tars the data over the API server, so for very large models (tens of GB) it can be slow or flaky.

**Option 2 — `minikube mount` (live host directory, no copy, no PVC pre-seed needed):**
```bash
minikube mount /path/to/vllm-deploy/git-clone-models:/mnt/models
```
Start this (and leave it running in its own terminal) before applying the vLLM Deployment. It live-mounts the host folder into the minikube node. Requires adding a `hostPath` volume (and volumeMount) to the vLLM Deployment pointing at `/mnt/models` instead of/alongside the PVC — more invasive, but the model is available from the very first pod start with no copy step, and local file changes reflect immediately.

## Observability best practices

[Unverified] Drawn from the [vLLM Prometheus/Grafana observability example](https://docs.vllm.ai/en/v0.20.1/examples/observability/prometheus_grafana/).

- vLLM exposes Prometheus metrics on `/metrics` by default (no extra flag needed) — confirm via `curl http://<pod>:8000/metrics` after rollout.
- Login default for the Grafana image is `admin`/`admin`; the current stack sets `grafana.ini` instead — verify the ConfigMap-mounted `grafana.ini` still forces a password change or sets `GF_SECURITY_ADMIN_PASSWORD`, since a stray default-credential Grafana on a `NodePort`/`Ingress` is a real exposure if this cluster is ever reachable beyond localhost.
- After migrating, sanity-check the dashboard against the documented panel set (E2E latency P50/P90/P95/P99, token throughput, inter-token latency, KV cache utilization %, scheduler running/waiting requests, TTFT, prompt/generation length heatmaps, finish reasons, queue/prefill/decode time) to confirm `vLLM-dashboard.json` didn't lose panels in the ConfigMap round-trip.
- To generate load for verifying the dashboard end-to-end post-migration, `vllm bench serve` against the port-forwarded vLLM Service works the same as against the compose service — just point `--endpoint`/host at the forwarded port (e.g. `8791`).
- Keep the Prometheus scrape interval (`prometheus.yml`, currently 5s per the repo's existing config style) unchanged when moving to a ConfigMap — no k8s-specific reason to change it, and mismatched scrape/evaluation intervals across the migration would make historical dashboards non-comparable.

## Open items to confirm with you


- Model cache PVC sizing (depends on which models get pulled at runtime beyond `Qwen/Qwen3.5-0.8B`).
- Whether you want Services as `ClusterIP` + `port-forward` (matches this plan) or `NodePort`/`Ingress` for more persistent local access.
