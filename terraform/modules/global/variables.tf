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

variable "api_auth_ssm_parameter" {
  description = "SSM parameter name containing the PSK for API authentication"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}