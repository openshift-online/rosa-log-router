// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

resource "random_id" "suffix" {
  byte_length = 4
}
locals {
  random_suffix = random_id.suffix.hex
}
module "global" {
  api_auth_psk_value = var.api_auth_psk_value
  environment        = var.environment
  org_id             = var.org_id
  project_name       = var.project_name
  region             = var.region
  regions = [
    "ap-northeast-2",
    "ap-southeast-1",
    "us-east-1",
    "us-east-2",
    "us-west-2",
  ]
  source = "../../modules/global"
  tags   = var.tags
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
  include_api_stack                 = var.include_api_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
  api_auth_secret_name              = module.global.api_auth_secret_name
  authorizer_execution_role_arn     = module.global.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = module.global.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = module.global.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = module.global.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
  tags                              = var.tags
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
  include_api_stack                 = var.include_api_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
  api_auth_secret_name              = module.global.api_auth_secret_name
  authorizer_execution_role_arn     = module.global.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = module.global.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = module.global.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = module.global.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
  tags                              = var.tags
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
  include_api_stack                 = var.include_api_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
  api_auth_secret_name              = module.global.api_auth_secret_name
  authorizer_execution_role_arn     = module.global.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = module.global.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = module.global.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = module.global.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
  tags                              = var.tags
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
  include_api_stack                 = var.include_api_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
  api_auth_secret_name              = module.global.api_auth_secret_name
  authorizer_execution_role_arn     = module.global.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = module.global.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = module.global.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = module.global.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
  tags                              = var.tags
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
  include_api_stack                 = var.include_api_stack
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
  api_auth_secret_name              = module.global.api_auth_secret_name
  authorizer_execution_role_arn     = module.global.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = module.global.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = module.global.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = module.global.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
  tags                              = var.tags
}
