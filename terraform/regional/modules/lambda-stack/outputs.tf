# Outputs for Lambda stack

output "log_distributor_function_name" {
  description = "Name of the log distributor Lambda function"
  value       = aws_lambda_function.log_distributor_function.function_name
}

output "log_distributor_function_arn" {
  description = "ARN of the log distributor Lambda function"
  value       = aws_lambda_function.log_distributor_function.arn
}