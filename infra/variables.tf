# =============================================================================
# Description: Input variables shared across the main Snap & Cook stack.
#              Per-module variables live in their own modules; these are the
#              project-wide knobs.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project slug used to prefix resource names and tags."
  type        = string
  default     = "snap-and-cook"
}

variable "bedrock_model_id" {
  description = "Bedrock model ID used for recipe generation."
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}
