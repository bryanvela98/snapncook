# =============================================================================
# Description: Input variables for the lambdas module. Receives resource names
#              and ARNs from the storage and messaging modules so the Lambda
#              IAM roles can be scoped to specific resources (least-privilege).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

variable "project_name" {
  description = "Project slug used to prefix Lambda function names."
  type        = string
}

variable "image_bucket_name" {
  description = "Name of the S3 image bucket (used as Lambda env var)."
  type        = string
}

variable "image_bucket_arn" {
  description = "ARN of the S3 image bucket (used to scope IAM policies)."
  type        = string
}

variable "results_table_name" {
  description = "Name of the DynamoDB results table (used as Lambda env var)."
  type        = string
}

variable "results_table_arn" {
  description = "ARN of the DynamoDB results table (used to scope IAM policies)."
  type        = string
}

variable "job_queue_url" {
  description = "URL of the SQS job queue (used as Lambda env var)."
  type        = string
}

variable "job_queue_arn" {
  description = "ARN of the SQS job queue (used to scope IAM policies)."
  type        = string
}

variable "lambda_runtime" {
  description = "Python runtime for all Lambda functions."
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Default Lambda timeout in seconds."
  type        = number
  default     = 30
}

variable "ingest_memory_mb" {
  description = "Memory (MB) for the ingest Lambda. Low — no ML work here."
  type        = number
  default     = 256
}

variable "processor_memory_mb" {
  description = "Memory (MB) for the processor Lambda. Higher — handles image + ML calls."
  type        = number
  default     = 512
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for recipe generation (used in IAM policy ARN and Lambda env var)."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "aws_region" {
  description = "AWS region (used to construct the Bedrock inference profile ARN in the IAM policy)."
  type        = string
  default     = "us-east-1"
}

variable "account_id" {
  description = "AWS account ID (used to construct the Bedrock inference profile ARN)."
  type        = string
}
