variable "project_name" {
  description = "Name of the project for resource naming"
  type        = string
  default     = "hcp-log"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["prod", "stage", "int"], var.environment)
    error_message = "Environment must be one of: prod, stage, int."
  }
}

variable "s3_delete_after_days" {
  description = "Number of days after which to delete logs from S3"
  type        = number
  default     = 7
  validation {
    condition     = var.s3_delete_after_days >= 1
    error_message = "S3 delete after days must be at least 1."
  }
}

variable "enable_s3_encryption" {
  description = "Enable S3 server-side encryption"
  type        = bool
  default     = true
}

variable "processor_image" {
  description = "ECR image for the log processor container image"
  type        = string
}

variable "authorizer_image" {
  description = "ECR image for the Lambda authorizer container image"
  type        = string
}

variable "api_image" {
  description = "ECR image for the API service container image"
  type        = string
}

variable "route53_zone_id" {
  description = "Zone id of the customer domain"
  type        = string
}

variable "random_suffix" {
  description = "Random suffix from the prod workspace (must match for consistent S3 bucket naming)"
  type        = string
}

variable "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role (from prod workspace)"
  type        = string
}

variable "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role (from prod workspace)"
  type        = string
}

variable "api_auth_secret_name" {
  description = "Name of the Secrets Manager secret for API auth PSK (from prod workspace)"
  type        = string
}

variable "authorizer_execution_role_arn" {
  description = "ARN of the authorizer Lambda execution role (from prod workspace)"
  type        = string
}

variable "api_execution_role_arn" {
  description = "ARN of the API Lambda execution role (from prod workspace)"
  type        = string
}

variable "api_gateway_authorizer_role_arn" {
  description = "ARN of the API Gateway authorizer role (from prod workspace)"
  type        = string
}

variable "api_gateway_cloudwatch_role_arn" {
  description = "ARN of the API Gateway CloudWatch role (from prod workspace)"
  type        = string
}
