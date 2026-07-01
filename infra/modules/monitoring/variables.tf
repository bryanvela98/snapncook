# =============================================================================
# Description: Input variables for the monitoring module. Receives function
#              names, queue ARNs, and notification settings so alarms and
#              subscriptions can reference the right resources without hard-
#              coding names.
# Last Modified By: bvela
# Created: 2026-07-01
# Last Modified:
#     2026-07-01 - File created.
# =============================================================================

variable "project_name" {
  description = "Project slug used to prefix alarm and SNS resource names."
  type        = string
}

variable "ingest_function_name" {
  description = "Name of the ingest Lambda function (used to scope alarms)."
  type        = string
}

variable "processor_function_name" {
  description = "Name of the processor Lambda function (used to scope alarms)."
  type        = string
}

variable "query_function_name" {
  description = "Name of the query Lambda function (used to scope alarms)."
  type        = string
}

variable "confirm_function_name" {
  description = "Name of the confirm Lambda function (used to scope alarms)."
  type        = string
}

variable "dlq_name" {
  description = "Name of the SQS dead-letter queue (used to scope the DLQ depth alarm)."
  type        = string
}

variable "alarm_email" {
  description = "Email address for CloudWatch alarm notifications via SNS."
  type        = string
  default     = ""
}

variable "lambda_error_threshold" {
  description = "Number of Lambda errors in the evaluation period that triggers the alarm."
  type        = number
  default     = 1
}

variable "dlq_depth_threshold" {
  description = "Number of messages in the DLQ that triggers the alarm."
  type        = number
  default     = 1
}

variable "processor_duration_threshold_ms" {
  description = "Processor Lambda maximum duration (ms) that triggers the alarm."
  type        = number
  # 110 000 ms — ~92% of the 120 s timeout; leaves room to detect runaway calls.
  default = 110000
}
