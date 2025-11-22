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
      service-phase          = "stage"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-1"
  region = "ap-southeast-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "stage"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-6"
  region = "ap-southeast-6"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "stage"
    }
  }
}
provider "aws" {
  alias  = "mx-central-1"
  region = "mx-central-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "stage"
    }
  }
}
provider "aws" {
  alias  = "us-east-1"
  region = "us-east-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "stage"
    }
  }
}
provider "aws" {
  alias  = "us-east-2"
  region = "us-east-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "stage"
    }
  }
}
provider "aws" {
  alias  = "us-west-2"
  region = "us-west-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "stage"
    }
  }
}
