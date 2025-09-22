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

variable "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role from global stack"
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/ROSA-CentralLogDistributionRole-[a-f0-9]{8}$", var.central_log_distribution_role_arn))
    error_message = "Must be a valid IAM role ARN matching the expected pattern."
  }
}

variable "random_suffix" {
  description = "Bucket name random suffix"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}