# =============================================================================
# Description: Terraform resources for the ingest_handler Lambda. Packages the
#              Python source as a zip, deploys the function with least-privilege
#              IAM (S3 PutObject, DynamoDB PutItem, SQS SendMessage), and
#              creates a CloudWatch log group with 30-day retention.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

# Zip the handler source. Terraform rebuilds the zip when source_code_hash
# changes, triggering a Lambda update on the next apply.
data "archive_file" "ingest" {
  type        = "zip"
  source_file = "${path.root}/../lambdas/ingest/handler.py"
  output_path = "${path.root}/../lambdas/ingest/handler.zip"
}

# --- IAM ---

resource "aws_iam_role" "ingest" {
  name = "${var.project_name}-ingest-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Least-privilege: only the exact actions needed by ingest_handler.
resource "aws_iam_role_policy" "ingest" {
  name = "${var.project_name}-ingest-policy"
  role = aws_iam_role.ingest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3PutImage"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${var.image_bucket_arn}/uploads/*"
      },
      {
        Sid      = "DynamoDBPutItem"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"]
        Resource = var.results_table_arn
      },
      {
        Sid      = "SQSSendMessage"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = var.job_queue_arn
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.ingest.arn}:*"
      }
    ]
  })
}

# --- Lambda function ---

resource "aws_lambda_function" "ingest" {
  function_name    = "${var.project_name}-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = var.ingest_memory_mb

  environment {
    variables = {
      IMAGE_BUCKET  = var.image_bucket_name
      RESULTS_TABLE = var.results_table_name
      JOB_QUEUE_URL = var.job_queue_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest]
}

# --- CloudWatch log group ---

# Explicit log group lets Terraform control retention; without it, Lambda
# auto-creates the group with infinite retention.
resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${var.project_name}-ingest"
  retention_in_days = 30
}
