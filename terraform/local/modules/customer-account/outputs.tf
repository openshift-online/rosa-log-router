output "log_delivery_bucket_name" {
  description = "Name of the S3 bucket for log delivery"
  value       = aws_s3_bucket.log_delivery_bucket.id
}

output "log_delivery_bucket_arn" {
  description = "ARN of the S3 bucket for log delivery"
  value       = aws_s3_bucket.log_delivery_bucket.arn
}

output "log_distribution_role_arn" {
  description = "ARN of the IAM role for log distribution"
  value       = aws_iam_role.log_distribution_role.arn
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.customer_logs.name
}
