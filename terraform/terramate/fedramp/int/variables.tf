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
  description = "AWS GovCloud region for deployment"
  type        = string
  default     = "us-gov-west-1"
  validation {
    condition     = contains(["us-gov-west-1", "us-gov-east-1"], var.aws_region)
    error_message = "AWS region must be a valid GovCloud region: us-gov-west-1 or us-gov-east-1."
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

variable "processor_image" {
  description = "ECR image for the log processor container image"
  type        = string
}

variable "api_auth_psk_value" {
  description = "The PSK value for API authentication"
  type        = string
  sensitive   = true
}

variable "authorizer_image" {
  description = "ECR image for the Lambda authorizer container image"
  type        = string
}

variable "api_image" {
  description = "ECR image for the API service container image"
  type        = string
}

variable "allowed_vpc_ids" {
  description = "Per-region VPC id permitted to invoke the private API, matched against aws:sourceVpc in the resource policy. Keyed by AWS region (e.g. us-gov-west-1). Injected by CI/CD. A region absent from the map (or mapped to \"\") produces a deny-all lockdown policy for that region. Only used when private_endpoint is true."
  type        = map(string)
  default     = {}
}

variable "route53_zone_id" {
  description = "Zone id of the customer domain (public path only; unused for the private endpoint where DNS is owned by the consumer account)"
  type        = string
  default     = ""
}

variable "base_domain" {
  description = "Base DNS domain for the API custom domain"
  type        = string
  default     = "devshift.net"
}
