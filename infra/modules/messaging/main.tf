# =============================================================================
# Description: Messaging module for Snap & Cook. Provisions the SQS job queue
#              that decouples the ingest Lambda from the (slow) processor
#              Lambda, plus a dead-letter queue for messages that fail
#              processing repeatedly. The redrive policy moves a message to the
#              DLQ after maxReceiveCount failed receives, preventing poison
#              messages from blocking the queue (Reliability pillar).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created: SQS job queue + DLQ with redrive policy.
# =============================================================================

# Dead-letter queue — terminal home for messages that fail processing
# maxReceiveCount times. Declared first so the main queue can reference its ARN.
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-job-dlq"
  message_retention_seconds = var.dlq_retention_seconds
  sqs_managed_sse_enabled   = true
}

# Main job queue. ingest_handler publishes { requestId, s3_key }; the SQS event
# source mapping on processor_handler consumes from here.
resource "aws_sqs_queue" "job" {
  name                       = "${var.project_name}-job-queue"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.job_retention_seconds
  sqs_managed_sse_enabled    = true

  # After maxReceiveCount failed receives, SQS moves the message to the DLQ.
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Allow only the main job queue to redrive into the DLQ.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.job.arn]
  })
}
