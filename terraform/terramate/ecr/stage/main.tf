// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

data "aws_caller_identity" "current" {
}
resource "aws_ecr_replication_configuration" "ecr_replication" {
  replication_configuration {
    rule {
      dynamic "destination" {
        for_each = [for r in ["ap-southeast-1", "ap-southeast-6", "mx-central-1", "us-east-1", "us-east-2", "us-west-2"] : r if r != var.region]
        content {
          region      = destination.value
          registry_id = data.aws_caller_identity.current.account_id
        }
      }
    }
  }
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-1" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-1
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-6" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-6
}
resource "aws_ecr_repository" "rosa-log-router-api-mx-central-1" {
  name     = "rosa-log-router-api"
  provider = aws.mx-central-1
}
resource "aws_ecr_repository" "rosa-log-router-api-us-east-1" {
  name     = "rosa-log-router-api"
  provider = aws.us-east-1
}
resource "aws_ecr_repository" "rosa-log-router-api-us-east-2" {
  name     = "rosa-log-router-api"
  provider = aws.us-east-2
}
resource "aws_ecr_repository" "rosa-log-router-api-us-west-2" {
  name     = "rosa-log-router-api"
  provider = aws.us-west-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-6" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-6
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-mx-central-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.mx-central-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-us-east-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.us-east-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-us-east-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.us-east-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-us-west-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.us-west-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-1" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-6" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-6
}
resource "aws_ecr_repository" "rosa-log-router-processor-mx-central-1" {
  name     = "rosa-log-router-processor"
  provider = aws.mx-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-us-east-1" {
  name     = "rosa-log-router-processor"
  provider = aws.us-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-us-east-2" {
  name     = "rosa-log-router-processor"
  provider = aws.us-east-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-us-west-2" {
  name     = "rosa-log-router-processor"
  provider = aws.us-west-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-6" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-6
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-mx-central-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.mx-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-us-east-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.us-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-us-east-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.us-east-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-us-west-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.us-west-2
}
