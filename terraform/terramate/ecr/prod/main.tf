// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

data "aws_caller_identity" "current" {
}
resource "aws_ecr_replication_configuration" "ecr_replication" {
  replication_configuration {
    rule {
      dynamic "destination" {
        for_each = [for r in ["af-south-1", "ap-east-1", "ap-northeast-1", "ap-northeast-2", "ap-northeast-3", "ap-south-1", "ap-south-2", "ap-southeast-1", "ap-southeast-2", "ap-southeast-3", "ap-southeast-4", "ap-southeast-5", "ap-southeast-6", "ap-southeast-7", "ca-central-1", "ca-west-1", "eu-central-1", "eu-central-2", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-2", "eu-west-3", "il-central-1", "us-east-1"] : r if r != var.region]
        content {
          region      = destination.value
          registry_id = data.aws_caller_identity.current.account_id
        }
      }
    }
  }
}
resource "aws_ecr_registry_policy" "cross-account-replication-policy-me-central-1" {
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "testpolicy"
        Effect = "Allow"
        Principal = {
          "AWS" = "arn:aws:iam::${var.prod_2_account_id}:root"
        }
        Action = [
          "ecr:ReplicateImage",
        ]
        Resource = [
          "arn:aws:ecr:me-central-1:${data.aws_caller_identity.current.account_id}:repository/*",
        ]
      },
    ]
  })
  provider = aws.me-central-1
}
resource "aws_ecr_registry_policy" "cross-account-replication-policy-me-south-1" {
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "testpolicy"
        Effect = "Allow"
        Principal = {
          "AWS" = "arn:aws:iam::${var.prod_2_account_id}:root"
        }
        Action = [
          "ecr:ReplicateImage",
        ]
        Resource = [
          "arn:aws:ecr:me-south-1:${data.aws_caller_identity.current.account_id}:repository/*",
        ]
      },
    ]
  })
  provider = aws.me-south-1
}
resource "aws_ecr_registry_policy" "cross-account-replication-policy-mx-central-1" {
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "testpolicy"
        Effect = "Allow"
        Principal = {
          "AWS" = "arn:aws:iam::${var.prod_2_account_id}:root"
        }
        Action = [
          "ecr:ReplicateImage",
        ]
        Resource = [
          "arn:aws:ecr:mx-central-1:${data.aws_caller_identity.current.account_id}:repository/*",
        ]
      },
    ]
  })
  provider = aws.mx-central-1
}
resource "aws_ecr_registry_policy" "cross-account-replication-policy-sa-east-1" {
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "testpolicy"
        Effect = "Allow"
        Principal = {
          "AWS" = "arn:aws:iam::${var.prod_2_account_id}:root"
        }
        Action = [
          "ecr:ReplicateImage",
        ]
        Resource = [
          "arn:aws:ecr:sa-east-1:${data.aws_caller_identity.current.account_id}:repository/*",
        ]
      },
    ]
  })
  provider = aws.sa-east-1
}
resource "aws_ecr_registry_policy" "cross-account-replication-policy-us-east-2" {
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "testpolicy"
        Effect = "Allow"
        Principal = {
          "AWS" = "arn:aws:iam::${var.prod_2_account_id}:root"
        }
        Action = [
          "ecr:ReplicateImage",
        ]
        Resource = [
          "arn:aws:ecr:us-east-2:${data.aws_caller_identity.current.account_id}:repository/*",
        ]
      },
    ]
  })
  provider = aws.us-east-2
}
resource "aws_ecr_registry_policy" "cross-account-replication-policy-us-west-2" {
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "testpolicy"
        Effect = "Allow"
        Principal = {
          "AWS" = "arn:aws:iam::${var.prod_2_account_id}:root"
        }
        Action = [
          "ecr:ReplicateImage",
        ]
        Resource = [
          "arn:aws:ecr:us-west-2:${data.aws_caller_identity.current.account_id}:repository/*",
        ]
      },
    ]
  })
  provider = aws.us-west-2
}
resource "aws_ecr_repository" "rosa-log-router-api-af-south-1" {
  name     = "rosa-log-router-api"
  provider = aws.af-south-1
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-east-1" {
  name     = "rosa-log-router-api"
  provider = aws.ap-east-1
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-northeast-1" {
  name     = "rosa-log-router-api"
  provider = aws.ap-northeast-1
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-northeast-2" {
  name     = "rosa-log-router-api"
  provider = aws.ap-northeast-2
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-northeast-3" {
  name     = "rosa-log-router-api"
  provider = aws.ap-northeast-3
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-south-1" {
  name     = "rosa-log-router-api"
  provider = aws.ap-south-1
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-south-2" {
  name     = "rosa-log-router-api"
  provider = aws.ap-south-2
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-1" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-1
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-2" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-2
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-3" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-3
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-4" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-4
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-5" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-5
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-6" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-6
}
resource "aws_ecr_repository" "rosa-log-router-api-ap-southeast-7" {
  name     = "rosa-log-router-api"
  provider = aws.ap-southeast-7
}
resource "aws_ecr_repository" "rosa-log-router-api-ca-central-1" {
  name     = "rosa-log-router-api"
  provider = aws.ca-central-1
}
resource "aws_ecr_repository" "rosa-log-router-api-ca-west-1" {
  name     = "rosa-log-router-api"
  provider = aws.ca-west-1
}
resource "aws_ecr_repository" "rosa-log-router-api-eu-central-1" {
  name     = "rosa-log-router-api"
  provider = aws.eu-central-1
}
resource "aws_ecr_repository" "rosa-log-router-api-eu-central-2" {
  name     = "rosa-log-router-api"
  provider = aws.eu-central-2
}
resource "aws_ecr_repository" "rosa-log-router-api-eu-north-1" {
  name     = "rosa-log-router-api"
  provider = aws.eu-north-1
}
resource "aws_ecr_repository" "rosa-log-router-api-eu-south-1" {
  name     = "rosa-log-router-api"
  provider = aws.eu-south-1
}
resource "aws_ecr_repository" "rosa-log-router-api-eu-south-2" {
  name     = "rosa-log-router-api"
  provider = aws.eu-south-2
}
resource "aws_ecr_repository" "rosa-log-router-api-eu-west-1" {
  name     = "rosa-log-router-api"
  provider = aws.eu-west-1
}
resource "aws_ecr_repository" "rosa-log-router-api-eu-west-2" {
  name     = "rosa-log-router-api"
  provider = aws.eu-west-2
}
resource "aws_ecr_repository" "rosa-log-router-api-eu-west-3" {
  name     = "rosa-log-router-api"
  provider = aws.eu-west-3
}
resource "aws_ecr_repository" "rosa-log-router-api-il-central-1" {
  name     = "rosa-log-router-api"
  provider = aws.il-central-1
}
resource "aws_ecr_repository" "rosa-log-router-api-us-east-1" {
  name     = "rosa-log-router-api"
  provider = aws.us-east-1
}
resource "aws_ecr_repository" "rosa-log-router-api-me-central-1" {
  name     = "rosa-log-router-api"
  provider = aws.me-central-1
}
resource "aws_ecr_repository" "rosa-log-router-api-me-south-1" {
  name     = "rosa-log-router-api"
  provider = aws.me-south-1
}
resource "aws_ecr_repository" "rosa-log-router-api-mx-central-1" {
  name     = "rosa-log-router-api"
  provider = aws.mx-central-1
}
resource "aws_ecr_repository" "rosa-log-router-api-sa-east-1" {
  name     = "rosa-log-router-api"
  provider = aws.sa-east-1
}
resource "aws_ecr_repository" "rosa-log-router-api-us-east-2" {
  name     = "rosa-log-router-api"
  provider = aws.us-east-2
}
resource "aws_ecr_repository" "rosa-log-router-api-us-west-2" {
  name     = "rosa-log-router-api"
  provider = aws.us-west-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-af-south-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.af-south-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-east-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-east-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-northeast-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-northeast-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-northeast-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-northeast-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-northeast-3" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-northeast-3
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-south-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-south-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-south-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-south-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-3" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-3
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-4" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-4
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-5" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-5
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-6" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-6
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ap-southeast-7" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ap-southeast-7
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ca-central-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ca-central-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-ca-west-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.ca-west-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-eu-central-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.eu-central-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-eu-central-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.eu-central-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-eu-north-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.eu-north-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-eu-south-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.eu-south-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-eu-south-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.eu-south-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-eu-west-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.eu-west-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-eu-west-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.eu-west-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-eu-west-3" {
  name     = "rosa-log-router-authorizer"
  provider = aws.eu-west-3
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-il-central-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.il-central-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-us-east-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.us-east-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-me-central-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.me-central-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-me-south-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.me-south-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-mx-central-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.mx-central-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-sa-east-1" {
  name     = "rosa-log-router-authorizer"
  provider = aws.sa-east-1
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-us-east-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.us-east-2
}
resource "aws_ecr_repository" "rosa-log-router-authorizer-us-west-2" {
  name     = "rosa-log-router-authorizer"
  provider = aws.us-west-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-af-south-1" {
  name     = "rosa-log-router-processor"
  provider = aws.af-south-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-east-1" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-northeast-1" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-northeast-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-northeast-2" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-northeast-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-northeast-3" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-northeast-3
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-south-1" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-south-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-south-2" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-south-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-1" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-2" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-3" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-3
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-4" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-4
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-5" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-5
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-6" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-6
}
resource "aws_ecr_repository" "rosa-log-router-processor-ap-southeast-7" {
  name     = "rosa-log-router-processor"
  provider = aws.ap-southeast-7
}
resource "aws_ecr_repository" "rosa-log-router-processor-ca-central-1" {
  name     = "rosa-log-router-processor"
  provider = aws.ca-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-ca-west-1" {
  name     = "rosa-log-router-processor"
  provider = aws.ca-west-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-eu-central-1" {
  name     = "rosa-log-router-processor"
  provider = aws.eu-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-eu-central-2" {
  name     = "rosa-log-router-processor"
  provider = aws.eu-central-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-eu-north-1" {
  name     = "rosa-log-router-processor"
  provider = aws.eu-north-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-eu-south-1" {
  name     = "rosa-log-router-processor"
  provider = aws.eu-south-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-eu-south-2" {
  name     = "rosa-log-router-processor"
  provider = aws.eu-south-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-eu-west-1" {
  name     = "rosa-log-router-processor"
  provider = aws.eu-west-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-eu-west-2" {
  name     = "rosa-log-router-processor"
  provider = aws.eu-west-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-eu-west-3" {
  name     = "rosa-log-router-processor"
  provider = aws.eu-west-3
}
resource "aws_ecr_repository" "rosa-log-router-processor-il-central-1" {
  name     = "rosa-log-router-processor"
  provider = aws.il-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-us-east-1" {
  name     = "rosa-log-router-processor"
  provider = aws.us-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-me-central-1" {
  name     = "rosa-log-router-processor"
  provider = aws.me-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-me-south-1" {
  name     = "rosa-log-router-processor"
  provider = aws.me-south-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-mx-central-1" {
  name     = "rosa-log-router-processor"
  provider = aws.mx-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-sa-east-1" {
  name     = "rosa-log-router-processor"
  provider = aws.sa-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-us-east-2" {
  name     = "rosa-log-router-processor"
  provider = aws.us-east-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-us-west-2" {
  name     = "rosa-log-router-processor"
  provider = aws.us-west-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-af-south-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.af-south-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-east-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-northeast-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-northeast-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-northeast-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-northeast-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-northeast-3" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-northeast-3
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-south-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-south-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-south-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-south-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-3" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-3
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-4" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-4
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-5" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-5
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-6" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-6
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ap-southeast-7" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ap-southeast-7
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ca-central-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ca-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-ca-west-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.ca-west-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-eu-central-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.eu-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-eu-central-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.eu-central-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-eu-north-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.eu-north-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-eu-south-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.eu-south-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-eu-south-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.eu-south-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-eu-west-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.eu-west-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-eu-west-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.eu-west-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-eu-west-3" {
  name     = "rosa-log-router-processor-go"
  provider = aws.eu-west-3
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-il-central-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.il-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-us-east-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.us-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-me-central-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.me-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-me-south-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.me-south-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-mx-central-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.mx-central-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-sa-east-1" {
  name     = "rosa-log-router-processor-go"
  provider = aws.sa-east-1
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-us-east-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.us-east-2
}
resource "aws_ecr_repository" "rosa-log-router-processor-go-us-west-2" {
  name     = "rosa-log-router-processor-go"
  provider = aws.us-west-2
}
