# =============================================================================
# Description: Root module for the Snap & Cook stack. Wires together the
#              storage, messaging, lambda, api, frontend, and monitoring
#              modules. Currently empty (Task 0 scaffold) — modules are added
#              phase by phase per tasks/plan.md. Provider + shared locals live
#              here; backend config is in versions.tf.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created: provider config + scaffold (no resources yet).
# =============================================================================

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
      Stack     = "main"
    }
  }
}

# Resolves the active account/region at plan time so resource names and IAM
# policy ARNs never hard-code the account ID.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

module "storage" {
  source = "./modules/storage"

  project_name = var.project_name
  account_id   = data.aws_caller_identity.current.account_id
}

module "messaging" {
  source = "./modules/messaging"

  project_name = var.project_name
}

module "lambdas" {
  source = "./modules/lambdas"

  project_name       = var.project_name
  image_bucket_name  = module.storage.image_bucket_name
  image_bucket_arn   = module.storage.image_bucket_arn
  results_table_name = module.storage.results_table_name
  results_table_arn  = module.storage.results_table_arn
  job_queue_url      = module.messaging.queue_url
  job_queue_arn      = module.messaging.queue_arn
  bedrock_model_id   = var.bedrock_model_id
  aws_region         = var.aws_region
  account_id         = data.aws_caller_identity.current.account_id
}

module "api" {
  source = "./modules/api"

  project_name         = var.project_name
  ingest_invoke_arn    = module.lambdas.ingest_invoke_arn
  ingest_function_name = module.lambdas.ingest_function_name
}

# Modules wired in as each phase lands (see tasks/plan.md):
#   module "lambdas"    { source = "./modules/lambdas" ... }    # Tasks 4,7,8
#   module "api"        { source = "./modules/api" ... }        # Tasks 4,8
#   module "frontend"   { source = "./modules/frontend" ... }   # Task 9
#   module "monitoring" { source = "./modules/monitoring" ... } # Task 11
