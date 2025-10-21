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
  image_uri     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com/${var.authorizer_image}"
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
  image_uri     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com/${var.api_image}"
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
  authorizer_uri                   = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${aws_lambda_function.authorizer_function.arn}/invocations"
  authorizer_credentials           = var.api_gateway_authorizer_role_arn
  authorizer_result_ttl_in_seconds = 300
  identity_source                  = "method.request.header.Authorization,method.request.header.X-API-Timestamp"
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "authorizer_invoke_permission" {
  function_name = aws_lambda_function.authorizer_function.arn
  action        = "lambda:InvokeFunction"
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${aws_api_gateway_rest_api.tenant_management_api.id}/authorizers/${aws_api_gateway_authorizer.api_authorizer.id}"
}

resource "aws_lambda_permission" "api_invoke_permission" {
  function_name = aws_lambda_function.api_function.arn
  action        = "lambda:InvokeFunction"
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${aws_api_gateway_rest_api.tenant_management_api.id}/*/*"
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

resource "aws_api_gateway_resource" "proxy_resource" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  parent_id   = aws_api_gateway_resource.api_version_resource.id
  path_part   = "{proxy+}"
}

# Health check method (no authorization)
resource "aws_api_gateway_method" "health_method" {
  rest_api_id   = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id   = aws_api_gateway_resource.api_version_resource.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health_integration" {
  rest_api_id             = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id             = aws_api_gateway_resource.api_version_resource.id
  http_method             = aws_api_gateway_method.health_method.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${aws_lambda_function.api_function.arn}/invocations"
}

resource "aws_api_gateway_method_response" "health_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.api_version_resource.id
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
  uri                     = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${aws_lambda_function.api_function.arn}/invocations"
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
  resource_id   = aws_api_gateway_resource.api_version_resource.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health_options_integration" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.api_version_resource.id
  http_method = aws_api_gateway_method.health_options_method.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_integration_response" "health_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.api_version_resource.id
  http_method = aws_api_gateway_method.health_options_method.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-API-Timestamp'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,PATCH,DELETE,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

resource "aws_api_gateway_method_response" "health_options_response" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.api_version_resource.id
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
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_gateway_log_group" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}-tenant-api"
  retention_in_days = 14
}
