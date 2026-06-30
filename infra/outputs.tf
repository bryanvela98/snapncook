# =============================================================================
# Description: Root-level outputs for the Snap & Cook stack (API URL, frontend
#              URL, resource names). Populated as modules are wired in per
#              tasks/plan.md. Empty for the Task 0 scaffold.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created (placeholder — outputs added per phase).
# =============================================================================

output "account_id" {
  description = "AWS account the stack is deployed into."
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS region the stack is deployed into."
  value       = data.aws_region.current.name
}

# --- Storage (Task 1) ---

output "image_bucket_name" {
  description = "S3 bucket for uploaded ingredient images."
  value       = module.storage.image_bucket_name
}

output "results_table_name" {
  description = "DynamoDB table storing request results."
  value       = module.storage.results_table_name
}
