# =============================================================================
# Description: Monitoring module for Snap & Cook. Provisions CloudWatch alarms
#              for Lambda errors (all four functions), DLQ message depth, and
#              processor Lambda duration. An SNS topic aggregates alarm state
#              changes; subscribe your email via alarm_email to receive
#              notifications. All alarms use a 1-minute evaluation period so
#              issues surface quickly without generating noise.
# Last Modified By: bvela
# Created: 2026-07-01
# Last Modified:
#     2026-07-01 - File created: Lambda error alarms, DLQ depth alarm,
#                  processor duration alarm, SNS topic.
# =============================================================================

# ---------------------------------------------------------------------------
# SNS topic — alarm notifications
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alarms" {
  name = "${var.project_name}-alarms"
}

# Email subscription is created only when alarm_email is set; otherwise the
# topic exists but has no subscribers (still useful for future wiring).
resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# ---------------------------------------------------------------------------
# Lambda error alarms
# ---------------------------------------------------------------------------

locals {
  lambda_functions = {
    ingest    = var.ingest_function_name
    processor = var.processor_function_name
    query     = var.query_function_name
    confirm   = var.confirm_function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.lambda_functions

  alarm_name          = "${var.project_name}-${each.key}-errors"
  alarm_description   = "Fires when the ${each.key} Lambda logs ≥${var.lambda_error_threshold} error(s) in 1 minute."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = var.lambda_error_threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# ---------------------------------------------------------------------------
# DLQ depth alarm — any message landing here means a job exhausted all retries
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${var.project_name}-dlq-depth"
  alarm_description   = "Fires when ≥${var.dlq_depth_threshold} message(s) appear in the dead-letter queue."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = var.dlq_name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = var.dlq_depth_threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# ---------------------------------------------------------------------------
# Processor Lambda duration alarm — catches runaway Rekognition/Bedrock calls
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "processor_duration" {
  alarm_name          = "${var.project_name}-processor-duration"
  alarm_description   = "Fires when the processor Lambda maximum duration exceeds ${var.processor_duration_threshold_ms} ms (≈92% of timeout)."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = { FunctionName = var.processor_function_name }
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.processor_duration_threshold_ms
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# ---------------------------------------------------------------------------
# Processor Lambda throttles alarm — Lambda concurrency saturation indicator
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "processor_throttles" {
  alarm_name          = "${var.project_name}-processor-throttles"
  alarm_description   = "Fires when the processor Lambda is throttled, indicating concurrency limits are being hit."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = var.processor_function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}
