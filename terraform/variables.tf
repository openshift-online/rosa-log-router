# Variables for the multi-tenant logging infrastructure

variable "aws_region" {
  description = "AWS region for the infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (production, staging, development)"
  type        = string
  default     = "production"
  
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

# EKS Configuration
variable "eks_oidc_issuer" {
  description = "OIDC issuer URL for the EKS cluster (without https://)"
  type        = string
  default     = ""
}

variable "cluster_names" {
  description = "List of Kubernetes cluster names that will send logs"
  type        = list(string)
  default     = ["prod-cluster-1", "prod-cluster-2"]
}

# Lambda Configuration
variable "lambda_reserved_concurrency" {
  description = "Reserved concurrency for the log distributor Lambda function"
  type        = number
  default     = 100
}

variable "lambda_max_concurrency" {
  description = "Maximum concurrency for Lambda event source mapping"
  type        = number
  default     = 50
}

variable "lambda_vpc_config" {
  description = "VPC configuration for Lambda function"
  type = object({
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}

variable "enable_lambda_canary" {
  description = "Enable canary deployments for Lambda function"
  type        = bool
  default     = false
}

variable "lambda_canary_version" {
  description = "Version number for canary deployment"
  type        = string
  default     = "1"
}

variable "lambda_canary_weight" {
  description = "Traffic weight for canary deployment (0.0 to 1.0)"
  type        = number
  default     = 0.1
}

variable "enable_lambda_insights" {
  description = "Enable CloudWatch Lambda Insights"
  type        = bool
  default     = true
}

variable "enable_dlq_processor" {
  description = "Enable DLQ processor Lambda function"
  type        = bool
  default     = true
}

# Firehose Configuration
variable "firehose_buffer_size_mb" {
  description = "Buffer size for Firehose in MB"
  type        = number
  default     = 128
  
  validation {
    condition     = var.firehose_buffer_size_mb >= 1 && var.firehose_buffer_size_mb <= 128
    error_message = "Firehose buffer size must be between 1 and 128 MB."
  }
}

variable "firehose_buffer_interval_seconds" {
  description = "Buffer interval for Firehose in seconds"
  type        = number
  default     = 900
  
  validation {
    condition     = var.firehose_buffer_interval_seconds >= 60 && var.firehose_buffer_interval_seconds <= 900
    error_message = "Firehose buffer interval must be between 60 and 900 seconds."
  }
}

# S3 Configuration
variable "s3_lifecycle_transition_days" {
  description = "Days after which to transition S3 objects to different storage classes"
  type = object({
    standard_ia = number
    glacier     = number
    deep_archive = number
  })
  default = {
    standard_ia = 30
    glacier     = 90
    deep_archive = 365
  }
}

variable "s3_log_retention_days" {
  description = "Number of days to retain logs in S3"
  type        = number
  default     = 2555  # 7 years
}

# Monitoring Configuration
variable "enable_analytics" {
  description = "Enable analytics processing pipeline"
  type        = bool
  default     = false
}

variable "alert_email_endpoints" {
  description = "List of email addresses for alerts"
  type        = list(string)
  default     = []
}

variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring"
  type        = bool
  default     = true
}

# Cost Optimization
variable "enable_s3_intelligent_tiering" {
  description = "Enable S3 Intelligent Tiering for cost optimization"
  type        = bool
  default     = true
}

variable "enable_parquet_conversion" {
  description = "Enable Parquet format conversion in Firehose"
  type        = bool
  default     = true
}

# Security Configuration
variable "enable_s3_encryption" {
  description = "Enable S3 server-side encryption"
  type        = bool
  default     = true
}

variable "kms_key_id" {
  description = "KMS key ID for encryption (optional)"
  type        = string
  default     = null
}

variable "enable_vpc_endpoints" {
  description = "Enable VPC endpoints for AWS services"
  type        = bool
  default     = false
}

# Multi-Region Configuration
variable "enable_cross_region_replication" {
  description = "Enable cross-region replication for S3 buckets"
  type        = bool
  default     = false
}

variable "backup_region" {
  description = "AWS region for backup/replication"
  type        = string
  default     = "us-west-2"
}

# Tenant Configuration
variable "default_tenants" {
  description = "Default tenant configurations to create"
  type = list(object({
    tenant_id                   = string
    account_id                 = string
    environment                = string
    log_distribution_role_arn  = string
    target_region             = string
    retention_days            = number
    max_log_rate_per_minute   = number
    alert_endpoints           = list(object({
      type     = string
      endpoint = string
    }))
  }))
  default = []
}

# Tagging
variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "multi-tenant-logging"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

variable "cost_center" {
  description = "Cost center for billing allocation"
  type        = string
  default     = ""
}

# Feature Flags
variable "enable_xray_tracing" {
  description = "Enable AWS X-Ray tracing"
  type        = bool
  default     = true
}

variable "enable_enhanced_monitoring" {
  description = "Enable enhanced monitoring and custom metrics"
  type        = bool
  default     = true
}

variable "enable_log_sampling" {
  description = "Enable log sampling for cost optimization"
  type        = bool
  default     = false
}

variable "log_sampling_rate" {
  description = "Sampling rate for logs (0.0 to 1.0)"
  type        = number
  default     = 1.0
  
  validation {
    condition     = var.log_sampling_rate >= 0.0 && var.log_sampling_rate <= 1.0
    error_message = "Log sampling rate must be between 0.0 and 1.0."
  }
}