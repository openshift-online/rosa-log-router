# LocalStack multi-account provider configuration
# Uses different AWS_ACCESS_KEY_ID values to simulate different accounts

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.31.0"
    }
  }
}

# LocalStack common endpoint configuration
locals {
  localstack_endpoint = "http://localhost:4566"

  # Simulated account IDs via access keys
  central_account_id   = "111111111111"
  customer1_account_id = "222222222222"
  customer2_account_id = "333333333333"
}

# Central account provider (where log processing happens)
provider "aws" {
  alias                       = "central"
  region                      = "us-east-1"
  access_key                  = local.central_account_id
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true

  # LocalStack S3 requires path-style access
  s3_use_path_style = true

  # Disable default tags for LocalStack (causes timeout issues)
  default_tags {
    tags = {}
  }

  endpoints {
    s3              = local.localstack_endpoint
    sqs             = local.localstack_endpoint
    sns             = local.localstack_endpoint
    dynamodb        = local.localstack_endpoint
    lambda          = local.localstack_endpoint
    iam             = local.localstack_endpoint
    sts             = local.localstack_endpoint
    cloudwatch      = local.localstack_endpoint
    logs            = local.localstack_endpoint
    kms             = local.localstack_endpoint
    ecr             = local.localstack_endpoint
    apigateway      = local.localstack_endpoint
    secretsmanager  = local.localstack_endpoint
  }
}

# Customer Account 1 - ACME Corp
provider "aws" {
  alias                       = "customer1"
  region                      = "us-east-1"
  access_key                  = local.customer1_account_id
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true

  # LocalStack S3 requires path-style access
  s3_use_path_style = true

  # Disable default tags for LocalStack (causes timeout issues)
  default_tags {
    tags = {}
  }

  endpoints {
    s3              = local.localstack_endpoint
    sqs             = local.localstack_endpoint
    sns             = local.localstack_endpoint
    dynamodb        = local.localstack_endpoint
    lambda          = local.localstack_endpoint
    iam             = local.localstack_endpoint
    sts             = local.localstack_endpoint
    cloudwatch      = local.localstack_endpoint
    logs            = local.localstack_endpoint
    kms             = local.localstack_endpoint
    ecr             = local.localstack_endpoint
    apigateway      = local.localstack_endpoint
    secretsmanager  = local.localstack_endpoint
  }
}

# Customer Account 2 - Globex Industries
provider "aws" {
  alias                       = "customer2"
  region                      = "us-east-1"
  access_key                  = local.customer2_account_id
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true

  # LocalStack S3 requires path-style access
  s3_use_path_style = true

  # Disable default tags for LocalStack (causes timeout issues)
  default_tags {
    tags = {}
  }

  endpoints {
    s3              = local.localstack_endpoint
    sqs             = local.localstack_endpoint
    sns             = local.localstack_endpoint
    dynamodb        = local.localstack_endpoint
    lambda          = local.localstack_endpoint
    iam             = local.localstack_endpoint
    sts             = local.localstack_endpoint
    cloudwatch      = local.localstack_endpoint
    logs            = local.localstack_endpoint
    kms             = local.localstack_endpoint
    ecr             = local.localstack_endpoint
    apigateway      = local.localstack_endpoint
    secretsmanager  = local.localstack_endpoint
  }
}

# Default provider points to central account
provider "aws" {
  region                      = "us-east-1"
  access_key                  = local.central_account_id
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true

  # Disable default tags for LocalStack (causes timeout issues)
  default_tags {
    tags = {}
  }

  endpoints {
    s3              = local.localstack_endpoint
    sqs             = local.localstack_endpoint
    sns             = local.localstack_endpoint
    dynamodb        = local.localstack_endpoint
    lambda          = local.localstack_endpoint
    iam             = local.localstack_endpoint
    sts             = local.localstack_endpoint
    cloudwatch      = local.localstack_endpoint
    logs            = local.localstack_endpoint
    kms             = local.localstack_endpoint
    ecr             = local.localstack_endpoint
    apigateway      = local.localstack_endpoint
    secretsmanager  = local.localstack_endpoint
  }
}
