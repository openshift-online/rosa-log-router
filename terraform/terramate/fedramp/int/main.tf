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
    "us-gov-west-1",
    "us-gov-east-1",
  ]
  source = "../../modules/global"
}
module "regional-resource-us-gov-west-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.us-gov-west-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  processor_image                   = var.processor_image
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
  api_auth_secret_name              = module.global.api_auth_secret_name
  authorizer_execution_role_arn     = module.global.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = module.global.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = module.global.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = module.global.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
}
module "regional-resource-us-gov-east-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.us-gov-east-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  random_suffix                     = local.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = module.global.central_log_distribution_role_arn
  processor_image                   = var.processor_image
  lambda_execution_role_arn         = module.global.lambda_execution_role_arn
  api_auth_secret_name              = module.global.api_auth_secret_name
  authorizer_execution_role_arn     = module.global.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = module.global.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = module.global.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = module.global.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
}
