// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

module "regional-resource-ap-east-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-east-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  random_suffix                     = var.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = var.central_log_distribution_role_arn
  processor_image                   = var.processor_image
  lambda_execution_role_arn         = var.lambda_execution_role_arn
  api_auth_secret_name              = var.api_auth_secret_name
  authorizer_execution_role_arn     = var.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = var.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = var.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = var.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
}
module "regional-resource-ap-northeast-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-northeast-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  random_suffix                     = var.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = var.central_log_distribution_role_arn
  processor_image                   = var.processor_image
  lambda_execution_role_arn         = var.lambda_execution_role_arn
  api_auth_secret_name              = var.api_auth_secret_name
  authorizer_execution_role_arn     = var.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = var.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = var.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = var.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
}
module "regional-resource-ap-south-1" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-south-1
  }
  project_name                      = var.project_name
  environment                       = var.environment
  random_suffix                     = var.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = var.central_log_distribution_role_arn
  processor_image                   = var.processor_image
  lambda_execution_role_arn         = var.lambda_execution_role_arn
  api_auth_secret_name              = var.api_auth_secret_name
  authorizer_execution_role_arn     = var.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = var.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = var.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = var.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
}
module "regional-resource-ap-south-2" {
  source = "../../modules/regional"
  providers = {
    aws = aws.ap-south-2
  }
  project_name                      = var.project_name
  environment                       = var.environment
  random_suffix                     = var.random_suffix
  s3_delete_after_days              = var.s3_delete_after_days
  enable_s3_encryption              = var.enable_s3_encryption
  central_log_distribution_role_arn = var.central_log_distribution_role_arn
  processor_image                   = var.processor_image
  lambda_execution_role_arn         = var.lambda_execution_role_arn
  api_auth_secret_name              = var.api_auth_secret_name
  authorizer_execution_role_arn     = var.authorizer_execution_role_arn
  authorizer_image                  = var.authorizer_image
  api_execution_role_arn            = var.api_execution_role_arn
  api_image                         = var.api_image
  api_gateway_authorizer_role_arn   = var.api_gateway_authorizer_role_arn
  api_gateway_cloudwatch_role_arn   = var.api_gateway_cloudwatch_role_arn
  route53_zone_id                   = var.route53_zone_id
}
