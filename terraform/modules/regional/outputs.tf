output "central_logging_bucket_name" {
  description = "Name of the central logging S3 bucket"
  value       = module.core_infrastructure.central_logging_bucket_name
}

output "central_logging_bucket_arn" {
  description = "ARN of the central logging S3 bucket"
  value       = module.core_infrastructure.central_logging_bucket_arn
}

output "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  value       = module.core_infrastructure.tenant_config_table_name
}

output "tenant_config_table_arn" {
  description = "ARN of the tenant configuration DynamoDB table"
  value       = module.core_infrastructure.tenant_config_table_arn
}

output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = module.api_stack.api_endpoint
}

output "custom_domain_arn" {
  description = "ARN of the API Gateway custom domain name (for the cross-account PRIVATE domain-name access association)"
  value       = module.api_stack.custom_domain_arn
}

output "custom_domain_id" {
  description = "Identifier of the PRIVATE custom domain name"
  value       = module.api_stack.custom_domain_id
}
