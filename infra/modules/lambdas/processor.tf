# =============================================================================
# Description: Terraform resources for the processor_handler Lambda. Packages
#              the Python source, deploys with least-privilege IAM (S3 GetObject,
#              Rekognition DetectLabels, Bedrock InvokeModel scoped to the Haiku
#              model ARN, DynamoDB UpdateItem, SQS receive/delete), and wires
#              the SQS event source mapping (batch size 1 so each message is
#              an independent invocation with its own retry counter).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created.
# =============================================================================

data "archive_file" "processor" {
  type        = "zip"
  source_file = "${path.root}/../lambdas/processor/handler.py"
  output_path = "${path.root}/../lambdas/processor/handler.zip"
}

# --- IAM ---

resource "aws_iam_role" "processor" {
  name = "${var.project_name}-processor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "processor" {
  name = "${var.project_name}-processor-policy"
  role = aws_iam_role.processor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3GetImage"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.image_bucket_arn}/uploads/*"
      },
      {
        Sid    = "RekognitionDetect"
        Effect = "Allow"
        Action = ["rekognition:DetectLabels"]
        # Rekognition is a regional service with no resource-level ARN for
        # DetectLabels — the action operates on the image passed inline.
        Resource = "*"
      },
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        # Inference profiles use a different ARN pattern than foundation models.
        # The us.* profile ID resolves to cross-region inference across US regions.
        Resource = [
          "arn:aws:bedrock:${var.aws_region}:${var.account_id}:inference-profile/${var.bedrock_model_id}",
          "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        ]
      },
      {
        Sid      = "DynamoDBUpdate"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = var.results_table_arn
      },
      {
        Sid    = "SQSConsume"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = var.job_queue_arn
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.processor.arn}:*"
      }
    ]
  })
}

# --- Lambda function ---

resource "aws_lambda_function" "processor" {
  function_name    = "${var.project_name}-processor"
  role             = aws_iam_role.processor.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.processor.output_path
  source_code_hash = data.archive_file.processor.output_base64sha256
  # Rekognition + Bedrock calls can take 5–15 s; 120 s gives comfortable margin.
  timeout     = 120
  memory_size = var.processor_memory_mb

  environment {
    variables = {
      IMAGE_BUCKET     = var.image_bucket_name
      RESULTS_TABLE    = var.results_table_name
      BEDROCK_MODEL_ID = var.bedrock_model_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.processor]
}

# --- SQS event source mapping ---

# Batch size 1: each message is an independent invocation so a Rekognition
# or Bedrock failure retries only the affected job, not the whole batch.
resource "aws_lambda_event_source_mapping" "sqs_processor" {
  event_source_arn = var.job_queue_arn
  function_name    = aws_lambda_function.processor.arn
  batch_size       = 1
  enabled          = true
}

# --- CloudWatch log group ---

resource "aws_cloudwatch_log_group" "processor" {
  name              = "/aws/lambda/${var.project_name}-processor"
  retention_in_days = 30
}
