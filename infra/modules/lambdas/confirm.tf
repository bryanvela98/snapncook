# =============================================================================
# Description: Terraform resources for the confirm_handler Lambda. Called via
#              POST /recipes/{requestId}/confirm after the user verifies
#              detected ingredients. Persists confirmed ingredients + preferences
#              to DynamoDB, transitions status to GENERATING, and enqueues a
#              phase='generate' SQS message for the processor Lambda.
#              IAM grants: DynamoDB GetItem + UpdateItem, SQS SendMessage.
# Last Modified By: bvela
# Created: 2026-07-01
# Last Modified:
#     2026-07-01 - File created.
# =============================================================================

data "archive_file" "confirm" {
  type        = "zip"
  source_file = "${path.root}/../lambdas/confirm/handler.py"
  output_path = "${path.root}/../lambdas/confirm/handler.zip"
}

# --- IAM ---

resource "aws_iam_role" "confirm" {
  name = "${var.project_name}-confirm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "confirm" {
  name = "${var.project_name}-confirm-policy"
  role = aws_iam_role.confirm.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBReadWrite"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = var.results_table_arn
      },
      {
        Sid      = "SQSSendGenerate"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = var.job_queue_arn
      },
      {
        Sid      = "CloudWatchLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.confirm.arn}:*"
      }
    ]
  })
}

# --- Lambda function ---

resource "aws_lambda_function" "confirm" {
  function_name    = "${var.project_name}-confirm"
  role             = aws_iam_role.confirm.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.confirm.output_path
  source_code_hash = data.archive_file.confirm.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      RESULTS_TABLE = var.results_table_name
      JOB_QUEUE_URL = var.job_queue_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.confirm]
}

# --- CloudWatch log group ---

resource "aws_cloudwatch_log_group" "confirm" {
  name              = "/aws/lambda/${var.project_name}-confirm"
  retention_in_days = 30
}