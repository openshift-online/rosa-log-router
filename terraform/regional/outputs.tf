# Core Infrastructure Outputs
output "central_logging_bucket_name" {
  description = "Name of the central logging S3 bucket"
  value       = module.core_infrastructure.central_logging_bucket_name
}

output "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  value       = module.core_infrastructure.tenant_config_table_name
}

# SQS Outputs (Optional)
output "log_delivery_queue_arn" {
  description = "ARN of the log delivery SQS queue"
  value       = var.include_sqs_stack ? module.sqs_stack[0].log_delivery_queue_arn : null
}

output "log_delivery_queue_url" {
  description = "URL of the log delivery SQS queue"
  value       = var.include_sqs_stack ? module.sqs_stack[0].log_delivery_queue_url : null
}

# Lambda Outputs (Optional)
output "log_distributor_function_name" {
  description = "Name of the log distributor Lambda function"
  value       = var.include_lambda_stack ? module.lambda_stack[0].log_distributor_function_name : null
}

output "log_distributor_function_arn" {
  description = "ARN of the log distributor Lambda function"
  value       = var.include_lambda_stack ? module.lambda_stack[0].log_distributor_function_arn : null
}

# IAM Role Outputs
output "regional_log_processor_role_arn" {
  description = "ARN of the regional log processor role"
  value       = module.core_infrastructure.regional_log_processor_role_arn
}

output "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role (from global stack)"
  value       = var.central_log_distribution_role_arn
}

# SNS Outputs
output "log_delivery_topic_arn" {
  description = "ARN of the log delivery SNS topic"
  value       = module.core_infrastructure.log_delivery_topic_arn
}

# API Outputs (Optional)
output "api_endpoint" {
  description = "API Gateway endpoint URL for tenant management"
  value       = var.include_api_stack ? module.api_stack[0].api_endpoint : null
}

output "api_id" {
  description = "API Gateway REST API ID"
  value       = var.include_api_stack ? module.api_stack[0].api_id : null
}

# Stack Information
output "stack_version" {
  description = "Version of this Terraform stack (POC)"
  value       = "1.0.0-poc"
}