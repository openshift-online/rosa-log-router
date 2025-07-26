# CloudFormation Multi-Tenant Logging Infrastructure

This directory contains CloudFormation templates for deploying the multi-tenant logging infrastructure.

## Architecture Overview

The infrastructure implements a "Centralized Ingestion, Decentralized Delivery" architecture using a modular nested CloudFormation stack approach:

1. **Main Stack** (`main.yaml`) - Orchestrates nested stacks with conditional deployment
2. **Core Infrastructure** (`core-infrastructure.yaml`) - S3, DynamoDB, KMS, IAM, and native S3 notifications
3. **SQS Stack** (`sqs-stack.yaml`) - Optional SQS queue and DLQ for message processing
4. **Lambda Stack** (`lambda-stack.yaml`) - Optional container-based Lambda functions for log processing

### Recent Updates (January 2025)

**Major Architectural Improvements:**
- **Container-Based Lambda** - Unified log processor using ECR container images with multi-mode execution
- **Modular Deployment** - Optional SQS and Lambda stacks with `--include-sqs` and `--include-lambda` flags
- **Native S3 Notifications** - Replaced custom Lambda functions with native `AWS::S3::Bucket NotificationConfiguration`
- **Eliminated Circular Dependencies** - Deterministic bucket naming with deploy script parameter generation
- **Simplified Infrastructure** - Reduced complexity with container-based approach
- **Enhanced Deployment** - Improved deploy script with modular stack selection and ECR integration
- **Vector Integration in Lambda** - Log processor spawns Vector subprocess for reliable CloudWatch delivery
- **Improved Error Handling** - Lambda returns `batchItemFailures` for proper SQS retry behavior
- **Enhanced IAM Security** - Double-hop role assumption with ExternalId validation

**Previous Major Changes:**
- **Removed Kinesis Data Firehose** - Vector agents now write directly to S3
- **Added CentralS3WriterRole** - Secure cross-account S3 access from Vector
- **Updated Vector Configuration** - Using aws_s3 sink instead of aws_kinesis_firehose
- **Modified Lambda Processing** - Parsing S3 key format: `customer_id/cluster_id/application/pod_name/`
- **Integrated S3 Events** - S3 event notifications with SNS/SQS infrastructure

**Infrastructure Quality Improvements:**
- Fixed IAM policy S3 ARN format errors (using `.Arn` attribute instead of bucket names)
- Updated nested stack template URLs to use legacy S3 format required by CloudFormation
- Removed invalid `AWS::DynamoDB::Item` resources from upstream changes
- Fixed DynamoDB SSE configuration to include required `SSEType` parameter
- Updated deployment script to properly honor `AWS_PROFILE` and `AWS_REGION` environment variables

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate permissions
- S3 bucket for storing CloudFormation templates
- Valid AWS account with necessary service quotas

### Deployment Options

The infrastructure supports three deployment patterns to accommodate different processing requirements:

#### **Core Infrastructure Only**
Deploy only S3, DynamoDB, SNS, and IAM resources. Suitable for external log processing systems.

```bash
cd cloudformation/
./deploy.sh -b your-cloudformation-templates-bucket
```

#### **Core + SQS Processing**
Add SQS queue and DLQ for message buffering. Enables external applications to poll for log processing events.

```bash
cd cloudformation/
./deploy.sh -b your-cloudformation-templates-bucket --include-sqs
```

#### **Full Container-Based Processing**
Complete serverless processing using container-based Lambda functions with ECR image deployment.

```bash
# First, build and push containers to ECR
cd ../container/
# Build collector container first (contains Vector)
podman build -f Containerfile.collector -t log-collector:latest .
# Build processor container (includes Vector from collector)
podman build -f Containerfile.processor -t log-processor:latest .

# Push to ECR
aws ecr get-login-password --region YOUR_AWS_REGION | podman login --username AWS --password-stdin AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com
podman tag log-processor:latest AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com/log-processor:latest
podman push AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com/log-processor:latest

# Deploy with Lambda processing
cd ../cloudformation/
./deploy.sh -b your-templates-bucket --include-sqs --include-lambda --ecr-image-uri AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com/log-processor:latest
```

