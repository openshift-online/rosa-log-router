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

variable "api_auth_psk_value" {
  description = "The PSK value for API authentication"
  type        = string
  sensitive   = true
}

variable "region" {
}

variable "regions" {
  description = "List of AWS regions where the secret should be applied"
  type        = list(string)
}
