stack {
  name        = "stage-environment"
  description = "Stage environment ecr resources"
}

globals "aws" {
  regions = [
    "ap-southeast-1",
    "ap-southeast-6",
    "mx-central-1",
    "us-east-1",
    "us-east-2",
    "us-west-2"
  ]
  # In case of resources detection, terraform still need to have the provider.
  delete_regions = []
  default_tags = {
    "app-code"               = "OSD-002"
    "cost-center"            = "148"
    "service-phase"          = "stage"
    "managed_by_integration" = "terraform-repo"
  }
}

generate_hcl "main.tf" {

  content {

    data "aws_caller_identity" "current" {}

    resource "aws_ecr_replication_configuration" "ecr_replication" {
      replication_configuration {
        rule {
          dynamic "destination" {
            for_each = [for r in global.aws.regions : r if r != var.region]
            content {
              region      = destination.value
              registry_id = data.aws_caller_identity.current.account_id
            }
          }
        }
      }
    }

    tm_dynamic "resource" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["aws_ecr_repository", "rosa-log-router-api-${region.value}"]
      attributes = {
        provider = tm_hcl_expression("aws.${region.value}")
        name     = "rosa-log-router-api"
      }
    }

    tm_dynamic "resource" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["aws_ecr_repository", "rosa-log-router-authorizer-${region.value}"]
      attributes = {
        provider = tm_hcl_expression("aws.${region.value}")
        name     = "rosa-log-router-authorizer"
      }
    }

    tm_dynamic "resource" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["aws_ecr_repository", "rosa-log-router-processor-${region.value}"]
      attributes = {
        provider = tm_hcl_expression("aws.${region.value}")
        name     = "rosa-log-router-processor"
      }
    }

    tm_dynamic "resource" {
      for_each = global.aws.regions
      iterator = region
      labels   = ["aws_ecr_repository", "rosa-log-router-processor-go-${region.value}"]
      attributes = {
        provider = tm_hcl_expression("aws.${region.value}")
        name     = "rosa-log-router-processor-go"
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
