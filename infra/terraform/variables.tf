variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name (prefix for resources)"
  type        = string
  default     = "wanderbot"
}

variable "env" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "VPC CIDR"
  type        = string
  default     = "10.0.0.0/16"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.30"
}

variable "node_instance_types" {
  description = "EKS managed node group instance types"
  type        = list(string)
  default     = ["t3.large"]
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 5
}

variable "node_desired_size" {
  type    = number
  default = 2
}

# --- Data stores ---
variable "db_name" {
  type    = string
  default = "wanderbot"
}

variable "db_username" {
  type    = string
  default = "wanderbot"
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

# --- CI/CD (GitHub OIDC) ---
variable "github_owner" {
  description = "GitHub org/user that owns the repo (e.g. cse18107)"
  type        = string
}

variable "github_repo" {
  description = "Repository name (e.g. wander-bot)"
  type        = string
}

# Admin IAM principals that should get cluster-admin via EKS access entries.
variable "cluster_admin_arns" {
  description = "IAM user/role ARNs to grant cluster admin (e.g. your CLI user)"
  type        = list(string)
  default     = []
}

variable "domain" {
  description = "Public hostname for the app (must match Helm ingress.host)"
  type        = string
  default     = "wanderbot.example.com"
}

# --- Provider API keys (set via TF_VAR_* or a gitignored *.auto.tfvars) -------
variable "openai_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
variable "google_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
variable "duffel_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
variable "tavily_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
variable "bedrock_guardrail_id" {
  type    = string
  default = ""
}
variable "extra_app_env" {
  description = "Any additional WB_* env to inject into the app secret"
  type        = map(string)
  default     = {}
}
