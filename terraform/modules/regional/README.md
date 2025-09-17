# Terraform Regional Infrastructure

This directory contains pure Terraform configurations for deploying the multi-tenant logging pipeline regional infrastructure. This is a complete Terraform conversion of the CloudFormation templates in `cloudformation/regional/`.

## Overview

The regional infrastructure consists of modular components:
- **Core Infrastructure**: S3, DynamoDB, KMS, SNS, and IAM resources
- **SQS Stack**: Optional SQS queue and dead letter queue for message processing
- **Lambda Stack**: Optional container-based Lambda function for serverless processing  
- **API Stack**: Optional API Gateway and Lambda functions for tenant management

## Architecture

This Terraform configuration uses a pure module-based approach:
- **Main orchestration**: `main.tf` uses native Terraform modules
- **Module organization**: Each component is a separate Terraform module under `modules/`
- **Conditional deployment**: Uses `count` for optional stacks
- **Native Terraform**: All resources defined using Terraform HCL

## Files Structure

```
terraform/regional/
├── main.tf                          # Main orchestration using modules
├── variables.tf                     # Input variables with validation
├── outputs.tf                       # Output values
├── README.md                        # This file
└── modules/                         # Terraform modules
    ├── core-infrastructure/
    │   ├── main.tf                  # Core infrastructure resources
    │   ├── variables.tf             # Module variables
    │   └── outputs.tf               # Module outputs
    ├── sqs-stack/
    │   ├── main.tf                  # SQS queue resources
    │   ├── variables.tf             # Module variables  
    │   └── outputs.tf               # Module outputs
    ├── lambda-stack/
    │   ├── main.tf                  # Lambda function resources
    │   ├── variables.tf             # Module variables
    │   └── outputs.tf               # Module outputs
```

## Usage

### Basic Deployment

```bash
# Initialize Terraform
terraform init

# Plan deployment with core infrastructure only
terraform plan -var="central_log_distribution_role_arn=arn:aws:iam::ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX"

# Deploy infrastructure
terraform apply -var="central_log_distribution_role_arn=arn:aws:iam::ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX"
```

### Advanced Deployment

```bash
# Deploy with all optional stacks  
terraform apply \
  -var="aws_region=us-west-2" \
  -var="environment=stage" \
  -var="central_log_distribution_role_arn=arn:aws:iam::ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX" \
  -var="lambda_execution_role_arn=arn:aws:iam::ACCOUNT:role/hcp-log-lambda-execution-role-XXXXXXXX" \
  -var="include_sqs_stack=true" \
  -var="include_lambda_stack=true" \
  -var="ecr_image_uri=123456789012.dkr.ecr.us-east-1.amazonaws.com/log-processor:latest" 
```

## Variables

### Required Variables
- `central_log_distribution_role_arn` - ARN of the global central log distribution role
- `lambda_execution_role_arn` - ARN of the global Lambda execution role (required if include_lambda_stack=true)

### Optional Variables
- `aws_region` - AWS region for deployment (default: null, uses current provider region)
- `environment` - Environment name (default: "int")
- `project_name` - Project name (default: "hcp-log")
- `include_sqs_stack` - Deploy SQS stack (default: true)
- `include_lambda_stack` - Deploy Lambda stack (default: false)
- `ecr_image_uri` - ECR container image URI (required if include_lambda_stack=true)
- `s3_delete_after_days` - S3 lifecycle deletion (default: 7)
- `enable_s3_encryption` - Enable S3 KMS encryption (default: true)

## Deployment Patterns

### Integration Environment
```hcl
module "regional_int" {
  source = "./modules/regional"
  
  aws_region  = "us-east-1"
  environment = "int"
  
  central_log_distribution_role_arn = var.global_central_role_arn
  lambda_execution_role_arn         = var.global_lambda_role_arn
  
  include_sqs_stack    = true
  include_lambda_stack = false  # Use polling for integration testing
  
  s3_delete_after_days = 1      # Quick cleanup for testing
  enable_s3_encryption = false  # Reduce complexity for testing
}
```

