# =============================================================================
# Description: Input variables for the frontend module. Receives the API
#              endpoint so config.js can be generated with the correct URL at
#              deploy time, avoiding any hardcoded URLs in the frontend bundle.
# Last Modified By: bvela
# Created: 2026-07-01
# Last Modified:
#     2026-07-01 - File created.
# =============================================================================

variable "project_name" {
  description = "Project slug used to prefix resource names."
  type        = string
}

variable "account_id" {
  description = "AWS account ID — appended to bucket name for global uniqueness."
  type        = string
}

variable "api_endpoint" {
  description = "Base URL of the API Gateway (no trailing slash). Injected into config.js."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g. prod, staging). Used in resource naming."
  type        = string
  default     = "prod"
}