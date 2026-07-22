#!/usr/bin/env bash
# Step 1: Kubernetes (k3s) + ingress + Akash CRDs/operators on the provider machine.
# Run as root on Ubuntu 22.04/24.04. Idempotent-ish; safe to re-run.
#
# What it does:
#   - installs k3s with traefik disabled (Akash uses ingress-nginx)
#   - wires kubeconfig for the current user
#   - installs ingress-nginx (akash gateway class) + cert-manager
#   - adds the Akash helm repo and installs the hostname + inventory operators
#
# It does NOT install akash-node (we use the public RPC rpc.abakos.ai) and does NOT
# install the provider chart (we run provider-services from source - see step 2/3).
set -euo pipefail

echo "== [1/6] install k3s (traefik disabled) =="
if ! command -v k3s >/dev/null 2>&1; then
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable=traefik" sh -s -
fi

echo "== [2/6] kubeconfig =="
mkdir -p "$HOME/.kube"
sudo cat /etc/rancher/k3s/k3s.yaml | tee "$HOME/.kube/config" >/dev/null
sudo chown "$(id -u):$(id -g)" "$HOME/.kube/config"
export KUBECONFIG="$HOME/.kube/config"
kubectl get nodes

echo "== [3/6] helm + akash repo =="
if ! command -v helm >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi
helm repo add akash https://akash-network.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
helm repo update

echo "== [4/6] namespaces =="
kubectl create ns lease 2>/dev/null || true
kubectl create ns akash-services 2>/dev/null || true
kubectl label ns akash-services akash.network=true --overwrite
kubectl create ns ingress-nginx 2>/dev/null || true
kubectl label ns ingress-nginx app.kubernetes.io/name=ingress-nginx --overwrite

echo "== [5/6] ingress-nginx (akash gateway) + cert-manager =="
# Akash deployments are exposed through an ingress-nginx configured as the akash gateway.
helm upgrade --install akash-ingress ingress-nginx/ingress-nginx -n ingress-nginx \
  --set controller.ingressClassResource.name=akash-ingress-class \
  --set controller.ingressClass=akash-ingress-class \
  --set controller.ingressClassResource.default=false \
  --set controller.service.type=LoadBalancer \
  --set tcp.1317="akash-services/akash-provider:1317" 2>/dev/null || \
  echo "   (ingress-nginx install returned non-zero - inspect: kubectl -n ingress-nginx get pods)"
kubectl label ingressclass akash-ingress-class akash.network=true --overwrite 2>/dev/null || true
helm upgrade --install cert-manager jetstack/cert-manager -n cert-manager --create-namespace \
  --set installCRDs=true 2>/dev/null || echo "   (cert-manager install returned non-zero)"

echo "== [6/6] Akash CRDs + operators (hostname, inventory) =="
# Hostname operator chart requires Gateway API HTTPRoute CRDs.
if ! kubectl get crd httproutes.gateway.networking.k8s.io >/dev/null 2>&1; then
  curl -fsSL https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml \
    | kubectl apply -f -
fi
helm upgrade --install akash-hostname-operator akash/akash-hostname-operator -n akash-services 2>/dev/null || \
  echo "   (hostname-operator: check chart availability / values)"
helm upgrade --install inventory-operator akash/akash-inventory-operator -n akash-services 2>/dev/null || \
  echo "   (inventory-operator: check chart availability / values)"

echo
echo "== done. verify: =="
echo "  kubectl get pods -A"
echo "  kubectl get ingressclass"
echo "Next: scripts/10-build-provider.sh"
