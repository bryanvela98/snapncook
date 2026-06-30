# =============================================================================
# Description: Outputs from the api module — the invoke URL is the primary
#              output consumed by the frontend and used in curl verification.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

output "api_endpoint" {
  description = "Base URL of the API Gateway HTTP API (no trailing slash)."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "api_id" {
  description = "API Gateway API ID (used by later modules adding routes)."
  value       = aws_apigatewayv2_api.api.id
}

output "execution_arn" {
  description = "Execution ARN prefix for Lambda permissions on future routes."
  value       = aws_apigatewayv2_api.api.execution_arn
}
