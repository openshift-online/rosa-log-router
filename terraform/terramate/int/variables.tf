# Basic Configuration Variables
variable "project_name" {
  description = "Name of the project for resource naming"
  type        = string
  default     = "hcp-log"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "int"
  validation {
    condition     = contains(["prod", "stage", "int"], var.environment)
    error_message = "Environment must be one of: prod, stage, int."
  }
}

variable "org_id" {
  description = "ID of osdfm org"
  type        = string
  default     = ""
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]{1}$", var.aws_region))
    error_message = "AWS region must be a valid region format (e.g., us-east-1, eu-west-1)."
  }
}

# Regional Module Configuration
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

variable "ecr_image" {
  description = "ECR container image for the log processor (required if include_lambda_stack is true)"
  type        = string
  default     = ""
  validation {
    condition     = var.ecr_image == "" || can(regex("^[a-zA-Z0-9\\-_/]+:[a-zA-Z0-9\\-_.]+$", var.ecr_image))
    error_message = "ECR image URI must be a valid image or empty string."
  }
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
