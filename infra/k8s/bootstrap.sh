#!/usr/bin/env bash
# Install cluster add-ons after `terraform apply`. Run once per cluster.
# Requires: kubectl pointed at the cluster, helm.
#
#   export ESO_ROLE_ARN=$(cd ../terraform && terraform output -raw external_secrets_role_arn)
#   export AWS_REGION=$(cd ../terraform && terraform output -raw region)
#   export ACME_EMAIL=you@example.com
#   ./bootstrap.sh
set -euo pipefail

: "${ESO_ROLE_ARN:?set ESO_ROLE_ARN (terraform output external_secrets_role_arn)}"
: "${AWS_REGION:?set AWS_REGION}"
: "${ACME_EMAIL:?set ACME_EMAIL for TLS issuance}"

helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add jetstack https://charts.jetstack.io
helm repo add external-secrets https://charts.external-secrets.io
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm repo update

echo "==> metrics-server (HPA)"
helm upgrade --install metrics-server metrics-server/metrics-server \
  -n kube-system

echo "==> ingress-nginx"
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx --create-namespace \
  --set controller.service.type=LoadBalancer

echo "==> cert-manager"
helm upgrade --install cert-manager jetstack/cert-manager \
  -n cert-manager --create-namespace \
  --set crds.enabled=true

echo "==> external-secrets operator (IRSA: ${ESO_ROLE_ARN})"
helm upgrade --install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace \
  --set installCRDs=true \
  --set "serviceAccount.annotations.eks\.amazonaws\.com/role-arn=${ESO_ROLE_ARN}"

echo "==> waiting for cert-manager & ESO webhooks"
kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=180s
kubectl -n external-secrets rollout status deploy/external-secrets-webhook --timeout=180s

echo "==> ClusterSecretStore + ClusterIssuer"
sed "s/__AWS_REGION__/${AWS_REGION}/g" cluster-secret-store.yaml | kubectl apply -f -
sed "s/__ACME_EMAIL__/${ACME_EMAIL}/g" cluster-issuer.yaml | kubectl apply -f -

echo "==> done. Get the ingress LoadBalancer hostname with:"
echo "    kubectl -n ingress-nginx get svc ingress-nginx-controller"
