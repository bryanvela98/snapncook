# =============================================================================
# Description: Input variables for the storage module.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

variable "project_name" {
  description = "Project slug used to prefix resource names."
  type        = string
}

variable "account_id" {
  description = "AWS account ID, appended to the image bucket name for global uniqueness."
  type        = string
}

variable "image_retention_days" {
  description = "Days before uploaded images are expired from S3."
  type        = number
  default     = 7
}
