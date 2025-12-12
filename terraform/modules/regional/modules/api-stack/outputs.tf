output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = var.enable_custom_domain ? "https://${local.domain_name}" : aws_api_gateway_stage.api_stage.invoke_url
}

output "api_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.tenant_management_api.id
}

output "authorizer_function_arn" {
  description = "ARN of the Lambda authorizer function"
  value       = aws_lambda_function.authorizer_function.arn
}

output "api_function_arn" {
  description = "ARN of the API service Lambda function"
  value       = aws_lambda_function.api_function.arn
}