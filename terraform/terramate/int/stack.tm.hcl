stack {
  name        = "int-environment"
  description = "Integration environment infrastructure"
}

globals "aws" {
  regions = ["us-east-1", "us-east-2"]
}

generate_hcl "main.tf" {
  content {

    module "global" {
      source = "../../modules/global"

      project_name = var.project_name
      environment  = var.environment
    }

    tm_dynamic "module" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["regional-resource-${region.value}"]
      attributes = {
        source = "../../modules/regional"

        providers = {
          aws = tm_hcl_expression("aws.${region.value}")
        }
        project_name                      = var.project_name
        environment                       = var.environment
        include_sqs_stack                 = var.include_sqs_stack
        include_lambda_stack              = var.include_lambda_stack
        ecr_image                         = var.ecr_image
        s3_delete_after_days              = var.s3_delete_after_days
        enable_s3_encryption              = var.enable_s3_encryption
        central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
        lambda_execution_role_arn         = module.global.lambda_execution_role_arn
      }
    }
  }
}

generate_hcl "config.tf" {
  content {
    terraform {
      required_version = ">= 1.0"
      required_providers {
        aws = {
          source  = "hashicorp/aws"
          version = "~> 5.0"
        }
        random = {
          source  = "hashicorp/random"
          version = "~> 3.1"
        }
      }
    }

    provider "aws" {
      region = var.aws_region
    }

    tm_dynamic "provider" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["aws"]
      attributes = {
        alias  = region.value
        region = region.value
      }
    }
  }
}

generate_hcl "outputs.tf" {
  content {

    output "project_name" {
      description = "Project name used for resource naming"
      value       = var.project_name
    }

    output "environment" {
      description = "Environment name"
      value       = var.environment
    }

    output "central_log_distribution_role_arn" {
      description = "ARN of the central log distribution role for cross-account access"
      value       = module.global.central_log_distribution_role_arn
    }
    output "central_s3_writer_role_arn" {
      description = "ARN of the central S3 writer role for Vector agents"
      value       = module.global.central_s3_writer_role_arn
    }

    tm_dynamic "output" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["central_logging_bucket_name_${region.value}"]
      attributes = {
        value = tm_hcl_expression("module.regional-resource-${region.value}.central_logging_bucket_name")
      }
    }

    tm_dynamic "output" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["tenant_config_table_name_${region.value}"]
      attributes = {
        value = tm_hcl_expression("module.regional-resource-${region.value}.tenant_config_table_name")
      }
    }

    tm_dynamic "output" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["tenant_config_table_arn_${region.value}"]
      attributes = {
        value = tm_hcl_expression("module.regional-resource-${region.value}.tenant_config_table_arn")
      }
    }
  }
}
