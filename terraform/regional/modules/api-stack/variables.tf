variable "environment" {
  description = "Environment name"
  type        = string
  default     = "development"
  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be one of: production, staging, development."
  }
}

variable "project_name" {
  description = "Name of the project for resource naming"
  type        = string
  default     = "multi-tenant-logging"
}

variable "api_auth_ssm_parameter" {
  description = "SSM parameter name containing the PSK for API authentication"
  type        = string
}

variable "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  type        = string
}

variable "tenant_config_table_arn" {
  description = "ARN of the tenant configuration DynamoDB table"
  type        = string
}

variable "authorizer_image_uri" {
  description = "ECR URI for the Lambda authorizer container image"
  type        = string
}

variable "api_image_uri" {
  description = "ECR URI for the API service container image"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}