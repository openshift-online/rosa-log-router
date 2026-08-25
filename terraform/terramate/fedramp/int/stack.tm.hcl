stack {
  name        = "fedramp-int-environment"
  description = "FedRAMP integration environment infrastructure"
}

globals "aws" {
  regions = [
    "us-gov-west-1",
    "us-gov-east-1"
  ]
  # In case of resources detection, terraform still need to have the provider.
  delete_regions = []
  default_tags = {
    "app-code"               = "OSD-002"
    "cost-center"            = "148"
    "service-phase"          = "dev"
    "managed_by_integration" = "terraform-repo"
  }
}

# Per-region private (FedRAMP) endpoint configuration.
# Both regions deploy the API as a PRIVATE REST API fronted by a region-templated
# PRIVATE custom domain ({region}.hcp-log.{env}.{base_domain}) so the fixed OCM
# client selects the regional API by hostname exactly as it does in commercial.
# The custom domain uses a public DNS-validated ACM cert (validated in the
# delegated public Route53 zone, var.route53_zone_id) and is reached in-VPC via an
# interface endpoint; the resource policy is locked to the region's allowed VPC.
# A region with no injected VPC id gets a deny-all lockdown policy.
globals "private" {
  config = {
    "us-gov-west-1" = {
      private_endpoint = true
    }
    "us-gov-east-1" = {
      private_endpoint = true
    }
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
      source = "../../../modules/global"

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
        source = "../../../modules/regional"

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
        base_domain                       = var.base_domain
        private_endpoint                  = global.private.config[region.value].private_endpoint
        allowed_vpc_id                    = tm_hcl_expression("lookup(var.allowed_vpc_ids, \"${region.value}\", \"\")")
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

    # ARN of each region's PRIVATE custom domain name. Consumed cross-account by
    # the terraform-ocm-fedramp-aws repo to build the domain-name access
    # association from the OCM cluster's execute-api VPC endpoint.
    tm_dynamic "output" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["custom_domain_arn_${region.value}"]
      attributes = {
        value = tm_hcl_expression("module.regional-resource-${region.value}.custom_domain_arn")
      }
    }

    tm_dynamic "output" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["custom_domain_id_${region.value}"]
      attributes = {
        value = tm_hcl_expression("module.regional-resource-${region.value}.custom_domain_id")
      }
    }

  }
}