#### **Environment-Specific Deployment**
```bash
# Development environment with SQS only
./deploy.sh -e development -b your-templates-bucket --include-sqs

# Staging environment with full Lambda processing
./deploy.sh -e staging -b your-templates-bucket --include-sqs --include-lambda --ecr-image-uri ECR_IMAGE_URI

# Production with custom parameters
./deploy.sh -e production -p my-logging-project -r us-west-2 -b my-templates-bucket --include-sqs --include-lambda --ecr-image-uri ECR_IMAGE_URI

# Using environment variables for AWS configuration
export AWS_PROFILE=your-profile
export AWS_REGION=YOUR_AWS_REGION
./deploy.sh -b your-cloudformation-templates-bucket --include-sqs --include-lambda --ecr-image-uri ECR_IMAGE_URI
```

### Validate Templates Only

```bash
# Validate all templates without deploying
./deploy.sh -b your-templates-bucket --validate-only

# Dry run to see what would be deployed
./deploy.sh -b your-templates-bucket --dry-run
```

## File Structure

```
cloudformation/
├── main.yaml                          # Main orchestration template with conditional stacks
├── core-infrastructure.yaml           # S3, DynamoDB, KMS, IAM, native S3 notifications
├── sqs-stack.yaml                     # Optional SQS queue and DLQ for message processing
├── lambda-stack.yaml                  # Optional container-based Lambda functions
├── customer-log-distribution-role.yaml # Customer account template
├── deploy.sh                          # Enhanced deployment script with modular options
└── README.md                          # This file
```

### Key Implementation Details

#### Lambda Execution Role Permissions
The Lambda execution role includes comprehensive permissions for:
- S3 bucket access: `GetObject`, `GetBucketLocation`, `ListBucket`
- KMS decryption for encrypted S3 buckets
- DynamoDB access for tenant configuration lookup
- STS AssumeRole for double-hop cross-account access

#### Double-Hop Role Assumption
The Lambda function performs secure cross-account access:
1. Lambda execution role assumes central log distribution role
2. Central role assumes customer log distribution role with ExternalId
3. Customer role provides minimal CloudWatch Logs permissions

#### Customer Role Requirements
Customer log distribution roles must include:
- `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`
- `logs:DescribeLogGroups` on all resources (required for Vector healthchecks)
- Trust relationship with central log distribution role and ExternalId condition

## Parameters

### Main Template Parameters

| Parameter                 | Description                     | Default              | Required |
|---------------------------|---------------------------------|----------------------|----------|
| Environment               | Environment name                | development          | Yes |
| ProjectName               | Project name for resource naming | multi-tenant-logging | Yes |
| TemplateBucket            | S3 bucket for nested templates | N/A                  | Yes |
| RandomSuffix              | Random suffix for unique naming | Generated by script  | Yes |
| IncludeSQSStack           | Deploy SQS stack                | false                | No |
| IncludeLambdaStack        | Deploy Lambda stack             | false                | No |
| ECRImageUri               | ECR container image URI         | ""                   | If Lambda enabled |
| EksOidcIssuer             | OIDC issuer URL for EKS cluster | ""                   | No |
| EnableS3Encryption        | Enable S3 encryption            | true                 | No |
| S3DeleteAfterDays         | Days before deleting S3 objects | 7                    | No |

### Environment-Specific Parameters

Create parameter files for different environments:

#### `parameters/production.json`
```json
{
  "Environment": "production",
  "ProjectName": "multi-tenant-logging",
  "LambdaReservedConcurrency": 200,
  "AlertEmailEndpoints": "ops@company.com,alerts@company.com",
  "EnableDetailedMonitoring": "true",
  "EnableEnhancedMonitoring": "true"
}
```

#### `parameters/staging.json`
```json
{
  "Environment": "staging",
  "ProjectName": "multi-tenant-logging",
  "LambdaReservedConcurrency": 50,
  "AlertEmailEndpoints": "dev-team@company.com",
  "EnableDetailedMonitoring": "false"
}
```

## Deployment Scripts

### Main Deployment Script (`deploy.sh`)

Full-featured deployment script with validation, error handling, and rollback capabilities.

