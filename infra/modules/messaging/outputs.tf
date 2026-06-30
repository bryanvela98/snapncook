# =============================================================================
# Description: Outputs from the messaging module, consumed by the lambda module
#              (queue URL for the ingest env var; queue/DLQ ARNs for IAM
#              policies and the processor event source mapping).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

output "queue_url" {
  description = "URL of the main job queue (for ingest_handler SendMessage)."
  value       = aws_sqs_queue.job.id
}

output "queue_arn" {
  description = "ARN of the main job queue (for IAM + event source mapping)."
  value       = aws_sqs_queue.job.arn
}

output "dlq_url" {
  description = "URL of the dead-letter queue."
  value       = aws_sqs_queue.dlq.id
}

output "dlq_arn" {
  description = "ARN of the dead-letter queue (for the DLQ-depth alarm)."
  value       = aws_sqs_queue.dlq.arn
}
