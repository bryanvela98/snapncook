# =============================================================================
# Description: Input variables for the messaging module.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

variable "project_name" {
  description = "Project slug used to prefix queue names."
  type        = string
}

variable "visibility_timeout_seconds" {
  description = "How long a message is hidden after a receive. Must exceed the processor Lambda's max runtime (cold start + Rekognition + Bedrock)."
  type        = number
  default     = 60
}

variable "max_receive_count" {
  description = "Failed receives before a message is moved to the DLQ."
  type        = number
  default     = 3
}

variable "job_retention_seconds" {
  description = "How long an unconsumed message stays in the job queue (default 4 days)."
  type        = number
  default     = 345600
}

variable "dlq_retention_seconds" {
  description = "How long a failed message is kept in the DLQ for inspection (default 14 days)."
  type        = number
  default     = 1209600
}
