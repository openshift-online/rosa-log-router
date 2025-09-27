stack {
  name        = "stage-environment"
  description = "Stage environment infrastructure"
}

globals "aws" {
  regions = [
    "ap-southeast-1",
    "mx-central-1",
    "us-east-1",
    "us-east-2",
    "us-west-2"
  ]
}

generate_hcl "main.tf" {
  content {

    resource "random_id" "suffix" {
      byte_length = 4
    }

    locals {
      random_suffix = random_id.suffix.hex
    }

    module "global" {
      source = "../../modules/global"

      project_name = var.project_name
      environment  = var.environment
      org_id       = var.org_id
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
        random_suffix                     = local.random_suffix
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

    variable "access_key" {}
    variable "secret_key" {}
    variable "region" {}

    terraform {
      required_version = ">= 1.8.5"
      required_providers {
        aws = {
          source  = "hashicorp/aws"
          version = "~> 6.0"
        }
        random = {
          source  = "hashicorp/random"
          version = "~> 3.1"
        }
      }
      backend "s3" {}
    }

    provider "aws" {
      access_key = var.access_key
      secret_key = var.secret_key
      region     = var.region
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
      labels   = ["tenant_config_table_arn_${region.value}"]
      attributes = {
        value = tm_hcl_expression("module.regional-resource-${region.value}.tenant_config_table_arn")
      }
    }
  }
}
