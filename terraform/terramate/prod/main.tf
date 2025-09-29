// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

resource "random_id" "suffix" {
  byte_length = 4
}
locals {
  random_suffix = random_id.suffix.hex
}
module "global" {
  environment  = var.environment
  org_id       = var.org_id
  project_name = var.project_name
  source       = "../../modules/global"
}
module "regional-resource-af-south-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.af-south-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-east-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-east-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-northeast-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-northeast-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-northeast-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-northeast-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-northeast-3" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-northeast-3
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-south-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-south-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-south-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-south-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-southeast-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-southeast-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-southeast-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-southeast-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-southeast-3" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-southeast-3
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-southeast-4" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-southeast-4
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-southeast-5" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-southeast-5
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ap-southeast-7" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-southeast-7
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ca-central-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ca-central-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-ca-west-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ca-west-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-eu-central-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.eu-central-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-eu-central-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.eu-central-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-eu-north-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.eu-north-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-eu-south-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.eu-south-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-eu-south-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.eu-south-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-eu-west-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.eu-west-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-eu-west-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.eu-west-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-eu-west-3" {
  source = "../../modules/regional"
  providers = {
    aws = aws.eu-west-3
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-il-central-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.il-central-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-me-central-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.me-central-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-me-south-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.me-south-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-mx-central-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.mx-central-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-sa-east-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.sa-east-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-us-east-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.us-east-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-us-east-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.us-east-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
module "regional-resource-us-west-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.us-west-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
