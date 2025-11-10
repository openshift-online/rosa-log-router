# Local development Terraform configuration using existing modules
# Simulates multi-account setup with LocalStack

locals {
  project_name = "multi-tenant-logging"
  environment  = "int"  # Must be one of: prod, stage, int (per module validation)

  common_tags = {
    Environment = "int-localstack"
    ManagedBy   = "terraform-localstack"
    Project     = local.project_name
  }
}

##############################################################################
# CENTRAL ACCOUNT - Uses existing modules!
##############################################################################

# ECR repository for Lambda container images
resource "aws_ecr_repository" "lambda_processor" {
  provider = aws.central
  name     = "${local.project_name}-${local.environment}-log-processor"

  image_scanning_configuration {
    scan_on_push = false  # Disable for LocalStack
  }

  tags = local.common_tags
}

# Central account role for cross-account access (create this first, needed by core-infrastructure)
resource "aws_iam_role" "central_log_distribution_role" {
  provider = aws.central
  name     = "ROSA-CentralLogDistributionRole-12345678"  # Matches expected naming pattern

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.common_tags
}

# Policy allowing central role to assume customer roles
resource "aws_iam_role_policy" "central_assume_customer_roles" {
  provider = aws.central
  name     = "AssumeCustomerRoles"
  role     = aws_iam_role.central_log_distribution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "sts:AssumeRole"
      Resource = [
        "arn:aws:iam::${local.customer1_account_id}:role/*",
        "arn:aws:iam::${local.customer2_account_id}:role/*"
      ]
    }]
  })
}

# Use your existing core infrastructure module
module "central_core_infrastructure" {
  source = "../modules/regional/modules/core-infrastructure"

  providers = {
    aws = aws.central
  }

  project_name                      = local.project_name
  environment                       = local.environment
  random_suffix                     = "local"
  enable_s3_encryption              = false  # Disable KMS for local testing
  s3_delete_after_days              = 7
  central_log_distribution_role_arn = aws_iam_role.central_log_distribution_role.arn
  tags                              = local.common_tags
}

# Use your existing SQS stack module
module "central_sqs_stack" {
  source = "../modules/regional/modules/sqs-stack"

  providers = {
    aws = aws.central
  }

  project_name           = local.project_name
  environment            = local.environment
  log_delivery_topic_arn = module.central_core_infrastructure.log_delivery_topic_arn
  tags                   = local.common_tags
}

# Central account IAM role for Lambda execution
resource "aws_iam_role" "central_lambda_execution_role" {
  provider = aws.central
  name     = "${local.project_name}-${local.environment}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "central_lambda_basic" {
  provider   = aws.central
  role       = aws_iam_role.central_lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "central_lambda_sqs" {
  provider   = aws.central
  role       = aws_iam_role.central_lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
}

resource "aws_iam_role_policy" "central_lambda_log_processor_policy" {
  provider = aws.central
  name     = "LogProcessorPolicy"
  role     = aws_iam_role.central_lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # DynamoDB access for tenant configurations
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:BatchGetItem"
        ]
        Resource = "arn:aws:dynamodb:*:${local.central_account_id}:table/${local.project_name}-*"
      },
      # S3 access for reading log files
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetBucketLocation",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::*${local.project_name}*",
          "arn:aws:s3:::*${local.project_name}*/*"
        ]
      },
      # Assume the central log distribution role
      {
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = aws_iam_role.central_log_distribution_role.arn
      },
      # KMS access for encrypted S3 buckets
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = "*"
      },
      # SQS access
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = "arn:aws:sqs:*:${local.central_account_id}:${local.project_name}-*"
      },
      # CloudWatch metrics
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      }
    ]
  })
}

# Lambda function - supports both zip file and container image
# Container images require LocalStack Pro
resource "aws_lambda_function" "central_log_distributor" {
  count    = var.deploy_lambda ? 1 : 0
  provider = aws.central

  function_name = "${local.project_name}-${local.environment}-log-distributor"
  role          = aws_iam_role.central_lambda_execution_role.arn

  # Conditional: use container image or zip file
  package_type = var.use_container_image ? "Image" : "Zip"

  # For zip deployment
  filename         = var.use_container_image ? null : var.lambda_zip_path
  source_code_hash = var.use_container_image ? null : filebase64sha256(var.lambda_zip_path)
  handler          = var.use_container_image ? null : "log_processor.lambda_handler"
  runtime          = var.use_container_image ? null : "python3.13"

  # For container image deployment
  image_uri = var.use_container_image ? "${aws_ecr_repository.lambda_processor.repository_url}:${var.lambda_image_tag}" : null

  timeout     = 300
  memory_size = 512

  environment {
    variables = {
      TENANT_CONFIG_TABLE               = module.central_core_infrastructure.tenant_config_table_name
      MAX_BATCH_SIZE                    = "1000"
      RETRY_ATTEMPTS                    = "3"
      CENTRAL_LOG_DISTRIBUTION_ROLE_ARN = aws_iam_role.central_log_distribution_role.arn
      SQS_QUEUE_URL                     = module.central_sqs_stack.log_delivery_queue_url
      EXECUTION_MODE                    = "lambda"
      LOG_LEVEL                         = "DEBUG"
    }
  }

  tags = local.common_tags
}

