# Minikube Cheatsheet (for this repo)

A quick reference for developers new to Kubernetes/minikube who need to work with this project's `k8s/` manifests. Pairs with [MINIKUBE_MIGRATION_PLAN.md](MINIKUBE_MIGRATION_PLAN.md), which has the full rationale and one-time setup steps.

[Unverified] Command behavior below is standard kubectl/minikube usage; it has not been re-verified against a live run of this project's manifests in this session.

## Mental model (compose → k8s translation)

| docker compose concept | kubernetes equivalent |
|---|---|
| `docker compose up` | `kubectl apply -f k8s/` |
| a service in `compose.yaml` | a `Deployment` + `Service` |
| `container_name` | Pod (created/managed by the Deployment) |
| bind mount / named volume | `PersistentVolumeClaim` (PVC) |
| mounted config file | `ConfigMap` |
| `.env` file | `Secret` |
| `ports: "8791:8000"` | `kubectl port-forward` (no permanent host port mapping by default) |
| `docker compose logs vllm` | `kubectl logs deploy/vllm -n vllm-deploy` |
| `docker compose ps` | `kubectl get pods -n vllm-deploy` |

This repo's manifests all live in [k8s/](k8s/) and are meant to be applied together via [k8s/apply.sh](k8s/apply.sh).

## One-time cluster setup

```bash
minikube start --driver=docker --container-runtime=docker --gpus=all
minikube addons enable nvidia-device-plugin
alias kubectl="minikube kubectl --"   # or install kubectl separately
```

Check the cluster is healthy and GPU-visible:

```bash
minikube status
kubectl get nodes
kubectl describe nodes | grep -i gpu
```

## Deploying this project

```bash
cd k8s
./apply.sh
```

This creates the namespace, the `vllm-env` Secret (from `vllm/.env`), PVCs, ConfigMaps, and the three Deployments/Services (vllm, prometheus, grafana), in the order they need to exist.

To re-apply after editing a manifest, just re-run `./apply.sh` or `kubectl apply -f <file>` — applying is idempotent.

## Everyday commands

**See what's running:**
```bash
kubectl get pods -n vllm-deploy
kubectl get pods -n vllm-deploy -w        # watch live (like `docker compose ps` in a loop)
kubectl get all -n vllm-deploy            # pods, services, deployments in one shot
```

**Logs:**
```bash
kubectl logs deploy/vllm -n vllm-deploy
kubectl logs deploy/vllm -n vllm-deploy -f          # follow, like `docker compose logs -f`
kubectl logs deploy/vllm -n vllm-deploy --previous   # logs from the last crashed container
```

**Shell into a running pod:**
```bash
kubectl exec -it deploy/vllm -n vllm-deploy -- bash
```

**Describe a pod (why is it Pending/CrashLoopBackOff?):**
```bash
kubectl describe pod -l app=vllm -n vllm-deploy
```
Read the `Events:` section at the bottom first — it usually says exactly why scheduling or startup failed (e.g. no GPU available, image pull error, failed probe).

**Access a service from your machine (compose used host ports; k8s needs an explicit tunnel):**
```bash
kubectl -n vllm-deploy port-forward svc/vllm 8791:8000
kubectl -n vllm-deploy port-forward svc/prometheus 8808:9090
kubectl -n vllm-deploy port-forward svc/grafana 8809:3000
```
Each of these blocks the terminal — run each in its own terminal/tmux pane, or background with `&`.

**Restart a deployment (like `docker compose restart <service>`):**
```bash
kubectl rollout restart deployment/vllm -n vllm-deploy
kubectl rollout status deployment/vllm -n vllm-deploy
```

**Stop pods without deleting config (scale a deployment to 0, like `docker compose stop <service>`):**
```bash
kubectl scale deployment/vllm -n vllm-deploy --replicas=0
kubectl scale deployment/vllm -n vllm-deploy --replicas=1   # start it back up
```

**Delete a specific pod (it will be recreated by its Deployment):**
```bash
kubectl delete pod -l app=vllm -n vllm-deploy
```
Useful for forcing a fresh pod without editing anything — the Deployment's controller immediately schedules a replacement.

**`docker compose down` equivalent (remove Deployments/Services, keep PVC data):**
```bash
kubectl delete deployment,service -n vllm-deploy --all
```
This tears down the running workloads and their Services but leaves ConfigMaps, the Secret, and PVCs (cached model weights, Prometheus/Grafana data) intact — re-run `./apply.sh` to bring it back up with the same data.

**`docker compose down -v` equivalent (also wipe volumes) / delete everything for this project:**
```bash
kubectl delete namespace vllm-deploy
```
This is destructive — it deletes the Deployments, Services, ConfigMaps, Secret, and PVCs (i.e. the cached model weights and Prometheus/Grafana data) in one shot. Confirm you actually want to lose the PVC data before running it.

## Editing config (ConfigMaps/Secrets aren't live-reloaded)

Unlike a bind mount in compose, editing `prometheus.yml` or `grafana-provisioning/*` on disk does **not** automatically update the running pod. You must recreate the ConfigMap and restart the pod:

```bash
kubectl create configmap prometheus-config --from-file=../prometheus.yml -n vllm-deploy \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/prometheus -n vllm-deploy
```

Same pattern for the Grafana ConfigMaps (see [k8s/apply.sh](k8s/apply.sh) for the exact `--from-file` invocations used at initial deploy time).

## Debugging checklist

1. `kubectl get pods -n vllm-deploy` — is it `Running`/`Ready`, `Pending`, or `CrashLoopBackOff`?
2. `kubectl describe pod -l app=<vllm|prometheus|grafana> -n vllm-deploy` — check `Events:` for scheduling/probe failures.
3. `kubectl logs deploy/<name> -n vllm-deploy` — check application-level errors.
4. `Pending` pod + GPU workload → almost always means the `nvidia.com/gpu: 1` resource request can't be satisfied. Re-check `minikube addons enable nvidia-device-plugin` and `kubectl describe nodes | grep -i gpu`.
5. Prometheus shows target `DOWN` → check the Service name/port match what's in `prometheus.yml`, and that the vllm pod's readiness probe (`/health`) is passing.

## Cluster lifecycle

```bash
minikube stop      # stop the cluster VM/container, keep all state on disk
minikube start      # resume where you left off
minikube delete     # destroy the cluster entirely (irreversible — all namespaces, PVC data, etc. gone)
```

`minikube stop`/`start` is the equivalent of turning your machine off/on — the vllm-deploy namespace and its PVCs survive. `minikube delete` is a full reset; only use it if you want to start over from an empty cluster.


## Further reading

- [MINIKUBE_MIGRATION_PLAN.md](MINIKUBE_MIGRATION_PLAN.md) — the full compose→k8s migration plan and manifest contents for this repo.
- [k8s/](k8s/) — actual manifests and the `apply.sh` deploy script.
- https://kubernetes.io/docs/reference/kubectl/cheatsheet/ — official kubectl cheatsheet.
- https://minikube.sigs.k8s.io/docs/ — official minikube docs.
