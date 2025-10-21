output "central_log_distribution_role_arn" {
  description = "ARN of the central log distribution role for cross-account access"
  value       = aws_iam_role.central_log_distribution_role.arn
}

output "central_log_distribution_role_name" {
  description = "Name of the central log distribution role"
  value       = aws_iam_role.central_log_distribution_role.name
}

output "central_s3_writer_role_arn" {
  description = "ARN of the central S3 writer role for Vector agents"
  value       = aws_iam_role.central_s3_writer_role.arn
}

output "central_s3_writer_role_name" {
  description = "Name of the central S3 writer role"
  value       = aws_iam_role.central_s3_writer_role.name
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role for log processing"
  value       = aws_iam_role.lambda_execution_role.arn
}

output "lambda_execution_role_name" {
  description = "Name of the Lambda execution role"
  value       = aws_iam_role.lambda_execution_role.name
}

output "authorizer_execution_role_arn" {
  description = "ARN of the Lambda authorizer execution role"
  value       = aws_iam_role.authorizer_execution_role.arn
}

output "authorizer_execution_role_name" {
  description = "Name of the Lambda authorizer execution role"
  value       = aws_iam_role.authorizer_execution_role.name
}

output "api_execution_role_arn" {
  description = "ARN of the Lambda api execution role"
  value       = aws_iam_role.api_execution_role.arn
}

output "api_execution_role_name" {
  description = "Name of the Lambda api execution role"
  value       = aws_iam_role.api_execution_role.name
}

output "api_gateway_authorizer_role_arn" {
  description = "ARN of the API Gateway authorizer role"
  value       = aws_iam_role.api_gateway_authorizer_role.arn
}

output "api_gateway_authorizer_name" {
  description = "Name of the API Gateway authorizer role"
  value       = aws_iam_role.api_gateway_authorizer_role.name
}

output "api_auth_secret_arn" {
  description = "ARN of the Secrets Manager secret containing API authentication PSK"
  value       = aws_secretsmanager_secret.api_auth_psk.arn
}

output "api_auth_secret_name" {
  description = "Name of the Secrets Manager secret containing API authentication PSK"
  value       = aws_secretsmanager_secret.api_auth_psk.name
}
