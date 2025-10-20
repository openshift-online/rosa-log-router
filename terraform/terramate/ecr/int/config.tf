// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

variable "access_key" {
}
variable "secret_key" {
}
variable "region" {
}
terraform {
  required_version = ">= 1.8.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {
  }
}
provider "aws" {
  access_key = var.access_key
  region     = var.region
  secret_key = var.secret_key
}
provider "aws" {
  alias  = "ap-northeast-2"
  region = "ap-northeast-2"
}
provider "aws" {
  alias  = "ap-southeast-1"
  region = "ap-southeast-1"
}
provider "aws" {
  alias  = "us-east-1"
  region = "us-east-1"
}
provider "aws" {
  alias  = "us-east-2"
  region = "us-east-2"
}
