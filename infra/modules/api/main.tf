# =============================================================================
# Description: API Gateway HTTP API (v2) for Snap & Cook. Exposes POST /analyze
#              wired to the ingest Lambda. CORS is configured here so the S3
#              frontend can call the API from the browser. Additional routes
#              (GET /recipes/{id}) are added in later tasks. Lambda permissions
#              are granted via aws_lambda_permission (resource-based policy).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created: POST /analyze route + ingest Lambda integration.
#     2026-07-01 - Added POST /recipes/{requestId}/confirm → confirm Lambda.
# =============================================================================

resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
  description   = "Snap & Cook API — image upload and recipe retrieval"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["POST", "GET", "OPTIONS"]
    allow_headers = ["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key"]
    max_age       = 300
  }
}

# Auto-deploy stage — changes are reflected immediately on apply.
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      sourceIp       = "$context.identity.sourceIp"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      durationMs     = "$context.integrationLatency"
    })
  }
}

# --- POST /analyze → ingest Lambda ---

resource "aws_apigatewayv2_integration" "ingest" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.ingest_invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "post_analyze" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /analyze"
  target    = "integrations/${aws_apigatewayv2_integration.ingest.id}"
}

# Allow API Gateway to invoke the ingest Lambda.
resource "aws_lambda_permission" "apigw_ingest" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.ingest_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# --- GET /recipes/{requestId} → query Lambda ---

resource "aws_apigatewayv2_integration" "query" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.query_invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "get_recipes" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /recipes/{requestId}"
  target    = "integrations/${aws_apigatewayv2_integration.query.id}"
}

resource "aws_lambda_permission" "apigw_query" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.query_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# --- POST /recipes/{requestId}/confirm → confirm Lambda ---

resource "aws_apigatewayv2_integration" "confirm" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.confirm_invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "post_confirm" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /recipes/{requestId}/confirm"
  target    = "integrations/${aws_apigatewayv2_integration.confirm.id}"
}

resource "aws_lambda_permission" "apigw_confirm" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.confirm_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# --- CloudWatch log group for API access logs ---

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${var.project_name}-api"
  retention_in_days = 30
}
