# =============================================================================
# Description: Outputs from the storage module, consumed by the lambda/api
#              modules (bucket + table names/ARNs for env vars and IAM policies).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

output "image_bucket_name" {
  description = "Name of the S3 bucket holding uploaded images."
  value       = aws_s3_bucket.images.id
}

output "image_bucket_arn" {
  description = "ARN of the image bucket (for IAM policies)."
  value       = aws_s3_bucket.images.arn
}

output "results_table_name" {
  description = "Name of the DynamoDB results table."
  value       = aws_dynamodb_table.results.name
}

output "results_table_arn" {
  description = "ARN of the DynamoDB results table (for IAM policies)."
  value       = aws_dynamodb_table.results.arn
}
