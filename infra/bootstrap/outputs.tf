# =============================================================================
# Description: Outputs from the bootstrap stack. These values are copied into
#              the main stack's backend "s3" block (which cannot interpolate
#              variables, so the names are surfaced here for reference).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

output "state_bucket_name" {
  description = "Name of the S3 bucket holding remote Terraform state."
  value       = aws_s3_bucket.tfstate.id
}

output "lock_table_name" {
  description = "Name of the DynamoDB table used for state locking."
  value       = aws_dynamodb_table.tflock.name
}
