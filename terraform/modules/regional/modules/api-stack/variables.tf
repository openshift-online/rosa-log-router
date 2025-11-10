variable "environment" {
  description = "Environment name"
  type        = string
  default     = "int"
  validation {
    condition     = contains(["prod", "stage", "int"], var.environment)
    error_message = "Environment must be one of: prod, stage, int."
  }
}

variable "project_name" {
  description = "Name of the project for resource naming"
  type        = string
  default     = "hcp-log"
}

variable "api_auth_secret_name" {
  description = "Secrets Manager secret name containing the PSK for API authentication"
  type        = string
}

variable "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  type        = string
}

variable "authorizer_execution_role_arn" {
  description = "ARN of the global Lambda authorizer execution role"
  type        = string
}

variable "authorizer_image" {
  description = "ECR image for the Lambda authorizer container image"
  type        = string
}

variable "api_execution_role_arn" {
  description = "ARN of the global Lambda api execution role"
  type        = string
}

variable "api_image" {
  description = "ECR image for the API service container image"
  type        = string
}

variable "api_gateway_authorizer_role_arn" {
  description = "ARN of the global API Gateway authorizer execution role"
  type        = string
}

variable "api_gateway_cloudwatch_role_arn" {
  description = "ARN of the global API Gateway cloudwatch execution role"
  type        = string
}

variable "route53_zone_id" {
  description = "Zone id of the customer domain"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}