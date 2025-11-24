stack {
  name        = "prod-environment"
  description = "Prod environment ecr resources"
}

globals "aws" {
  # ECR replication supports max 25 regions per account. Primary source region is us-east-1.
  # Additional regions beyond 25 are handled via cross-account replication to prod-2 account.
  pord-replicate-regions = [
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
    "us-east-1"
  ]
  pord-2-replicate-regions = [
    "me-central-1",
    "me-south-1",
    "mx-central-1",
    "sa-east-1",
    "us-east-2",
    "us-west-2"
  ]
  regions = tm_concat(global.aws.pord-replicate-regions, global.aws.pord-2-replicate-regions)
  # Regions to remove. Terraform still requires provider configuration for deletion operations.
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

    data "aws_caller_identity" "current" {}

    resource "aws_ecr_replication_configuration" "ecr_replication" {
      replication_configuration {
        rule {
          dynamic "destination" {
            for_each = [for r in global.aws.pord-replicate-regions : r if r != var.region]
            content {
              region      = destination.value
              registry_id = data.aws_caller_identity.current.account_id
            }
          }
        }
      }
    }

    tm_dynamic "resource" {
      for_each = global.aws.pord-2-replicate-regions
      iterator = region
      labels   = ["aws_ecr_registry_policy", "cross-account-replication-policy-${region.value}"]
      content {
        provider = tm_hcl_expression("aws.${region.value}")
        policy = jsonencode({
          Version = "2012-10-17",
          Statement = [
            {
              Sid    = "testpolicy",
              Effect = "Allow",
              Principal = {
                "AWS" : "arn:aws:iam::${var.prod_2_account_id}:root"
              },
              Action = [
                "ecr:ReplicateImage"
              ],
              Resource = [
                "arn:aws:ecr:${region.value}:${data.aws_caller_identity.current.account_id}:repository/*"
              ]
            }
          ]
        })
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

    variable "prod_2_account_id" {}

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
