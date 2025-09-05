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

variable "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  type        = string
}

variable "tenant_config_table_arn" {
  description = "ARN of the tenant configuration DynamoDB table"
  type        = string
}

variable "sqs_queue_arn" {
  description = "ARN of the SQS queue to process messages from"
  type        = string
}

variable "sqs_queue_url" {
  description = "URL of the SQS queue"
  type        = string
}

variable "ecr_image_uri" {
  description = "URI of the ECR container image for the log processor"
  type        = string
}

variable "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role for cross-account access"
  type        = string
}

variable "central_logging_bucket_arn" {
  description = "ARN of the central logging S3 bucket"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}