### Staging Environment
```hcl
module "regional_stage" {
  source = "./modules/regional"
  
  aws_region  = "us-west-2"
  environment = "stage"
  
  central_log_distribution_role_arn = var.global_central_role_arn
  lambda_execution_role_arn         = var.global_lambda_role_arn
  
  include_sqs_stack    = true
  include_lambda_stack = true
  ecr_image_uri       = "123456789012.dkr.ecr.us-east-1.amazonaws.com/log-processor:stage"
  
  s3_delete_after_days = 7
  enable_s3_encryption = true
}
```

### Production Environment  
```hcl
module "regional_prod" {
  source = "./modules/regional"
  
  aws_region  = "eu-west-1"
  environment = "prod"
  
  central_log_distribution_role_arn = var.global_central_role_arn
  lambda_execution_role_arn         = var.global_lambda_role_arn
  
  include_sqs_stack    = true
  include_lambda_stack = true
  ecr_image_uri       = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/log-processor:v1.2.3"
  
  s3_delete_after_days = 30     # Longer retention for production
  enable_s3_encryption = true   # Required for production
}
```

## Module Dependencies

This module requires global IAM resources to be deployed first. It references:

- **Central Log Distribution Role**: ARN from global module for cross-account access
- **Lambda Execution Role**: ARN from global module for Lambda function execution  

### Typical Usage Pattern
```hcl
# 1. Deploy global resources first
module "global_iam" {
  source = "./modules/global"
  
  project_name  = "hcp-log"
  random_suffix = "abcd1234"
}

# 2. Then deploy regional resources
module "regional_us_east_1" {
  source = "./modules/regional"
  
  aws_region  = "us-east-1"
  environment = "prod"
  
  # Reference global IAM roles
  central_log_distribution_role_arn = module.global_iam.central_log_distribution_role_arn
  lambda_execution_role_arn         = module.global_iam.lambda_execution_role_arn
  
  include_sqs_stack    = true
  include_lambda_stack = true
  ecr_image_uri       = var.ecr_image_uri
}
```

## Single Region Deployment Patterns

### Core Infrastructure Only
```bash
terraform apply \
  -var="environment=int" \
  -var="include_sqs_stack=false" \
  -var="include_lambda_stack=false" \
  -var="central_log_distribution_role_arn=YOUR_ROLE_ARN" \
  -var="lambda_execution_role_arn=YOUR_LAMBDA_ROLE_ARN"
```

### With SQS for External Processing
```bash
terraform apply \
  -var="environment=stage" \
  -var="include_sqs_stack=true" \
  -var="include_lambda_stack=false" \
  -var="central_log_distribution_role_arn=YOUR_ROLE_ARN" \
  -var="lambda_execution_role_arn=YOUR_LAMBDA_ROLE_ARN"
```

### Full Serverless with Lambda
```bash
terraform apply \
  -var="environment=prod" \
  -var="include_sqs_stack=true" \
  -var="include_lambda_stack=true" \
  -var="ecr_image_uri=YOUR_ECR_URI" \
  -var="central_log_distribution_role_arn=YOUR_ROLE_ARN" \
  -var="lambda_execution_role_arn=YOUR_LAMBDA_ROLE_ARN"
```

## Module Details

### Core Infrastructure Module
**Path**: `modules/core-infrastructure/`
**Resources**:
- S3 bucket with encryption, lifecycle, and notifications
- DynamoDB table with GSIs and encryption  
- KMS key for encryption (conditional)
- SNS topic and policies
- IAM roles for S3 writer and log processor
- CloudWatch log group

### SQS Stack Module  
**Path**: `modules/sqs-stack/`
**Resources**:
- SQS queue with dead letter queue
- SQS queue policy for SNS
- SNS subscription to SQS

### Lambda Stack Module
**Path**: `modules/lambda-stack/`
**Resources**:
- Lambda function (container-based)
- Lambda execution role with policies
- CloudWatch log group
- SQS event source mapping


## Outputs

### Core Infrastructure
- `central_logging_bucket_name` - S3 bucket name
- `tenant_config_table_name` - DynamoDB table name
- `log_delivery_topic_arn` - SNS topic ARN
- `regional_log_processor_role_arn` - IAM role ARN

