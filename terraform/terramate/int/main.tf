// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

module "global" {
  environment  = var.environment
  org_id       = var.org_id
  project_name = var.project_name
  source       = "../../modules/global"
}
module "regional-resource-ap-northeast-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-northeast-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  org_id                            = var.org_id
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  ecr_image                         = var.ecr_image
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
  org_id                            = var.org_id
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  ecr_image                         = var.ecr_image
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
  org_id                            = var.org_id
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  ecr_image                         = var.ecr_image
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
  org_id                            = var.org_id
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  ecr_image                         = var.ecr_image
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
  org_id                            = var.org_id
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  ecr_image                         = var.ecr_image
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
  org_id                            = var.org_id
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  ecr_image                         = var.ecr_image
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
  org_id                            = var.org_id
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  ecr_image                         = var.ecr_image
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
  org_id                            = var.org_id
  include_sqs_stack                 = var.include_sqs_stack
  include_lambda_stack              = var.include_lambda_stack
  ecr_image                         = var.ecr_image
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
}
