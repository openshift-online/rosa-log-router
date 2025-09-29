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
output "central_logging_bucket_name_af-south-1" {
  value = module.regional-resource-af-south-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-east-1" {
  value = module.regional-resource-ap-east-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-northeast-1" {
  value = module.regional-resource-ap-northeast-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-northeast-2" {
  value = module.regional-resource-ap-northeast-2.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-northeast-3" {
  value = module.regional-resource-ap-northeast-3.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-south-1" {
  value = module.regional-resource-ap-south-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-south-2" {
  value = module.regional-resource-ap-south-2.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-southeast-1" {
  value = module.regional-resource-ap-southeast-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-southeast-2" {
  value = module.regional-resource-ap-southeast-2.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-southeast-3" {
  value = module.regional-resource-ap-southeast-3.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-southeast-4" {
  value = module.regional-resource-ap-southeast-4.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-southeast-5" {
  value = module.regional-resource-ap-southeast-5.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-southeast-7" {
  value = module.regional-resource-ap-southeast-7.central_logging_bucket_name
}
output "central_logging_bucket_name_ca-central-1" {
  value = module.regional-resource-ca-central-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ca-west-1" {
  value = module.regional-resource-ca-west-1.central_logging_bucket_name
}
output "central_logging_bucket_name_eu-central-1" {
  value = module.regional-resource-eu-central-1.central_logging_bucket_name
}
output "central_logging_bucket_name_eu-central-2" {
  value = module.regional-resource-eu-central-2.central_logging_bucket_name
}
output "central_logging_bucket_name_eu-north-1" {
  value = module.regional-resource-eu-north-1.central_logging_bucket_name
}
output "central_logging_bucket_name_eu-south-1" {
  value = module.regional-resource-eu-south-1.central_logging_bucket_name
}
output "central_logging_bucket_name_eu-south-2" {
  value = module.regional-resource-eu-south-2.central_logging_bucket_name
}
output "central_logging_bucket_name_eu-west-1" {
  value = module.regional-resource-eu-west-1.central_logging_bucket_name
}
output "central_logging_bucket_name_eu-west-2" {
  value = module.regional-resource-eu-west-2.central_logging_bucket_name
}
output "central_logging_bucket_name_eu-west-3" {
  value = module.regional-resource-eu-west-3.central_logging_bucket_name
}
output "central_logging_bucket_name_il-central-1" {
  value = module.regional-resource-il-central-1.central_logging_bucket_name
}
output "central_logging_bucket_name_me-central-1" {
  value = module.regional-resource-me-central-1.central_logging_bucket_name
}
output "central_logging_bucket_name_me-south-1" {
  value = module.regional-resource-me-south-1.central_logging_bucket_name
}
output "central_logging_bucket_name_mx-central-1" {
  value = module.regional-resource-mx-central-1.central_logging_bucket_name
}
output "central_logging_bucket_name_sa-east-1" {
  value = module.regional-resource-sa-east-1.central_logging_bucket_name
}
output "central_logging_bucket_name_us-east-1" {
  value = module.regional-resource-us-east-1.central_logging_bucket_name
}
output "central_logging_bucket_name_us-east-2" {
  value = module.regional-resource-us-east-2.central_logging_bucket_name
}
output "central_logging_bucket_name_us-west-2" {
  value = module.regional-resource-us-west-2.central_logging_bucket_name
}
output "tenant_config_table_arn_af-south-1" {
  value = module.regional-resource-af-south-1.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-east-1" {
  value = module.regional-resource-ap-east-1.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-northeast-1" {
  value = module.regional-resource-ap-northeast-1.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-northeast-2" {
  value = module.regional-resource-ap-northeast-2.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-northeast-3" {
  value = module.regional-resource-ap-northeast-3.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-south-1" {
  value = module.regional-resource-ap-south-1.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-south-2" {
  value = module.regional-resource-ap-south-2.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-southeast-1" {
  value = module.regional-resource-ap-southeast-1.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-southeast-2" {
  value = module.regional-resource-ap-southeast-2.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-southeast-3" {
  value = module.regional-resource-ap-southeast-3.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-southeast-4" {
  value = module.regional-resource-ap-southeast-4.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-southeast-5" {
  value = module.regional-resource-ap-southeast-5.tenant_config_table_arn
}
output "tenant_config_table_arn_ap-southeast-7" {
  value = module.regional-resource-ap-southeast-7.tenant_config_table_arn
}
output "tenant_config_table_arn_ca-central-1" {
  value = module.regional-resource-ca-central-1.tenant_config_table_arn
}
output "tenant_config_table_arn_ca-west-1" {
  value = module.regional-resource-ca-west-1.tenant_config_table_arn
}
output "tenant_config_table_arn_eu-central-1" {
  value = module.regional-resource-eu-central-1.tenant_config_table_arn
}
output "tenant_config_table_arn_eu-central-2" {
  value = module.regional-resource-eu-central-2.tenant_config_table_arn
}
output "tenant_config_table_arn_eu-north-1" {
  value = module.regional-resource-eu-north-1.tenant_config_table_arn
}
output "tenant_config_table_arn_eu-south-1" {
  value = module.regional-resource-eu-south-1.tenant_config_table_arn
}
output "tenant_config_table_arn_eu-south-2" {
  value = module.regional-resource-eu-south-2.tenant_config_table_arn
}
output "tenant_config_table_arn_eu-west-1" {
  value = module.regional-resource-eu-west-1.tenant_config_table_arn
}
output "tenant_config_table_arn_eu-west-2" {
  value = module.regional-resource-eu-west-2.tenant_config_table_arn
}
output "tenant_config_table_arn_eu-west-3" {
  value = module.regional-resource-eu-west-3.tenant_config_table_arn
}
output "tenant_config_table_arn_il-central-1" {
  value = module.regional-resource-il-central-1.tenant_config_table_arn
}
output "tenant_config_table_arn_me-central-1" {
  value = module.regional-resource-me-central-1.tenant_config_table_arn
}
output "tenant_config_table_arn_me-south-1" {
  value = module.regional-resource-me-south-1.tenant_config_table_arn
}
output "tenant_config_table_arn_mx-central-1" {
  value = module.regional-resource-mx-central-1.tenant_config_table_arn
}
output "tenant_config_table_arn_sa-east-1" {
  value = module.regional-resource-sa-east-1.tenant_config_table_arn
}
output "tenant_config_table_arn_us-east-1" {
  value = module.regional-resource-us-east-1.tenant_config_table_arn
}
output "tenant_config_table_arn_us-east-2" {
  value = module.regional-resource-us-east-2.tenant_config_table_arn
}
output "tenant_config_table_arn_us-west-2" {
  value = module.regional-resource-us-west-2.tenant_config_table_arn
}
