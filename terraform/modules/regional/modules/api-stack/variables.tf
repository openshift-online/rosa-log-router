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

variable "api_auth_secret_name" {
  description = "Secrets Manager secret name containing the PSK for API authentication"
  type        = string
}

variable "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  type        = string
}

variable "authorizer_execution_role_arn" {
  description = "ARN of the global Lambda authorizer execution role"
  type        = string
}

variable "authorizer_image" {
  description = "ECR image for the Lambda authorizer container image (e.g., repo:tag)"
  type        = string
  default     = ""
}

variable "authorizer_image_uri" {
  description = "Full ECR image URI for the Lambda authorizer container image (e.g., account.dkr.ecr.region.amazonaws.com/repo:tag)"
  type        = string
  default     = ""
}

variable "api_execution_role_arn" {
  description = "ARN of the global Lambda api execution role"
  type        = string
}

variable "api_image" {
  description = "ECR image for the API service container image (e.g., repo:tag)"
  type        = string
  default     = ""
}
variable "api_image_uri" {
  description = "Full ECR image URI for the API service container image (e.g., account.dkr.ecr.region.amazonaws.com/repo:tag)"
  type        = string
  default     = ""
}

variable "api_gateway_authorizer_role_arn" {
  description = "ARN of the global API Gateway authorizer execution role"
  type        = string
}

variable "api_gateway_cloudwatch_role_arn" {
  description = "ARN of the global API Gateway cloudwatch execution role"
  type        = string
}

variable "route53_zone_id" {
  description = "Zone id of the customer domain"
  type        = string
}

variable "base_domain" {
  description = "Base DNS domain for the API custom domain"
  type        = string
  default     = "devshift.net"
}

variable "enable_custom_domain" {
  description = "Enable custom domain with Route53 and ACM (disable for LocalStack)"
  type        = bool
  default     = true
}

variable "private_endpoint" {
  description = "Deploy the API Gateway as a PRIVATE REST API reachable only via an interface VPC endpoint. When true, the endpoint type becomes PRIVATE and the resource policy is locked to allowed_vpc_id. When combined with enable_custom_domain, the custom domain is created as a PRIVATE custom domain (certificate_arn + domain_name_id); the runtime vanity DNS record and the domain-name access association to the VPC endpoint are owned by the consumer account."
  type        = bool
  default     = false
}

variable "allowed_vpc_id" {
  description = "VPC id permitted to invoke the private API (matched against aws:sourceVpc in the resource policy). Only used when private_endpoint is true. An empty value produces a deny-all lockdown policy (compliant but unreachable)."
  type        = string
  default     = ""
}
