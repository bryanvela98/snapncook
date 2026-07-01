# =============================================================================
# Description: Terraform resources for the query_handler Lambda. Packages the
#              Python source, deploys with least-privilege IAM (DynamoDB
#              GetItem only on the results table), and exports the invoke ARN
#              consumed by the API Gateway module for the GET route.
# Last Modified By: bvela
# Created: 2026-07-01
# Last Modified:
#     2026-07-01 - File created.
# =============================================================================

data "archive_file" "query" {
  type        = "zip"
  source_file = "${path.root}/../lambdas/query/handler.py"
  output_path = "${path.root}/../lambdas/query/handler.zip"
}

# --- IAM ---

resource "aws_iam_role" "query" {
  name = "${var.project_name}-query-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "query" {
  name = "${var.project_name}-query-policy"
  role = aws_iam_role.query.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DynamoDBGetItem"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem"]
        Resource = var.results_table_arn
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.query.arn}:*"
      }
    ]
  })
}

# --- Lambda function ---

resource "aws_lambda_function" "query" {
  function_name    = "${var.project_name}-query"
  role             = aws_iam_role.query.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.query.output_path
  source_code_hash = data.archive_file.query.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = 256

  environment {
    variables = {
      RESULTS_TABLE = var.results_table_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.query]
}

# --- CloudWatch log group ---

resource "aws_cloudwatch_log_group" "query" {
  name              = "/aws/lambda/${var.project_name}-query"
  retention_in_days = 30
}