#### Usage
```bash
./deploy.sh [OPTIONS]

OPTIONS:
    -e, --environment ENV       Environment name (production, staging, development)
    -p, --project-name NAME     Project name
    -r, --region REGION         AWS region
    -b, --template-bucket NAME  S3 bucket for templates (required)
    --include-sqs               Include SQS stack for log processing
    --include-lambda            Include Lambda stack for container-based processing
    --ecr-image-uri URI         ECR container image URI (required if --include-lambda)
    --profile PROFILE           AWS CLI profile
    --validate-only             Only validate templates
    -h, --help                  Show help
```

#### Examples
```bash
# Core infrastructure only
./deploy.sh -b my-templates-bucket

# Core + SQS for external processing
./deploy.sh -b my-templates-bucket --include-sqs

# Full container-based Lambda deployment
./deploy.sh -b my-templates-bucket --include-sqs --include-lambda --ecr-image-uri 123456789012.dkr.ecr.us-east-2.amazonaws.com/log-processor:latest

# Staging with custom profile
./deploy.sh -e staging -b my-templates-bucket --profile staging-profile --include-sqs

# Validate templates only
./deploy.sh -b my-templates-bucket --validate-only

# Production with all options
./deploy.sh -e production -b my-templates-bucket --include-sqs --include-lambda --ecr-image-uri ECR_URI
```

## Resource Outputs

### Main Stack Outputs

| Output                     | Description                       |
|----------------------------|-----------------------------------|
| CentralLoggingBucketName   | S3 bucket for central logging     |
| TenantConfigTableName      | DynamoDB table for tenant configs |
| LogDistributorFunctionName | Lambda function name              |
| CentralS3WriterRoleArn     | IAM role ARN for S3 writes        |
| VectorRoleArn              | IAM role ARN for Vector           |

### Using Outputs

```bash
# Get stack outputs
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-production \
  --query 'Stacks[0].Outputs'

# Get specific output
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-production \
  --query 'Stacks[0].Outputs[?OutputKey==`CentralLoggingBucketName`].OutputValue' \
  --output text
```

## Monitoring and Observability

The infrastructure provides basic observability through standard AWS service metrics:

### Built-in AWS Monitoring
- **CloudWatch Logs**: Lambda function logs and processing events
- **Service Metrics**: S3, Lambda, SQS, and DynamoDB metrics available through AWS Console
- **Resource Tags**: All resources tagged for organization and cost tracking

### Custom Monitoring (Optional)
Custom dashboards and alarms can be added incrementally based on operational requirements:
- Lambda function performance monitoring
- S3 storage utilization tracking
- SQS queue depth monitoring
- Budget threshold alerts

### SNS Notifications

Configure email notifications:
```bash
# During deployment
./deploy.sh -b my-templates-bucket --alert-emails "ops@company.com,alerts@company.com"

# After deployment
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:123456789012:multi-tenant-logging-production-alerts \
  --protocol email \
  --notification-endpoint your-email@company.com
```

## Security

### IAM Roles and Policies

The infrastructure creates minimal IAM roles with least privilege:

- **CentralS3WriterRole**: Allows Vector to write logs directly to S3 with KMS encryption
- **VectorRole**: Uses IRSA to assume the CentralS3WriterRole (when OIDC configured)
- **LambdaExecutionRole**: Full permissions for log processing including S3, KMS, DynamoDB, and STS
- **LogDistributorRole** (CentralLogDistributionRole): Intermediate role for double-hop assumption
- **DLQProcessorRole**: Allows DLQ processing Lambda to send alerts

### Encryption

- **S3**: Server-side encryption with KMS
- **DynamoDB**: Encryption at rest
- **SQS/SNS**: Encryption with AWS managed keys

### Cross-Account Access

