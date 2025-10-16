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

# Optional Stack Configuration
variable "include_sqs_stack" {
  description = "Whether to deploy the SQS stack for log processing"
  type        = bool
  default     = true
}

variable "include_lambda_stack" {
  description = "Whether to deploy the Lambda stack for container-based log processing"
  type        = bool
  default     = true
}

variable "include_api_stack" {
  description = "Whether to deploy the API stack"
  type        = bool
  default     = true
}

variable "random_suffix" {
  description = "Bucket name random suffix"
  type        = string
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

variable "lambda_execution_role_arn" {
  description = "ARN of the global Lambda execution role"
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.*lambda-execution-role$", var.lambda_execution_role_arn))
    error_message = "Must be a valid IAM role ARN for Lambda execution."
  }
}

variable "api_auth_ssm_parameter" {
  description = "SSM parameter name containing the PSK for API authentication"
  type        = string
}

variable "authorizer_execution_role_arn" {
  description = "ARN of the global Lambda authorizer execution role"
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.*api-authorizer-role$", var.authorizer_execution_role_arn))
    error_message = "Must be a valid IAM role ARN for Lambda execution."
  }
}

variable "authorizer_image" {
  description = "ECR image for the Lambda authorizer container image"
  type        = string
}

variable "api_execution_role_arn" {
  description = "ARN of the global Lambda api execution role"
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.*api-service-role", var.api_execution_role_arn))
    error_message = "Must be a valid IAM role ARN for Lambda execution."
  }
}

variable "api_image" {
  description = "ECR image for the API service container image"
  type        = string
}

variable "api_gateway_authorizer_role_arn" {
  description = "ARN of the global API Gateway authorizer execution role"
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.*api-gateway-authorizer-role", var.api_gateway_authorizer_role_arn))
    error_message = "Must be a valid IAM role ARN for API Gateway."
  }
}
