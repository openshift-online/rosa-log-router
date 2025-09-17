# Outputs for core infrastructure

output "central_logging_bucket_name" {
  description = "Name of the central logging S3 bucket"
  value       = aws_s3_bucket.central_logging_bucket.id
}

output "central_logging_bucket_arn" {
  description = "ARN of the central logging S3 bucket"
  value       = aws_s3_bucket.central_logging_bucket.arn
}

output "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  value       = aws_dynamodb_table.tenant_config_table.name
}

output "tenant_config_table_arn" {
  description = "ARN of the tenant configuration DynamoDB table"
  value       = aws_dynamodb_table.tenant_config_table.arn
}

# SNS Outputs
output "log_delivery_topic_arn" {
  description = "ARN of the log delivery SNS topic"
  value       = aws_sns_topic.log_delivery_topic.arn
}

# KMS Outputs (conditional)
output "kms_key_id" {
  description = "KMS key ID for encryption"
  value       = var.enable_s3_encryption ? aws_kms_key.logging_kms_key[0].key_id : ""
}

output "kms_key_arn" {
  description = "KMS key ARN for encryption"
  value       = var.enable_s3_encryption ? aws_kms_key.logging_kms_key[0].arn : ""
}
