# Variables for local testing configuration

variable "deploy_lambda" {
  description = "Whether to deploy Lambda function and event source mapping"
  type        = bool
  default     = true
}

variable "lambda_image_tag" {
  description = "Tag for Lambda container image"
  type        = string
  default     = "local"
}
