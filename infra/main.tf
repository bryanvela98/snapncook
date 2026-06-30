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

# Modules wired in as each phase lands (see tasks/plan.md):
#   module "messaging"  { source = "./modules/messaging" ... }  # Task 2
#   module "lambdas"    { source = "./modules/lambdas" ... }    # Tasks 4,7,8
#   module "api"        { source = "./modules/api" ... }        # Tasks 4,8
#   module "frontend"   { source = "./modules/frontend" ... }   # Task 9
#   module "monitoring" { source = "./modules/monitoring" ... } # Task 11
