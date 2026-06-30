# =============================================================================
# Description: Input variables for the api module.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

variable "project_name" {
  description = "Project slug used to prefix API Gateway resource names."
  type        = string
}

variable "ingest_invoke_arn" {
  description = "Invoke ARN of the ingest Lambda (from the lambdas module)."
  type        = string
}

variable "ingest_function_name" {
  description = "Name of the ingest Lambda function (for the resource-based permission)."
  type        = string
}
