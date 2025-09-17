// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

output "project_name" {
  description = "Project name used for resource naming"
  value       = var.project_name
}
output "environment" {
  description = "Environment name"
  value       = var.environment
}
output "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role for cross-account access"
  value       = module.global.central_log_distribution_role_arn
}
output "central_s3_writer_role_arn" {
  description = "ARN of the central S3 writer role for Vector agents"
  value       = module.global.central_s3_writer_role_arn
}
output "central_logging_bucket_name_us-east-1" {
  value = module.regional-resource-us-east-1.central_logging_bucket_name
}
output "central_logging_bucket_name_us-east-2" {
  value = module.regional-resource-us-east-2.central_logging_bucket_name
}
output "tenant_config_table_name_us-east-1" {
  value = module.regional-resource-us-east-1.tenant_config_table_name
}
output "tenant_config_table_name_us-east-2" {
  value = module.regional-resource-us-east-2.tenant_config_table_name
}
output "tenant_config_table_arn_us-east-1" {
  value = module.regional-resource-us-east-1.tenant_config_table_arn
}
output "tenant_config_table_arn_us-east-2" {
  value = module.regional-resource-us-east-2.tenant_config_table_arn
}
