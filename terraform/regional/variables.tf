# Basic Configuration
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

# Optional Stack Configuration
variable "include_sqs_stack" {
  description = "Whether to deploy the SQS stack for log processing"
  type        = bool
  default     = true
}

variable "include_lambda_stack" {
  description = "Whether to deploy the Lambda stack for container-based log processing"
  type        = bool
  default     = false
}

variable "ecr_image_uri" {
  description = "URI of the ECR container image for the log processor (required if include_lambda_stack is true)"
  type        = string
  default     = ""
}

# API Stack Configuration
variable "include_api_stack" {
  description = "Whether to deploy the API stack for tenant management"
  type        = bool
  default     = false
}

variable "api_auth_ssm_parameter" {
  description = "SSM parameter name containing the PSK for API authentication (required if include_api_stack is true)"
  type        = string
  default     = ""
}

variable "authorizer_image_uri" {
  description = "URI of the ECR container image for the API authorizer (required if include_api_stack is true)"
  type        = string
  default     = ""
}

variable "api_image_uri" {
  description = "URI of the ECR container image for the API service (required if include_api_stack is true)"
  type        = string
  default     = ""
}

# S3 Configuration
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

# Required Parameters
variable "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role from global stack"
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/ROSA-CentralLogDistributionRole-[a-f0-9]{8}$", var.central_log_distribution_role_arn))
    error_message = "Must be a valid IAM role ARN matching the expected pattern."
  }
}