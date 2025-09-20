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

output "central_s3_writer_role_arn" {
  description = "ARN of the Central S3 Writer IAM role"
  value       = aws_iam_role.central_s3_writer_role.arn
}

output "vector_assume_role_policy_arn" {
  description = "ARN of the managed policy for Vector agents to assume S3 writer role"
  value       = aws_iam_policy.vector_assume_role_policy.arn
}

output "regional_log_processor_role_arn" {
  description = "ARN of the regional log processor IAM role"
  value       = aws_iam_role.regional_log_processor_role.arn
}

output "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role (from global stack)"
  value       = var.central_log_distribution_role_arn
}