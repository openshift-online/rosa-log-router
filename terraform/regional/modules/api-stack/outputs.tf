# Outputs for API stack

output "api_endpoint" {
  description = "API Gateway endpoint URL for tenant management"
  value       = "https://${aws_api_gateway_rest_api.tenant_management_api.id}.execute-api.${data.aws_region.current.name}.amazonaws.com/${aws_api_gateway_stage.api_stage.stage_name}"
}

output "api_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.tenant_management_api.id
}