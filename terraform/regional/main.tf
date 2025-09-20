terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Local values for resource naming and tagging
locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
  
  stack_name = "${var.project_name}-${var.environment}"
}

# Core Infrastructure Module
module "core_infrastructure" {
  source = "./modules/core-infrastructure"

  environment                        = var.environment
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

  environment             = var.environment
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

  environment                        = var.environment
  project_name                      = var.project_name
  tenant_config_table_name          = module.core_infrastructure.tenant_config_table_name
  tenant_config_table_arn           = module.core_infrastructure.tenant_config_table_arn
  sqs_queue_arn                     = var.include_sqs_stack ? module.sqs_stack[0].log_delivery_queue_arn : ""
  sqs_queue_url                     = var.include_sqs_stack ? module.sqs_stack[0].log_delivery_queue_url : ""
  ecr_image_uri                     = var.ecr_image_uri
  central_log_distribution_role_arn = var.central_log_distribution_role_arn
  central_logging_bucket_arn        = module.core_infrastructure.central_logging_bucket_arn

  tags = merge(local.common_tags, {
    StackType = "lambda-functions"
  })
}

# API Stack Module (Optional)
module "api_stack" {
  count  = var.include_api_stack ? 1 : 0
  source = "./modules/api-stack"

  environment                = var.environment
  project_name              = var.project_name
  api_auth_ssm_parameter    = var.api_auth_ssm_parameter
  tenant_config_table_name  = module.core_infrastructure.tenant_config_table_name
  tenant_config_table_arn   = module.core_infrastructure.tenant_config_table_arn
  authorizer_image_uri      = var.authorizer_image_uri
  api_image_uri             = var.api_image_uri

  tags = merge(local.common_tags, {
    StackType = "api-management"
  })
}