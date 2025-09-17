# Global IAM Module

This Terraform module creates global IAM resources for the multi-tenant logging infrastructure. It includes roles for central log distribution, Vector S3 writing, and Lambda execution. Originally converted from CloudFormation templates but now expanded with additional capabilities.

## Resources Created

### Central Log Distribution Role
- **AWS IAM Role**: `ROSA-CentralLogDistributionRole-{random_suffix}` - Central role for cross-account access (random suffix generated automatically)
- **AWS IAM Role Policy**: Cross-account assume role policy with permissions for:
  - STS assume role with external ID validation
  - S3 source bucket read access (hcp-log-* buckets)
  - S3 target bucket write access (all buckets for cross-region delivery)
  - KMS encryption/decryption permissions

### Central S3 Writer Role
- **AWS IAM Role**: `{project_name}-central-s3-writer-role` - Role for Vector agents to write to S3 buckets
- **AWS IAM Role Policy**: S3 write permissions for:
  - S3 object write access (`s3:PutObject`, `s3:PutObjectAcl`) on project buckets
  - S3 bucket access (`s3:ListBucket`, `s3:GetBucketLocation`) on project buckets
  - KMS encryption/decryption for S3 operations across all regions

### Lambda Execution Role (for Log Processing)
- **AWS IAM Role**: `{project_name}-lambda-execution-role` - Role for Lambda functions to process logs
- **AWS IAM Role Policy**: Log processing permissions for:
  - DynamoDB access (`dynamodb:GetItem`, `dynamodb:Query`, `dynamodb:BatchGetItem`) on project tables across all regions
  - S3 read access (`s3:GetObject`, `s3:GetBucketLocation`, `s3:ListBucket`) on project buckets across all regions
  - Assume central log distribution role (`sts:AssumeRole`)
  - KMS decryption for encrypted S3 objects (`kms:Decrypt`, `kms:DescribeKey`)

## Usage

```hcl
module "global_iam" {
  source = "./modules/global"
  
  project_name = "hcp-log"
}
```

**Note**: The `random_suffix` is now generated automatically within the module using the `random` provider.

## Variables

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| project_name | Name of the project for resource naming | `string` | `"hcp-log"` | no |

**Note**: The `random_suffix` is generated automatically within the module and no longer needs to be provided as an input.

## Outputs

| Name | Description |
|------|-------------|
| central_log_distribution_role_arn | ARN of the central log distribution role for cross-account access |
| central_log_distribution_role_name | Name of the central log distribution role |
| central_s3_writer_role_arn | ARN of the central S3 writer role for Vector agents |
| central_s3_writer_role_name | Name of the central S3 writer role |
| vector_assume_role_policy_arn | ARN of the managed policy for Vector agents to assume S3 writer role |
| random_suffix | Random suffix used for resource naming |

## IAM Permissions

### Central Log Distribution Role

#### Inline Policy Permissions
- **Cross-account role assumption**: `sts:AssumeRole` on `arn:aws:iam::*:role/CustomerLogDistribution-*` with external ID validation
- **Source S3 access**: `s3:GetObject`, `s3:GetBucketLocation`, `s3:ListBucket` on `hcp-log-*` buckets
- **Target S3 access**: `s3:PutObject` on all S3 buckets for cross-region delivery
- **KMS operations**: `kms:Decrypt`, `kms:DescribeKey`, `kms:GenerateDataKey` on all KMS keys

#### Trust Policy
The role can be assumed by:
- The current AWS account root user
- AWS Lambda service

### Central S3 Writer Role (for Vector Agents)

#### Inline Policy Permissions
- **S3 object write**: `s3:PutObject`, `s3:PutObjectAcl` on `{project_name}-*/*` buckets
- **S3 bucket access**: `s3:ListBucket`, `s3:GetBucketLocation` on `{project_name}-*` buckets  
- **KMS operations**: `kms:Decrypt`, `kms:GenerateDataKey` on all KMS keys for S3 operations (all regions)

#### Trust Policy
The role can be assumed by:
- The current AWS account root user

### Lambda Execution Role (for Log Processing)

#### Managed Policy Attachments
- `arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole`
- `arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole`

#### Inline Policy Permissions
- **DynamoDB access**: `dynamodb:GetItem`, `dynamodb:Query`, `dynamodb:BatchGetItem` on all project tables across regions
- **S3 read access**: `s3:GetObject`, `s3:GetBucketLocation`, `s3:ListBucket` on project buckets across regions
- **Central role assumption**: `sts:AssumeRole` on the central log distribution role
- **KMS operations**: `kms:Decrypt`, `kms:DescribeKey` on all KMS keys

#### Trust Policy
The role can be assumed by:
- AWS Lambda service

### Vector Assume Role Policy
Standalone managed policy that grants:
- **Role assumption**: `sts:AssumeRole` on the central S3 writer role
- **Usage**: Attach this policy to Vector service accounts or IAM users that need to assume the S3 writer role

## Tags

All resources are tagged with:
- `Project`: Value from `project_name` variable
- `Environment`: `global`
- `ManagedBy`: `terraform`
- `StackType`: `global`

## Migration from CloudFormation

This module was originally converted from the CloudFormation template `cloudformation/global/central-log-distribution-role.yaml` but has been significantly expanded. Key differences and enhancements:

### Original CloudFormation Conversion
1. **Resource names**: Terraform uses underscores instead of CloudFormation's PascalCase
2. **Policy documents**: Uses `jsonencode()` for inline JSON policies
3. **Data sources**: Uses `data.aws_caller_identity.current` instead of CloudFormation's `AWS::AccountId`
4. **Validation**: Terraform variable validation replaces CloudFormation's `AllowedPattern`
5. **Policy attachments**: Uses separate `aws_iam_role_policy_attachment` resources instead of deprecated `managed_policy_arns`

### Additional Enhancements
1. **Central S3 Writer Role**: Moved from regional to global for cross-region consistency
2. **Lambda Execution Role**: Moved from regional to global for centralized management
3. **Vector Assume Role Policy**: New managed policy for Vector agent integration
4. **Cross-region permissions**: Enhanced policies work across all AWS regions
5. **Modular design**: Supports multi-region deployments with single global roles

## Requirements

- Terraform >= 0.14
- AWS Provider >= 3.0