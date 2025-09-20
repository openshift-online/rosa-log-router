# API Gateway and Lambda functions for tenant management API

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Local values
locals {
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# Lambda Authorizer Execution Role
resource "aws_iam_role" "authorizer_execution_role" {
  name = "${var.project_name}-${var.environment}-api-authorizer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "authorizer_basic_execution" {
  role       = aws_iam_role.authorizer_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "authorizer_ssm_policy" {
  name = "SSMParameterAccess"
  role = aws_iam_role.authorizer_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "ssm:GetParameter"
        Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.api_auth_ssm_parameter}"
      }
    ]
  })
}

# Lambda Authorizer Function
resource "aws_lambda_function" "authorizer_function" {
  function_name = "${var.project_name}-${var.environment}-api-authorizer"
  package_type  = "Image"
  image_uri     = var.authorizer_image_uri
  role          = aws_iam_role.authorizer_execution_role.arn
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      PSK_PARAMETER_NAME = var.api_auth_ssm_parameter
      LOG_LEVEL         = "INFO"
    }
  }

  tags = merge(local.common_tags, {
    Component = "api-authorizer"
  })
}

# API Lambda Execution Role
resource "aws_iam_role" "api_execution_role" {
  name = "${var.project_name}-${var.environment}-api-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "api_basic_execution" {
  role       = aws_iam_role.api_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api_dynamodb_policy" {
  name = "DynamoDBAccess"
  role = aws_iam_role.api_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = var.tenant_config_table_arn
      }
    ]
  })
}

# Main API Lambda Function
resource "aws_lambda_function" "api_function" {
  function_name = "${var.project_name}-${var.environment}-api-service"
  package_type  = "Image"
  image_uri     = var.api_image_uri
  role          = aws_iam_role.api_execution_role.arn
  timeout       = 30
  memory_size   = 512

  environment {
    variables = {
      TENANT_CONFIG_TABLE = var.tenant_config_table_name
      LOG_LEVEL          = "INFO"
    }
  }

  tags = merge(local.common_tags, {
    Component = "api-service"
  })
}

# API Gateway REST API
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
        Effect = "Allow"
        Principal = "*"
        Action = "execute-api:Invoke"
        Resource = "*"
      }
    ]
  })

  tags = local.common_tags
}

# API Gateway role for invoking authorizer
resource "aws_iam_role" "api_gateway_authorizer_role" {
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "api_gateway_authorizer_policy" {
  name = "InvokeAuthorizerFunction"
  role = aws_iam_role.api_gateway_authorizer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "lambda:InvokeFunction"
        Resource = aws_lambda_function.authorizer_function.arn
      }
    ]
  })
}

# API Gateway Authorizer
resource "aws_api_gateway_authorizer" "api_authorizer" {
  name                   = "${var.project_name}-${var.environment}-hmac-authorizer"
  rest_api_id           = aws_api_gateway_rest_api.tenant_management_api.id
  type                  = "REQUEST"
  authorizer_uri        = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${aws_lambda_function.authorizer_function.arn}/invocations"
  authorizer_credentials = aws_iam_role.api_gateway_authorizer_role.arn
  authorizer_result_ttl_in_seconds = 300
  identity_source       = "method.request.header.Authorization,method.request.header.X-API-Timestamp"
}

# Permission for API Gateway to invoke authorizer
resource "aws_lambda_permission" "authorizer_invoke_permission" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${aws_api_gateway_rest_api.tenant_management_api.id}/authorizers/${aws_api_gateway_authorizer.api_authorizer.id}"
}

# Permission for API Gateway to invoke main API function
resource "aws_lambda_permission" "api_invoke_permission" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${aws_api_gateway_rest_api.tenant_management_api.id}/*/*"
}

# API Gateway Resources and Methods (simplified structure)
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
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.api_version_resource.id
  http_method = aws_api_gateway_method.health_method.http_method

  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${aws_lambda_function.api_function.arn}/invocations"
}

# Proxy method (with authorization)
resource "aws_api_gateway_method" "proxy_method" {
  rest_api_id   = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id   = aws_api_gateway_resource.proxy_resource.id
  http_method   = "ANY"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.api_authorizer.id
}

resource "aws_api_gateway_integration" "proxy_integration" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id
  resource_id = aws_api_gateway_resource.proxy_resource.id
  http_method = aws_api_gateway_method.proxy_method.http_method

  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${aws_lambda_function.api_function.arn}/invocations"
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "api_deployment" {
  rest_api_id = aws_api_gateway_rest_api.tenant_management_api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.api_resource.id,
      aws_api_gateway_resource.api_version_resource.id,
      aws_api_gateway_resource.proxy_resource.id,
      aws_api_gateway_method.health_method.id,
      aws_api_gateway_method.proxy_method.id,
      aws_api_gateway_integration.health_integration.id,
      aws_api_gateway_integration.proxy_integration.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

# API Gateway Stage
resource "aws_api_gateway_stage" "api_stage" {
  deployment_id = aws_api_gateway_deployment.api_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.tenant_management_api.id
  stage_name    = var.environment

  tags = local.common_tags
}