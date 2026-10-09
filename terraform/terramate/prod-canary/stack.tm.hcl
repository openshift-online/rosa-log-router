stack {
  name        = "prod-canary-environment"
  description = "Prod canary environment infrastructure (subset of regions deployed before full prod)"
}

globals "aws" {
  regions = [
    "ap-east-1",
    "ap-northeast-1",
    "ap-south-1",
    "ap-south-2"
  ]
  delete_regions = []
  default_tags = {
    "app-code"               = "OSD-002"
    "cost-center"            = "148"
    "service-phase"          = "prod"
    "managed_by_integration" = "terraform-repo"
  }
}

generate_hcl "main.tf" {
  content {

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
        random_suffix                     = var.random_suffix
        s3_delete_after_days              = var.s3_delete_after_days
        enable_s3_encryption              = var.enable_s3_encryption
        central_log_distribution_role_arn = var.central_log_distribution_role_arn
        processor_image                   = var.processor_image
        lambda_execution_role_arn         = var.lambda_execution_role_arn
        api_auth_secret_name              = var.api_auth_secret_name
        authorizer_execution_role_arn     = var.authorizer_execution_role_arn
        authorizer_image                  = var.authorizer_image
        api_execution_role_arn            = var.api_execution_role_arn
        api_image                         = var.api_image
        api_gateway_authorizer_role_arn   = var.api_gateway_authorizer_role_arn
        api_gateway_cloudwatch_role_arn   = var.api_gateway_cloudwatch_role_arn
        route53_zone_id                   = var.route53_zone_id
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
      }
      backend "s3" {}
    }

    provider "aws" {
      access_key = var.access_key
      secret_key = var.secret_key
      region     = var.region
      default_tags {
        tags = global.aws.default_tags
      }
    }

    tm_dynamic "provider" {
      for_each = tm_concat(global.aws.regions, global.aws.delete_regions)
      iterator = region
      labels   = ["aws"]
      content {
        alias  = region.value
        region = region.value
        default_tags {
          tags = global.aws.default_tags
        }
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
      labels   = ["api_endpoint_${region.value}"]
      attributes = {
        value = tm_hcl_expression("module.regional-resource-${region.value}.api_endpoint")
      }
    }
  }
}
