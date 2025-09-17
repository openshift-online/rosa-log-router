terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Local values for resource naming and tagging
locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Core Infrastructure Module
module "core_infrastructure" {
  source = "./modules/core-infrastructure"

  environment                       = var.environment
  project_name                      = var.project_name
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = var.central_log_distribution_role_arn

  tags = merge(local.common_tags, {
    StackType = "core-infrastructure"
  })
}

# SQS Stack Module (Optional)
module "sqs_stack" {
  count  = var.include_sqs_stack ? 1 : 0
  source = "./modules/sqs-stack"

  environment            = var.environment
  project_name           = var.project_name
  log_delivery_topic_arn = module.core_infrastructure.log_delivery_topic_arn

  tags = merge(local.common_tags, {
    StackType = "sqs-infrastructure"
  })
}

# Lambda Stack Module (Optional)
module "lambda_stack" {
  count  = var.include_lambda_stack ? 1 : 0
  source = "./modules/lambda-stack"

  environment                       = var.environment
  project_name                      = var.project_name
  tenant_config_table_name          = module.core_infrastructure.tenant_config_table_name
  sqs_queue_arn                     = var.include_sqs_stack ? module.sqs_stack[0].log_delivery_queue_arn : ""
  ecr_image                         = var.ecr_image
  central_log_distribution_role_arn = var.central_log_distribution_role_arn
  lambda_execution_role_arn         = var.lambda_execution_role_arn

  tags = merge(local.common_tags, {
    StackType = "lambda-functions"
  })
}
