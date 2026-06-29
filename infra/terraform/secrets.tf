# --- App secrets in AWS Secrets Manager --------------------------------------
# A single JSON secret; External Secrets Operator syncs it into the
# `wanderbot-secrets` k8s Secret that the API/MCP pods consume as env.

resource "random_password" "jwt" {
  length  = 48
  special = false
}

locals {
  app_secret_json = merge(
    {
      WB_DATABASE_URL         = local.db_url
      WB_APP_STORE_URL        = local.db_url
      WB_REDIS_URL            = local.redis_url
      WB_JWT_SECRET           = random_password.jwt.result
      WB_OPENAI_API_KEY       = var.openai_api_key
      WB_GOOGLE_API_KEY       = var.google_api_key
      WB_DUFFEL_API_KEY       = var.duffel_api_key
      WB_TAVILY_API_KEY       = var.tavily_api_key
      WB_BEDROCK_GUARDRAIL_ID = var.bedrock_guardrail_id
    },
    var.extra_app_env,
  )
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project}/${var.env}"
  description             = "Wanderbot app config (synced to k8s via External Secrets)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(local.app_secret_json)
}

# --- IRSA role for External Secrets Operator to read the secret --------------
data "aws_iam_policy_document" "eso_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      # ESO controller service account.
      values = ["system:serviceaccount:external-secrets:external-secrets"]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eso" {
  name               = "${local.name}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.eso_assume.json
}

resource "aws_iam_role_policy" "eso" {
  name = "read-app-secrets"
  role = aws_iam_role.eso.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = "${aws_secretsmanager_secret.app.arn}*"
    }]
  })
}