# Event source mapping: SQS -> Lambda (from your lambda-stack module pattern)
resource "aws_lambda_event_source_mapping" "central_sqs_to_lambda" {
  count    = var.deploy_lambda ? 1 : 0
  provider = aws.central

  event_source_arn                   = module.central_sqs_stack.log_delivery_queue_arn
  function_name                      = aws_lambda_function.central_log_distributor[0].arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

##############################################################################
# CUSTOMER ACCOUNTS - Simulating customer-side infrastructure
##############################################################################

# Customer 1: ACME Corp (Account 222222222222)
module "customer1_acme_corp" {
  source = "./modules/customer-account"

  providers = {
    aws = aws.customer1
  }

  customer_name        = "acme-corp"
  account_id           = local.customer1_account_id
  central_account_id   = local.central_account_id
  project_name         = local.project_name
  environment          = local.environment
  tags                 = local.common_tags
}

# Customer 2: Globex Industries (Account 333333333333)
module "customer2_globex" {
  source = "./modules/customer-account"

  providers = {
    aws = aws.customer2
  }

  customer_name        = "globex-industries"
  account_id           = local.customer2_account_id
  central_account_id   = local.central_account_id
  project_name         = local.project_name
  environment          = local.environment
  tags                 = local.common_tags
}

##############################################################################
# TENANT CONFIGURATIONS - In central account DynamoDB
##############################################################################

# Tenant 1: ACME Corp - S3 delivery to their account
resource "aws_dynamodb_table_item" "tenant_acme_corp_s3" {
  provider   = aws.central
  table_name = module.central_core_infrastructure.tenant_config_table_name
  hash_key   = "tenant_id"
  range_key  = "type"

  item = jsonencode({
    tenant_id                  = { S = "acme-corp" }
    type                       = { S = "s3" }
    enabled                    = { BOOL = true }
    bucket_name                = { S = module.customer1_acme_corp.log_delivery_bucket_name }
    bucket_prefix              = { S = "logs/" }
    target_region              = { S = "us-east-1" }
    log_distribution_role_arn  = { S = module.customer1_acme_corp.log_distribution_role_arn }
    desired_logs               = { L = [
      { S = "payment-service" },
      { S = "user-database" }
    ]}
  })
}

# Tenant 2: Globex Industries - S3 delivery to their account
resource "aws_dynamodb_table_item" "tenant_globex_s3" {
  provider   = aws.central
  table_name = module.central_core_infrastructure.tenant_config_table_name
  hash_key   = "tenant_id"
  range_key  = "type"

  item = jsonencode({
    tenant_id                  = { S = "globex-industries" }
    type                       = { S = "s3" }
    enabled                    = { BOOL = true }
    bucket_name                = { S = module.customer2_globex.log_delivery_bucket_name }
    bucket_prefix              = { S = "platform-logs/" }
    target_region              = { S = "us-east-1" }
    log_distribution_role_arn  = { S = module.customer2_globex.log_distribution_role_arn }
  })
}

# Tenant 2: Globex Industries - CloudWatch delivery to their account
resource "aws_dynamodb_table_item" "tenant_globex_cloudwatch" {
  provider   = aws.central
  table_name = module.central_core_infrastructure.tenant_config_table_name
  hash_key   = "tenant_id"
  range_key  = "type"

  item = jsonencode({
    tenant_id                  = { S = "globex-industries" }
    type                       = { S = "cloudwatch" }
    enabled                    = { BOOL = true }
    log_group_name             = { S = module.customer2_globex.cloudwatch_log_group_name }
    target_region              = { S = "us-east-1" }
    log_distribution_role_arn  = { S = module.customer2_globex.log_distribution_role_arn }
  })
}

# Test tenant - delivers to central account bucket
resource "aws_dynamodb_table_item" "tenant_test" {
  provider   = aws.central
  table_name = module.central_core_infrastructure.tenant_config_table_name
  hash_key   = "tenant_id"
  range_key  = "type"

  item = jsonencode({
    tenant_id     = { S = "test-tenant" }
    type          = { S = "s3" }
    enabled       = { BOOL = true }
    bucket_name   = { S = module.central_core_infrastructure.central_logging_bucket_name }
    bucket_prefix = { S = "test/" }
    target_region = { S = "us-east-1" }
  })
}
