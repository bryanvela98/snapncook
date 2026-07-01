# =============================================================================
# Description: Outputs from the lambdas module consumed by the api module
#              (invoke ARNs for the API Gateway integrations).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
#     2026-07-01 - Added confirm Lambda outputs.
# =============================================================================

output "ingest_function_name" {
  description = "Name of the ingest Lambda function."
  value       = aws_lambda_function.ingest.function_name
}

output "ingest_invoke_arn" {
  description = "Invoke ARN of the ingest Lambda (used by API Gateway integration)."
  value       = aws_lambda_function.ingest.invoke_arn
}

output "processor_function_name" {
  description = "Name of the processor Lambda function."
  value       = aws_lambda_function.processor.function_name
}

output "query_function_name" {
  description = "Name of the query Lambda function."
  value       = aws_lambda_function.query.function_name
}

output "query_invoke_arn" {
  description = "Invoke ARN of the query Lambda (used by API Gateway integration)."
  value       = aws_lambda_function.query.invoke_arn
}

output "confirm_function_name" {
  description = "Name of the confirm Lambda function."
  value       = aws_lambda_function.confirm.function_name
}

output "confirm_invoke_arn" {
  description = "Invoke ARN of the confirm Lambda (used by API Gateway integration)."
  value       = aws_lambda_function.confirm.invoke_arn
}
