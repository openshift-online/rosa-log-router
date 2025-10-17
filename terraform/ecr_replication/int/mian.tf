variable "replicate_regions" {
  description = "List of AWS regions to replicate ECR repositories to"
  type        = list(string)
  default = [
    "ap-northeast-2",
    "ap-southeast-1",
    "us-east-1",
    "us-east-2",
    "us-west-2"
  ]
}

data "aws_caller_identity" "current" {}

variable "access_key" {}
variable "secret_key" {}
variable "region" {}
terraform {
  required_version = ">= 1.8.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.14.0"
    }
  }
  backend "s3" {}
}
provider "aws" {
  access_key = var.access_key
  secret_key = var.secret_key
  region     = var.region
}

resource "aws_ecr_replication_configuration" "ecr_replication" {
  replication_configuration {
    rule {
      dynamic "destination" {
        for_each = toset(var.replicate_regions)

        content {
          region      = destination.value
          registry_id = data.aws_caller_identity.current.account_id
        }
      }
    }
  }
}
