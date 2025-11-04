variable "customer_name" {
  description = "Customer name (e.g., acme-corp)"
  type        = string
}

variable "account_id" {
  description = "Customer AWS account ID"
  type        = string
}

variable "central_account_id" {
  description = "Central AWS account ID that will assume roles"
  type        = string
}

variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
