variable "replicate_regions" {
  description = "List of AWS regions to replicate ECR repositories to"
  type        = list(string)
  default     = []
}

data "aws_caller_identity" "current" {}

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