### Optional Components
- `log_delivery_queue_arn` - SQS queue ARN (if SQS stack deployed)
- `log_delivery_queue_url` - SQS queue URL (if SQS stack deployed)
- `log_distributor_function_name` - Lambda function name (if Lambda stack deployed)
- `log_distributor_function_arn` - Lambda function ARN (if Lambda stack deployed)
- `api_endpoint` - API Gateway URL (if API stack deployed)
- `api_id` - API Gateway ID (if API stack deployed)

## Migration from CloudFormation

If migrating from existing CloudFormation stacks:

### 1. Import Existing Resources
```bash
# Import S3 bucket
terraform import module.core_infrastructure.aws_s3_bucket.central_logging_bucket existing-bucket-name

# Import DynamoDB table
terraform import module.core_infrastructure.aws_dynamodb_table.tenant_config_table existing-table-name

# Import IAM roles
terraform import module.core_infrastructure.aws_iam_role.regional_log_processor_role existing-role-name
```

### 2. State Planning
```bash
# Review what Terraform plans to change
terraform plan -detailed-exitcode

# Apply only if no changes are planned
terraform apply
```

### 3. Gradual Migration Strategy
1. **Core first**: Migrate core infrastructure module
2. **SQS next**: Add SQS stack if needed
3. **Lambda/API**: Add remaining optional stacks
4. **Cleanup**: Remove old CloudFormation stacks

## Best Practices

### State Management
```bash
# Configure remote state backend
terraform init -backend-config="bucket=my-terraform-state" \
               -backend-config="key=regional/terraform.tfstate" \
               -backend-config="region=us-east-1"
```

### Variable Management
```bash
# Use terraform.tfvars file
cat > terraform.tfvars <<EOF
environment = "production"
project_name = "hcp-log"
central_log_distribution_role_arn = "arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234"
include_sqs_stack = true
include_lambda_stack = true
ecr_image_uri = "123456789012.dkr.ecr.us-east-1.amazonaws.com/log-processor:latest"
EOF

terraform apply -var-file="terraform.tfvars"
```

### Workspace Management
```bash
# Use workspaces for different environments
terraform workspace new production
terraform workspace new staging
terraform workspace new development

terraform workspace select production
terraform apply
```

## Troubleshooting

### Common Issues

1. **Module not found**: Ensure you're running terraform commands from the `terraform/regional/` directory
2. **Variable validation errors**: Check that required variables match the expected patterns
3. **Resource conflicts**: Ensure resource names don't conflict with existing infrastructure
4. **IAM permissions**: Verify Terraform execution role has necessary permissions

### Debugging Commands

```bash
# Validate configuration
terraform validate

# Format configuration
terraform fmt -recursive

# Show dependency graph
terraform graph | dot -Tpng > graph.png

# Debug with detailed logging
TF_LOG=DEBUG terraform apply

# Show current state
terraform show

# Refresh state from actual infrastructure  
terraform refresh
```

### Module Development

```bash
# Validate individual modules
cd modules/core-infrastructure
terraform init
terraform validate
terraform plan

# Format all modules
terraform fmt -recursive modules/
```

## Security Considerations

- **State encryption**: Use encrypted S3 backend for state storage
- **Variable sensitivity**: Mark sensitive variables in module definitions
- **IAM least privilege**: Use minimal required permissions
- **Resource encryption**: All resources use encryption by default
- **Network security**: API Gateway uses REGIONAL endpoints

## Performance Optimization

- **Module caching**: Terraform caches module downloads locally
- **Parallel execution**: Terraform applies resources in parallel when possible
- **Resource targeting**: Use `-target` for specific resource updates
- **State locking**: DynamoDB table prevents concurrent modifications

## Integration with CI/CD

```yaml
# Example GitHub Actions workflow
name: Terraform Regional Infrastructure
on:
  push:
    branches: [main]
    paths: ['terraform/regional/**']

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: hashicorp/setup-terraform@v1
        with:
          terraform_version: 1.5.0
      
      - name: Terraform Init
        run: terraform init
        working-directory: terraform/regional
      
      - name: Terraform Plan
        run: terraform plan
        working-directory: terraform/regional
      
      - name: Terraform Apply
        if: github.ref == 'refs/heads/main'
        run: terraform apply -auto-approve
        working-directory: terraform/regional
```

For complete deployment instructions and integration with other infrastructure components, refer to the main project documentation in `CLAUDE.md`.