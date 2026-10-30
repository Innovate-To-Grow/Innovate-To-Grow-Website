resource "aws_iam_role" "guard" {
  name = "${local.prefix}-webhook-guard"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_cloudwatch_log_group" "guard" {
  name              = "/aws/lambda/${local.prefix}-webhook-guard"
  retention_in_days = 14
}

resource "aws_iam_role_policy" "guard" {
  role = aws_iam_role.guard.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ssm:GetParameters"], Resource = ["${local.secret_arn}/id", "${local.secret_arn}/key-base64", "${local.secret_arn}/webhook-secret"] },
      { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = module.runners.webhook.lambda.arn },
      { Effect = "Allow", Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.recovery.arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.guard.arn}:*" },
    ]
  })
}

resource "aws_lambda_function" "guard" {
  function_name    = "${local.prefix}-webhook-guard"
  role             = aws_iam_role.guard.arn
  runtime          = "nodejs24.x"
  handler          = "index.handler"
  filename         = "${path.module}/.artifacts/guard.zip"
  source_code_hash = filebase64sha256("${path.module}/.artifacts/guard.zip")
  timeout          = 30
  memory_size      = 256
  environment {
    variables = {
      WEBHOOK_FUNCTION = module.runners.webhook.lambda.function_name
      RECOVERY_QUEUE   = aws_sqs_queue.recovery.url
    }
  }
  depends_on = [aws_iam_role_policy.guard, aws_cloudwatch_log_group.guard]
}

# Every accepted job gets a delayed authoritative status check, independent of
# the initial launch queue. Failed handoffs and failed boots cannot strand it.
resource "aws_sqs_queue" "recovery" {
  name                       = "${local.prefix}-job-recovery"
  visibility_timeout_seconds = 180
  message_retention_seconds  = 86400
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.recovery_dead_letter.arn
    maxReceiveCount     = 10
  })
}

resource "aws_sqs_queue" "recovery_dead_letter" {
  name                      = "${local.prefix}-job-recovery-dead-letter"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_lambda_event_source_mapping" "recovery" {
  event_source_arn        = aws_sqs_queue.recovery.arn
  function_name           = aws_lambda_function.guard.arn
  batch_size              = 5
  function_response_types = ["ReportBatchItemFailures"]
  depends_on              = [aws_iam_role_policy.guard]
}

resource "aws_apigatewayv2_api" "guard" {
  name          = "${local.prefix}-guard"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "guard" {
  api_id                 = aws_apigatewayv2_api.guard.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.guard.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "guard" {
  api_id    = aws_apigatewayv2_api.guard.id
  route_key = "POST /github"
  target    = "integrations/${aws_apigatewayv2_integration.guard.id}"
}

resource "aws_apigatewayv2_stage" "guard" {
  api_id      = aws_apigatewayv2_api.guard.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }
}

resource "aws_lambda_permission" "guard" {
  statement_id  = "GitHubWebhook"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.guard.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.guard.execution_arn}/*/*"
}

output "github_webhook_url" {
  value = "${aws_apigatewayv2_api.guard.api_endpoint}/github"
}
