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

variable "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  type        = string
}

variable "sqs_queue_arn" {
  description = "ARN of the SQS queue to process messages from"
  type        = string
}
variable "sqs_queue_url" {
  description = "URL of the SQS queue to re-queue messages"
  type        = string
}

variable "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role for cross-account access"
  type        = string
}

variable "processor_image" {
  description = "ECR image for the log processor container image"
  type        = string
}

variable "lambda_execution_role_arn" {
  description = "ARN of the global Lambda execution role"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}