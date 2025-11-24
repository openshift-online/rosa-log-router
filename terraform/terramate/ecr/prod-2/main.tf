// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

data "aws_caller_identity" "current" {
}
resource "aws_ecr_replication_configuration" "ecr_replication" {
  replication_configuration {
    rule {
      dynamic "destination" {
        for_each = [for r in ["me-central-1", "me-south-1", "mx-central-1", "sa-east-1", "us-east-2", "us-west-2"] : r if r != var.region]
        content {
          region      = destination.value
          registry_id = var.prod-account-id
        }
      }
    }
  }
}
