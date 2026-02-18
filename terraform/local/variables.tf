# Variables for local testing configuration

variable "deploy_lambda" {
  description = "Whether to deploy Lambda function and event source mapping"
  type        = bool
  default     = true
}

variable "lambda_image_tag" {
  description = "Tag for Lambda container image (LocalStack uses local images)"
  type        = string
  default     = "local"
}

variable "api_image_tag" {
  description = "Tag for API container images (service and authorizer)"
  type        = string
  default     = "local"
}

variable "api_psk_value" {
  description = "PSK value for API HMAC authentication (testing only - DO NOT use in production)"
  type        = string
  default     = "test-psk-localstack-do-not-use-in-production"
  sensitive   = true
}
