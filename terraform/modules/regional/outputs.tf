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

# output "api_endpoint" {
#   description = "API Gateway endpoint URL"
#   value       = module.api_stack.api_endpoint
# }
