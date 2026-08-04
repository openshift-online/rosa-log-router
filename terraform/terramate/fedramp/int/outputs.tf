// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

output "project_name" {
  description = "Project name used for resource naming"
  value       = var.project_name
}
output "environment" {
  description = "Environment name"
  value       = var.environment
}
output "api_auth_psk_value" {
  description = "The PSK value for API authentication"
  sensitive   = true
  value       = var.api_auth_psk_value
}
output "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role for cross-account access"
  value       = module.global.central_log_distribution_role_arn
}
output "central_s3_writer_role_arn" {
  description = "ARN of the central S3 writer role for Vector agents"
  value       = module.global.central_s3_writer_role_arn
}
output "central_logging_bucket_name_us-gov-west-1" {
  value = module.regional-resource-us-gov-west-1.central_logging_bucket_name
}
output "central_logging_bucket_name_us-gov-east-1" {
  value = module.regional-resource-us-gov-east-1.central_logging_bucket_name
}
output "api_endpoint_us-gov-west-1" {
  value = module.regional-resource-us-gov-west-1.api_endpoint
}
output "api_endpoint_us-gov-east-1" {
  value = module.regional-resource-us-gov-east-1.api_endpoint
}
