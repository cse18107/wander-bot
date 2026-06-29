# AWS deployment (EKS) — runbook

Provisions the whole stack on AWS and deploys Wanderbot to EKS via Helm.

```
infra/
  terraform/   # VPC, EKS, RDS Postgres, ElastiCache Redis, Secrets Manager, IAM (OIDC)
  k8s/         # cluster add-ons: ingress-nginx, cert-manager, External Secrets, issuers
```

**Architecture**

```
Route53 -> ingress-nginx (ALB/NLB) ──/api,/healthz,/metrics──> wanderbot-api (FastAPI)
                                   └──/ (everything else)──────> wanderbot-web (Nginx SPA)
wanderbot-api ──> RDS Postgres (app store + checkpointer), ElastiCache Redis, wanderbot-mcp
Secrets Manager (wanderbot/prod) ──External Secrets──> wanderbot-secrets (env)
GHCR images ──(pull secret)──> nodes        GitHub Actions ──OIDC──> AWS (Helm deploy)
```

---

## Prerequisites
- AWS account + `aws` CLI configured (`aws sts get-caller-identity`)
- `terraform >= 1.6`, `kubectl`, `helm`
- The GHCR images are built by CI (`wanderbot-api/web/mcp`). Make the GHCR
  packages **public**, or create a pull secret (step 5).

## 1. Provision AWS infra (Terraform)

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # edit: github_owner/repo, cluster_admin_arns, domain
# provider keys via env (don't commit):
export TF_VAR_duffel_api_key=... TF_VAR_tavily_api_key=... TF_VAR_google_api_key=...

terraform init
terraform apply        # ~15-20 min (EKS + RDS)
```

Note the outputs:

```bash
terraform output kubeconfig_command          # configure kubectl
terraform output external_secrets_role_arn   # for the bootstrap script
terraform output github_cd_role_arn          # GitHub secret AWS_DEPLOY_ROLE_ARN
terraform output cluster_name region
```

```bash
eval "$(terraform output -raw kubeconfig_command)"
kubectl get nodes
```

## 2. Install cluster add-ons

```bash
cd ../k8s
export ESO_ROLE_ARN=$(cd ../terraform && terraform output -raw external_secrets_role_arn)
export AWS_REGION=$(cd ../terraform && terraform output -raw region)
export ACME_EMAIL=you@example.com
./bootstrap.sh
```

This installs metrics-server, ingress-nginx, cert-manager, External Secrets Operator,
and applies the `ClusterSecretStore` + Let's Encrypt `ClusterIssuer`.

## 3. DNS

```bash
kubectl -n ingress-nginx get svc ingress-nginx-controller   # copy EXTERNAL-IP/hostname
```
Point your domain (`domain` in tfvars, and `ingress.host` in the Helm values) at it
via Route53 (CNAME/ALIAS). cert-manager issues TLS automatically on first request.

## 4. Configure GitHub for CD

In the repo → Settings:
- **Secrets** → `AWS_DEPLOY_ROLE_ARN` = `terraform output github_cd_role_arn`
- **Variables** → `AWS_REGION`, `EKS_CLUSTER` (= `terraform output cluster_name`),
  and `DEPLOY_ENABLED` = `true`
- **Environments** → create `staging` and `production`; add required reviewers to
  `production` for the manual approval gate.

## 5. (If GHCR is private) image pull secret

```bash
for ns in wanderbot wanderbot-staging; do
  kubectl create ns $ns --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n $ns create secret docker-registry ghcr-pull \
    --docker-server=ghcr.io --docker-username=<gh-user> --docker-password=<gh-PAT(read:packages)>
done
```
Then set in `values-prod.yaml` / `values-staging.yaml`:
```yaml
imagePullSecrets: [{ name: ghcr-pull }]
ingress: { host: wanderbot.yourdomain.com }
```

## 6. Deploy

Push to `main` (or re-run the CD workflow). With `DEPLOY_ENABLED=true` it builds the
images, then `helm upgrade` to staging → production (manual approval). Verify:

```bash
kubectl -n wanderbot get pods
curl -fsS https://wanderbot.yourdomain.com/healthz
```

Manual deploy (without CI):
```bash
helm upgrade --install wanderbot deploy/helm/wanderbot \
  -f deploy/helm/wanderbot/values-prod.yaml \
  --set image.tag=<git-sha> --namespace wanderbot --create-namespace --atomic --wait
```

## Updating secrets / provider keys
Edit the JSON in Secrets Manager (`wanderbot/prod`) — via `terraform apply` after
changing `TF_VAR_*`, or directly:
```bash
aws secretsmanager put-secret-value --secret-id wanderbot/prod --secret-string '{...}'
kubectl -n wanderbot annotate externalsecret wanderbot-secrets force-sync=$(date +%s) --overwrite
```

## Teardown
```bash
helm uninstall wanderbot -n wanderbot
cd infra/terraform && terraform destroy
```

> Cost note: EKS control plane (~$0.10/hr) + 2× t3.large nodes + RDS + ElastiCache +
> NAT gateway ≈ **$150-250/mo**. Scale nodes/instances down (or use the
> single-EC2/compose path) for a cheaper demo.
