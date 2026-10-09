// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

output "project_name" {
  description = "Project name used for resource naming"
  value       = var.project_name
}
output "environment" {
  description = "Environment name"
  value       = var.environment
}
output "central_logging_bucket_name_ap-east-1" {
  value = module.regional-resource-ap-east-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-northeast-1" {
  value = module.regional-resource-ap-northeast-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-south-1" {
  value = module.regional-resource-ap-south-1.central_logging_bucket_name
}
output "central_logging_bucket_name_ap-south-2" {
  value = module.regional-resource-ap-south-2.central_logging_bucket_name
}
output "api_endpoint_ap-east-1" {
  value = module.regional-resource-ap-east-1.api_endpoint
}
output "api_endpoint_ap-northeast-1" {
  value = module.regional-resource-ap-northeast-1.api_endpoint
}
output "api_endpoint_ap-south-1" {
  value = module.regional-resource-ap-south-1.api_endpoint
}
output "api_endpoint_ap-south-2" {
  value = module.regional-resource-ap-south-2.api_endpoint
}
