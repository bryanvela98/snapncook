# =============================================================================
# Description: Outputs from the monitoring module. Exposes the SNS topic ARN
#              so it can be wired to additional subscribers or alarm actions
#              without modifying this module.
# Last Modified By: bvela
# Created: 2026-07-01
# Last Modified:
#     2026-07-01 - File created.
# =============================================================================

output "alarms_topic_arn" {
  description = "ARN of the SNS topic that receives CloudWatch alarm state changes."
  value       = aws_sns_topic.alarms.arn
}
