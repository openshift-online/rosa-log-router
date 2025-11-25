stack {
  name        = "prod-environment"
  description = "Prod environment infrastructure"
}

globals "aws" {
  regions = [
    "af-south-1",
    "ap-east-1",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ap-south-1",
    "ap-south-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-southeast-3",
    "ap-southeast-4",
    "ap-southeast-5",
    "ap-southeast-6",
    "ap-southeast-7",
    "ca-central-1",
    "ca-west-1",
    "eu-central-1",
    "eu-central-2",
    "eu-north-1",
    "eu-south-1",
    "eu-south-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "il-central-1",
    "me-central-1",
    "me-south-1",
    "mx-central-1",
    "sa-east-1",
    "us-east-1",
    "us-east-2",
    "us-west-2"
  ]
  # In case of resources detection, terraform still need to have the provider.
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

    resource "random_id" "suffix" {
      byte_length = 4
    }

    locals {
      random_suffix = random_id.suffix.hex
    }

    module "global" {
      source = "../../modules/global"

      project_name       = var.project_name
      environment        = var.environment
      org_id             = var.org_id
      api_auth_psk_value = var.api_auth_psk_value
      region             = var.region
      regions            = global.aws.regions
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
        random_suffix                     = local.random_suffix
        s3_delete_after_days              = var.s3_delete_after_days
        enable_s3_encryption              = var.enable_s3_encryption
        central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
        processor_image                   = var.processor_image
        lambda_execution_role_arn         = module.global.lambda_execution_role_arn
        api_auth_secret_name              = module.global.api_auth_secret_name
        authorizer_execution_role_arn     = module.global.authorizer_execution_role_arn
        authorizer_image                  = var.authorizer_image
        api_execution_role_arn            = module.global.api_execution_role_arn
        api_image                         = var.api_image
        api_gateway_authorizer_role_arn   = module.global.api_gateway_authorizer_role_arn
        api_gateway_cloudwatch_role_arn   = module.global.api_gateway_cloudwatch_role_arn
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

    output "api_auth_psk_value" {
      description = "The PSK value for API authentication"
      value       = var.api_auth_psk_value
      sensitive   = true
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
      labels   = ["api_endpoint_${region.value}"]
      attributes = {
        value = tm_hcl_expression("module.regional-resource-${region.value}.api_endpoint")
      }
    }
  }
}
