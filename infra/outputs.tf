# =============================================================================
# Description: Root-level outputs for the Snap & Cook stack (API URL, frontend
#              URL, resource names). Populated as modules are wired in per
#              tasks/plan.md. Empty for the Task 0 scaffold.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created (placeholder — outputs added per phase).
#     2026-07-01 - Added website_url output (Task 9).
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

# --- Messaging (Task 2) ---

output "job_queue_url" {
  description = "URL of the SQS job queue."
  value       = module.messaging.queue_url
}

output "job_dlq_url" {
  description = "URL of the SQS dead-letter queue."
  value       = module.messaging.dlq_url
}

# --- API (Task 4) ---

output "api_endpoint" {
  description = "Base URL for all API routes (e.g. POST <api_endpoint>/analyze)."
  value       = module.api.api_endpoint
}

# --- Frontend (Task 9) ---

output "website_url" {
  description = "Public URL of the S3 static website frontend."
  value       = module.frontend.website_url
}
