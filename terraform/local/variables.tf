# Variables for local testing configuration

variable "deploy_lambda" {
  description = "Whether to deploy Lambda function and event source mapping"
  type        = bool
  default     = true
}

variable "use_container_image" {
  description = "Use container image for Lambda instead of zip file (requires LocalStack Pro)"
  type        = bool
  default     = false
}

variable "use_container" {
  description = "Which implementation to use: 'pyzip' for Python zip, 'py' for Python container, or 'go' for Go container"
  type        = string
  default     = "pyzip"

  validation {
    condition     = contains(["pyzip", "py", "go"], var.use_container)
    error_message = "use_container must be one of: 'pyzip', 'py', or 'go'"
  }
}

variable "lambda_zip_path" {
  description = "Path to the Lambda function zip file"
  type        = string
  default     = "log-processor.zip"
}

variable "lambda_image_tag" {
  description = "Tag for Lambda container image (used when use_container_image = true)"
  type        = string
  default     = "latest"
}
