# Outputs for local testing

##############################################################################
# Central Account Outputs
##############################################################################

output "central_account_id" {
  description = "Central account ID (LocalStack namespace)"
  value       = local.central_account_id
}

output "central_source_bucket" {
  description = "Central S3 bucket where Vector writes logs"
  value       = module.central_core_infrastructure.central_logging_bucket_name
}

output "central_sqs_queue_url" {
  description = "SQS queue URL for manual testing"
  value       = module.central_sqs_stack.log_delivery_queue_url
}

output "central_dynamodb_table" {
  description = "DynamoDB table name for tenant configs"
  value       = module.central_core_infrastructure.tenant_config_table_name
}

output "central_lambda_function" {
  description = "Lambda function name (empty if not deployed)"
  value       = var.deploy_lambda ? aws_lambda_function.central_log_distributor[0].function_name : ""
}

output "central_sns_topic" {
  description = "SNS topic ARN"
  value       = module.central_core_infrastructure.log_delivery_topic_arn
}

output "central_log_distribution_role_arn" {
  description = "Central log distribution role ARN (for container scan mode)"
  value       = aws_iam_role.central_log_distribution_role.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for Lambda container images"
  value       = aws_ecr_repository.lambda_processor.repository_url
}

##############################################################################
# Customer Account Outputs
##############################################################################

output "customer1_account_id" {
  description = "Customer 1 (ACME Corp) account ID"
  value       = local.customer1_account_id
}

output "customer1_bucket" {
  description = "ACME Corp log delivery bucket"
  value       = module.customer1_acme_corp.log_delivery_bucket_name
}

output "customer1_role_arn" {
  description = "ACME Corp log distribution role ARN"
  value       = module.customer1_acme_corp.log_distribution_role_arn
}

output "customer2_account_id" {
  description = "Customer 2 (Globex) account ID"
  value       = local.customer2_account_id
}

output "customer2_bucket" {
  description = "Globex log delivery bucket"
  value       = module.customer2_globex.log_delivery_bucket_name
}

output "customer2_role_arn" {
  description = "Globex log distribution role ARN"
  value       = module.customer2_globex.log_distribution_role_arn
}

output "customer2_log_group" {
  description = "Globex CloudWatch log group name"
  value       = module.customer2_globex.cloudwatch_log_group_name
}

##############################################################################
# Testing Commands
##############################################################################

output "test_commands" {
  description = "Commands for testing the setup"
  value = <<-EOT

  # Upload test log to central bucket (triggers S3 → SNS → SQS → Lambda)
  aws --endpoint-url=http://localhost:4566 s3 cp test.json.gz \
    s3://${module.central_core_infrastructure.central_logging_bucket_name}/test-cluster/acme-corp/payment-service/pod-1/test.json.gz

  # Check Lambda logs (if Lambda deployed)
  ${var.deploy_lambda ? "aws --endpoint-url=http://localhost:4566 logs tail /aws/lambda/${aws_lambda_function.central_log_distributor[0].function_name} --follow" : "# Lambda not deployed - using container scan mode instead"}

  # Check customer buckets (cross-account!)
  AWS_ACCESS_KEY_ID=${local.customer1_account_id} aws --endpoint-url=http://localhost:4566 \
    s3 ls s3://${module.customer1_acme_corp.log_delivery_bucket_name}/logs/ --recursive

  AWS_ACCESS_KEY_ID=${local.customer2_account_id} aws --endpoint-url=http://localhost:4566 \
    s3 ls s3://${module.customer2_globex.log_delivery_bucket_name}/platform-logs/ --recursive

  # Test cross-account AssumeRole
  AWS_ACCESS_KEY_ID=${local.central_account_id} aws --endpoint-url=http://localhost:4566 \
    sts assume-role \
    --role-arn ${module.customer1_acme_corp.log_distribution_role_arn} \
    --role-session-name test \
    --external-id ${local.central_account_id}

  EOT
}
