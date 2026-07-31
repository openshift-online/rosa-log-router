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
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "dev"
    }
  }
}
provider "aws" {
  alias  = "us-gov-east-1"
  region = "us-gov-east-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "dev"
    }
  }
}
provider "aws" {
  alias  = "us-gov-west-1"
  region = "us-gov-west-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "dev"
    }
  }
}
