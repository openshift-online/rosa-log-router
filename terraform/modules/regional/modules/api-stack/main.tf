# Regional API Stack Terraform Module
# Converted from CloudFormation template

# Data sources for current AWS context
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Local values
locals {
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    StackType   = "api-stack"
  })
}

# Lambda Authorizer Function
resource "aws_lambda_function" "authorizer_function" {
  function_name = "${var.project_name}-${var.environment}-api-authorizer"
  image_uri     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.id}.amazonaws.com/${var.authorizer_image}"
  package_type  = "Image"
  role          = var.authorizer_execution_role_arn
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      PSK_SECRET_NAME = var.api_auth_secret_name
      LOG_LEVEL       = "INFO"
    }
  }

  tags = local.common_tags
}


# Main API Lambda Function
resource "aws_lambda_function" "api_function" {
  function_name = "${var.project_name}-${var.environment}-api-service"
  image_uri     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.id}.amazonaws.com/${var.api_image}"
  package_type  = "Image"
  role          = var.api_execution_role_arn
  timeout       = 30
  memory_size   = 512

  environment {
    variables = {
      TENANT_CONFIG_TABLE = var.tenant_config_table_name
      LOG_LEVEL           = "INFO"
    }
  }

  tags = local.common_tags
}

resource "aws_api_gateway_rest_api" "tenant_management_api" {
  name        = "${var.project_name}-${var.environment}-tenant-api"
  description = "REST API for tenant configuration management"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = "*"
        Action    = "execute-api:Invoke"
        Resource  = "*"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_api_gateway_authorizer" "api_authorizer" {
  name                             = "${var.project_name}-${var.environment}-hmac-authorizer"
  rest_api_id                      = aws_api_gateway_rest_api.tenant_management_api.id
  type                             = "REQUEST"
  authorizer_uri                   = "arn:aws:apigateway:${data.aws_region.current.id}:lambda:path/2015-03-31/functions/${aws_lambda_function.authorizer_function.arn}/invocations"
  authorizer_credentials           = var.api_gateway_authorizer_role_arn
  authorizer_result_ttl_in_seconds = 300
  identity_source                  = "method.request.header.Authorization,method.request.header.X-API-Timestamp"
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "authorizer_invoke_permission" {
  function_name = aws_lambda_function.authorizer_function.arn
  action        = "lambda:InvokeFunction"
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:${aws_api_gateway_rest_api.tenant_management_api.id}/authorizers/${aws_api_gateway_authorizer.api_authorizer.id}"
}

resource "aws_lambda_permission" "api_invoke_permission" {
  function_name = aws_lambda_function.api_function.arn
  action        = "lambda:InvokeFunction"
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:${aws_api_gateway_rest_api.tenant_management_api.id}/*/*"
}

# API Gateway Resources
resource "aws_api_gateway_resource" "api_resource" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  parent_id   = aws_api_gateway_rest_api.tenant_management_api.root_resource_id
  path_part   = "api"
}

resource "aws_api_gateway_resource" "api_version_resource" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  parent_id   = aws_api_gateway_resource.api_resource.id
  path_part   = "v1"
}

resource "aws_api_gateway_resource" "health_resource" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  parent_id   = aws_api_gateway_resource.api_version_resource.id
  path_part   = "health"
}

resource "aws_api_gateway_resource" "proxy_resource" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  parent_id   = aws_api_gateway_resource.api_version_resource.id
  path_part   = "{proxy+}"
}

# Health check method (no authorization)
resource "aws_api_gateway_method" "health_method" {
  rest_api_id   = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id   = aws_api_gateway_resource.health_resource.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health_integration" {
  rest_api_id             = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id             = aws_api_gateway_resource.health_resource.id
  http_method             = aws_api_gateway_method.health_method.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = "arn:aws:apigateway:${data.aws_region.current.id}:lambda:path/2015-03-31/functions/${aws_lambda_function.api_function.arn}/invocations"
}

resource "aws_api_gateway_method_response" "health_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.health_resource.id
  http_method = aws_api_gateway_method.health_method.http_method
  status_code = "200"

  response_models = {
    "application/json" = "Empty"
  }

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin" = true
  }
}

# Proxy method for all other endpoints (with authorization)
resource "aws_api_gateway_method" "proxy_method" {
  rest_api_id   = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id   = aws_api_gateway_resource.proxy_resource.id
  http_method   = "ANY"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.api_authorizer.id
}

resource "aws_api_gateway_integration" "proxy_integration" {
  rest_api_id             = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id             = aws_api_gateway_resource.proxy_resource.id
  http_method             = aws_api_gateway_method.proxy_method.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = "arn:aws:apigateway:${data.aws_region.current.id}:lambda:path/2015-03-31/functions/${aws_lambda_function.api_function.arn}/invocations"
}

resource "aws_api_gateway_method_response" "proxy_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.proxy_resource.id
  http_method = aws_api_gateway_method.proxy_method.http_method
  status_code = "200"

  response_models = {
    "application/json" = "Empty"
  }

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin" = true
  }
}

# CORS Options method for health endpoint
resource "aws_api_gateway_method" "health_options_method" {
  rest_api_id   = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id   = aws_api_gateway_resource.health_resource.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health_options_integration" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.health_resource.id
  http_method = aws_api_gateway_method.health_options_method.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_integration_response" "health_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.health_resource.id
  http_method = aws_api_gateway_method.health_options_method.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-API-Timestamp'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,PATCH,DELETE,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.health_options_integration]
}

resource "aws_api_gateway_method_response" "health_options_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.health_resource.id
  http_method = aws_api_gateway_method.health_options_method.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

# CORS Options method for proxy endpoints
resource "aws_api_gateway_method" "proxy_options_method" {
  rest_api_id   = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id   = aws_api_gateway_resource.proxy_resource.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_options_integration" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.proxy_resource.id
  http_method = aws_api_gateway_method.proxy_options_method.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_integration_response" "proxy_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.proxy_resource.id
  http_method = aws_api_gateway_method.proxy_options_method.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-API-Timestamp'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,PATCH,DELETE,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.proxy_options_integration]
}

resource "aws_api_gateway_method_response" "proxy_options_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.proxy_resource.id
  http_method = aws_api_gateway_method.proxy_options_method.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "api_deployment" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  description = "${var.environment} stage for tenant management API"

  # Force redeployment when any API Gateway resources change
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_rest_api.tenant_management_api.id,
      aws_api_gateway_authorizer.api_authorizer.id,
      aws_api_gateway_resource.api_resource.id,
      aws_api_gateway_resource.api_version_resource.id,
      aws_api_gateway_resource.health_resource.id,
      aws_api_gateway_resource.proxy_resource.id,
      aws_api_gateway_method.health_method.id,
      aws_api_gateway_method.proxy_method.id,
      aws_api_gateway_method.health_options_method.id,
      aws_api_gateway_method.proxy_options_method.id,
      aws_api_gateway_integration.health_integration.id,
      aws_api_gateway_integration.proxy_integration.id,
      aws_api_gateway_integration.health_options_integration.id,
      aws_api_gateway_integration.proxy_options_integration.id,
      aws_api_gateway_method_response.health_response.id,
      aws_api_gateway_method_response.proxy_response.id,
      aws_api_gateway_method_response.health_options_response.id,
      aws_api_gateway_method_response.proxy_options_response.id,
      aws_api_gateway_integration_response.health_options_integration_response.id,
      aws_api_gateway_integration_response.proxy_options_integration_response.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_method.health_method,
    aws_api_gateway_method.proxy_method,
    aws_api_gateway_method.health_options_method,
    aws_api_gateway_method.proxy_options_method,
    aws_api_gateway_integration.health_integration,
    aws_api_gateway_integration.proxy_integration,
    aws_api_gateway_integration.health_options_integration,
    aws_api_gateway_integration.proxy_options_integration
  ]
}

# API Gateway Stage
resource "aws_api_gateway_stage" "api_stage" {
  stage_name    = var.environment
  rest_api_id   = aws_api_gateway_rest_api.tenant_management_api.id
  deployment_id = aws_api_gateway_deployment.api_deployment.id
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_log_group.arn
    format = jsonencode({
      requestTime     = "$context.requestTime"
      requestId       = "$context.requestId"
      ip              = "$context.identity.sourceIp"
      caller          = "$context.identity.caller"
      user            = "$context.identity.user"
      userAgent       = "$context.identity.userAgent"
      httpMethod      = "$context.httpMethod"
      path            = "$context.path"
      resourcePath    = "$context.resourcePath"
      status          = "$context.status"
      protocol        = "$context.protocol"
      responseLatency = "$context.responseLatency"
      responseLength  = "$context.responseLength"
    })
  }
}


resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = var.api_gateway_cloudwatch_role_arn
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  stage_name  = aws_api_gateway_stage.api_stage.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled    = true
    logging_level      = "INFO"
    data_trace_enabled = true
  }
}

resource "aws_cloudwatch_log_group" "api_gateway_ecexution_log" {
  name              = "API-Gateway-Execution-Logs_${aws_api_gateway_rest_api.tenant_management_api.id}/${var.environment}"
  retention_in_days = 14
  tags              = local.common_tags
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_gateway_log_group" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}-tenant-api"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "api_gateway_log_welcome" {
  name              = "/aws/apigateway/welcome"
  retention_in_days = 14
}

# CloudWatch Log Group for Lambda functions
resource "aws_cloudwatch_log_group" "api_service_log_group" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-api-service"
  retention_in_days = 14

  tags = local.common_tags
}

# CloudWatch Log Group for Lambda functions
resource "aws_cloudwatch_log_group" "api_authorizer_log_group" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-api-authorizer"
  retention_in_days = 14

  tags = local.common_tags
}
