# Variables for local testing configuration

variable "deploy_lambda" {
  description = "Whether to deploy Lambda function and event source mapping"
  type        = bool
  default     = true
}

variable "lambda_zip_path" {
  description = "Path to the Lambda function zip file"
  type        = string
  default     = "log-processor.zip"  # Default to local e2e testing zip
}
