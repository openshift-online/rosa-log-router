// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

data "aws_caller_identity" "current" {
}
resource "aws_ecr_replication_configuration" "ecr_replication" {
  replication_configuration {
    rule {
      dynamic "destination" {
        for_each = [for r in ["us-gov-east-1", "us-gov-west-1"] : r if r != var.region]
        content {
          region      = destination.value
          registry_id = data.aws_caller_identity.current.account_id
        }
      }
    }
  }
}
resource "aws_ecr_repository" "rosa-log-router-api-us-gov-east-1" {
  name     = "rosa-log-router-api"
  provider = aws.us-gov-east-1
}
resource "aws_ecr_repository" "rosa-log-router-api-us-gov-west-1" {
  name     = "rosa-log-router-api"
  provider = aws.us-gov-west-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-us-gov-east-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.us-gov-east-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-us-gov-west-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.us-gov-west-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-us-gov-east-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.us-gov-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-us-gov-west-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.us-gov-west-1
}
