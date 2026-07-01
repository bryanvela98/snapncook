# =============================================================================
# Description: Outputs from the frontend module. The website_url is the public
#              S3 static website endpoint consumed by the root outputs and shown
#              after terraform apply.
# Last Modified By: bvela
# Created: 2026-07-01
# Last Modified:
#     2026-07-01 - File created.
# =============================================================================

output "website_url" {
  description = "Public HTTP URL of the S3 static website (index.html entry point)."
  value       = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}

output "bucket_name" {
  description = "Name of the S3 bucket hosting the frontend."
  value       = aws_s3_bucket.frontend.id
}