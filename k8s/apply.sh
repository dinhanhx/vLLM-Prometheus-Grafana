#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

kubectl apply -f 00-namespace.yaml

kubectl create secret generic vllm-env \
  --from-env-file=../vllm/.env \
  -n vllm-deploy \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f 10-pvc.yaml
kubectl apply -f 20-configmaps.yaml

kubectl create configmap grafana-dashboards \
  --from-file=../grafana-provisioning/dashboards/dashboard-provisioning.yml \
  --from-file=../grafana-provisioning/dashboards/vLLM-dashboard.json \
  -n vllm-deploy \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f 21-grafana-provisioning-configmaps.yaml
kubectl apply -f 30-vllm.yaml
kubectl apply -f 31-prometheus.yaml
kubectl apply -f 32-grafana.yaml
