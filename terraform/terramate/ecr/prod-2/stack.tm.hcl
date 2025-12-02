stack {
  name        = "prod-2-environment"
  description = "Prod-2 environment ecr resources"
}

globals "aws" {
  pord-2-replicate-regions = [
    "me-central-1",
    "me-south-1",
    "mx-central-1",
    "sa-east-1",
    "us-east-2",
    "us-west-2"
  ]
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
            for_each = [for r in global.aws.pord-2-replicate-regions : r if r != var.region]
            content {
              region      = destination.value
              registry_id = var.prod_account_id
            }
          }
        }
      }
    }
    resource "aws_ecr_repository" "rosa-log-router-api" {
      name     = "rosa-log-router-api"
    }
    resource "aws_ecr_repository" "rosa-log-router-authorizer" {
      name     = "rosa-log-router-authorizer"
    }
    resource "aws_ecr_repository" "rosa-log-router-processor-go" {
      name     = "rosa-log-router-processor-go"
    }
  }
}

generate_hcl "config.tf" {
  content {

    variable "access_key" {}
    variable "secret_key" {}
    variable "region" {}

    variable "prod_account_id" {}

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
  }
}