Lambda functions use double-hop role assumption with ExternalId for secure cross-account log delivery:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CENTRAL-ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "CENTRAL-ACCOUNT-ID"
        }
      }
    }
  ]
}
```

## Cost Optimization

### S3 Lifecycle Management

Automatic transitions:
- Standard → Standard-IA (30 days)
- Standard-IA → Glacier (90 days)
- Glacier → Deep Archive (365 days)
- Deletion (7 years)

### S3 Direct Write Optimization

- Gzip compression for storage savings
- Dynamic partitioning by customer_id/cluster_id/application/pod_name
- Optimized batch settings (10MB/5 minutes)

### Lambda Optimization

- Reserved concurrency to prevent runaway costs
- Batch processing (10 SQS messages per invocation) with partial batch failure support
- Efficient error handling with `batchItemFailures` for automatic retry
- Container-based deployment for better cold start performance
- Vector subprocess for optimized CloudWatch Logs delivery

## Troubleshooting

### Common Issues

1. **Stack Creation Failures**
   ```bash
   # Check stack events
   aws cloudformation describe-stack-events --stack-name multi-tenant-logging-production
   
   # Check nested stack failures
   aws cloudformation describe-stack-resources --stack-name multi-tenant-logging-production
   ```

2. **Template Validation Errors**
   ```bash
   # Validate individual templates
   aws cloudformation validate-template --template-body file://main.yaml
   ```

3. **Permission Errors**
   ```bash
   # Check IAM permissions
   aws iam simulate-principal-policy \
     --policy-source-arn arn:aws:iam::123456789012:user/your-user \
     --action-names cloudformation:CreateStack \
     --resource-arns "*"
   ```

4. **IAM Policy ARN Format Errors**
   - Error: `Resource handler returned message: "Resource multi-tenant-logging-production-central-* must be in ARN format"`
   - Solution: Use `!Sub '${BucketName.Arn}/*'` instead of `!Sub '${BucketName}/*'` in IAM policies

5. **Nested Stack Template URL Errors**
   - Error: `TemplateURL must be a supported URL`
   - Solution: Use legacy S3 URL format: `https://s3.amazonaws.com/bucket/path` instead of `https://bucket.s3.region.amazonaws.com/path`

6. **Invalid Resource Type Errors**
   - Error: `Invalid template resource property 'AWS::DynamoDB::Item'`
   - Solution: Remove AWS::DynamoDB::Item resources - use Lambda or AWS CLI to populate DynamoDB tables

7. **DynamoDB SSE Configuration Errors**
   - Error: `One or more parameter values were invalid: SSEType is required`
   - Solution: Include `SSEType: KMS` when using `KMSMasterKeyId` in SSE configuration

### Debugging Commands

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name multi-tenant-logging-production

# Get stack events
aws cloudformation describe-stack-events \
  --stack-name multi-tenant-logging-production \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]'

# Check resource drift
aws cloudformation detect-stack-drift --stack-name multi-tenant-logging-production
```

## Maintenance

### Updates and Patches

```bash
# Update stack with new template version
./deploy.sh -b my-templates-bucket

# Update only specific parameters
aws cloudformation update-stack \
  --stack-name multi-tenant-logging-production \
  --use-previous-template \
  --parameters ParameterKey=LambdaReservedConcurrency,ParameterValue=150
```

### Backup and Recovery

```bash
# Export stack template
aws cloudformation get-template \
  --stack-name multi-tenant-logging-production \
  --template-stage Original > backup-template.yaml

# Create change set for updates
aws cloudformation create-change-set \
  --stack-name multi-tenant-logging-production \
  --template-body file://main.yaml \
  --change-set-name update-$(date +%Y%m%d-%H%M%S)
```

## Lambda Processing Details

### Log Format Handling
The Lambda processor handles Vector's output format:
- Vector writes JSON arrays on a single line
- Lambda parses the array and extracts individual log events
- Only the `message` field is sent to CloudWatch (no Vector metadata)

### Log Stream Naming
CloudWatch log streams are named using the pattern: `application-pod_name-date`
- Example: `payment-service-payment-pod-abc123-2024-01-01`
- This format provides clear identification of log sources

### Error Handling
The Lambda function implements robust error handling:
- Returns `batchItemFailures` for failed messages
- Failed messages remain in SQS for retry
- Comprehensive INFO-level logging for debugging
- Vector subprocess output captured and logged

## Support

For questions or issues:
- Create an issue in the repository
- Contact the Platform Engineering team
- Review the troubleshooting section above

## Contributing

1. Make changes to templates
2. Validate with `./deploy.sh --validate-only`
3. Test in staging environment
4. Submit pull request with description of changes

## License

This project is licensed under the MIT License - see the LICENSE file for details.