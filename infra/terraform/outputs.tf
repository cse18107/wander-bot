output "region" {
  value = var.region
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "kubeconfig_command" {
  description = "Run this to point kubectl at the cluster"
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "rds_endpoint" {
  value = aws_db_instance.this.address
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "app_secret_name" {
  value = aws_secretsmanager_secret.app.name
}

output "external_secrets_role_arn" {
  description = "Annotate the ESO service account with this (eks.amazonaws.com/role-arn)"
  value       = aws_iam_role.eso.arn
}

output "github_cd_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN GitHub secret for the CD workflow"
  value       = aws_iam_role.github_cd.arn
}
