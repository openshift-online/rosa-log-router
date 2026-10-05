# Outputs for SQS stack

output "log_delivery_queue_arn" {
  description = "ARN of the log delivery SQS queue"
  value       = aws_sqs_queue.log_delivery_queue.arn
}

output "log_delivery_queue_name" {
  description = "Name of the log delivery SQS queue"
  value       = aws_sqs_queue.log_delivery_queue.name
}

output "log_delivery_queue_url" {
  description = "URL of the log delivery SQS queue"
  value       = aws_sqs_queue.log_delivery_queue.id
}

output "log_delivery_dlq_arn" {
  description = "ARN of the log delivery DLQ"
  value       = aws_sqs_queue.log_delivery_dlq.arn
}

output "log_delivery_dlq_name" {
  description = "Name of the log delivery DLQ"
  value       = aws_sqs_queue.log_delivery_dlq.name
}

output "log_delivery_retry_queue_arn" {
  description = "ARN of the log delivery retry queue"
  value       = aws_sqs_queue.log_delivery_retry_queue.arn
}

output "log_delivery_retry_queue_url" {
  description = "URL of the log delivery retry queue"
  value       = aws_sqs_queue.log_delivery_retry_queue.id
}

output "log_delivery_partial_queue_arn" {
  description = "ARN of the partial success queue (Q3)"
  value       = aws_sqs_queue.log_delivery_partial_queue.arn
}

output "log_delivery_partial_queue_url" {
  description = "URL of the partial success queue (Q3)"
  value       = aws_sqs_queue.log_delivery_partial_queue.id
}

output "log_delivery_partial_dlq_arn" {
  description = "ARN of the partial queue DLQ"
  value       = aws_sqs_queue.log_delivery_partial_dlq.arn
}

output "log_delivery_partial_dlq_name" {
  description = "Name of the partial queue DLQ"
  value       = aws_sqs_queue.log_delivery_partial_dlq.name
}
