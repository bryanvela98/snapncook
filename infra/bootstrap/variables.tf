# =============================================================================
# Description: Input variables for the bootstrap stack. account_id is required
#              to make the state bucket name globally unique without hard-coding
#              it in source.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

variable "aws_region" {
  description = "AWS region for the state bucket and lock table."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project slug used to prefix backend resource names."
  type        = string
  default     = "snap-and-cook"
}

variable "account_id" {
  description = "AWS account ID, appended to the state bucket name for global uniqueness."
  type        = string
}
