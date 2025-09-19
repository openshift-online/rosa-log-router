variable "replicate_regions" {
  description = "List of AWS regions to replicate ECR repositories to"
  type        = list(string)
  default = [
    "af-south-1",
    "ap-east-1",
    "ap-south-2",
    "ap-southeast-3",
    "ap-southeast-4",
    "ap-southeast-5",
    "eu-central-2",
    "eu-south-1",
    "eu-south-2",
    "me-central-1",
    "me-south-1",
    "us-west-1",
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
