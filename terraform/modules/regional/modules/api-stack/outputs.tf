output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = var.enable_custom_domain ? "https://${local.domain_name}" : aws_api_gateway_stage.api_stage.invoke_url
}

output "api_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.tenant_management_api.id
}

output "custom_domain_arn" {
  description = "ARN of the API Gateway custom domain name (empty when the custom domain is disabled). Consumed cross-account to build the PRIVATE domain-name access association from the consumer's VPC endpoint."
  value       = var.enable_custom_domain ? aws_api_gateway_domain_name.domain[0].arn : ""
}

output "custom_domain_id" {
  description = "Identifier of the PRIVATE custom domain name (empty unless this is a private custom domain). Supported only for private custom domain names."
  value       = var.enable_custom_domain && var.private_endpoint ? aws_api_gateway_domain_name.domain[0].domain_name_id : ""
}

output "authorizer_function_arn" {
  description = "ARN of the Lambda authorizer function"
  value       = aws_lambda_function.authorizer_function.arn
}

output "api_function_arn" {
  description = "ARN of the API service Lambda function"
  value       = aws_lambda_function.api_function.arn
}