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

variable "lambda_zip_path" {
  description = "Path to the Lambda function zip file (used when use_container_image = false)"
  type        = string
  default     = "log-processor.zip"  # Default to local e2e testing zip
}

variable "lambda_image_tag" {
  description = "Tag for Lambda container image (used when use_container_image = true)"
  type        = string
  default     = "latest"
}
