# CloudFormation Multi-Tenant Logging Infrastructure

This directory contains CloudFormation templates for deploying the multi-tenant logging infrastructure, converted from the original Terraform configuration.

## Architecture Overview

The infrastructure implements a "Centralized Ingestion, Decentralized Delivery" architecture using a nested CloudFormation stack approach:

1. **Main Stack** (`main.yaml`) - Orchestrates nested stacks with parameter passing
2. **Core Infrastructure** (`core-infrastructure.yaml`) - S3, DynamoDB, KMS, and IAM resources
3. **Kinesis Stack** (`kinesis-stack.yaml`) - Firehose delivery stream and Glue catalog
4. **Lambda Stack** (`lambda-stack.yaml`) - Lambda functions for log distribution
5. **Monitoring Stack** (`monitoring-stack.yaml`) - CloudWatch, SNS/SQS, and alerting

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate permissions
- S3 bucket for storing CloudFormation templates
- Valid AWS account with necessary service quotas

### Basic Deployment

```bash
# Clone repository and navigate to cloudformation directory
cd cloudformation/

# Deploy with minimal configuration
./deploy.sh -b your-cloudformation-templates-bucket

# Deploy to staging environment
./deploy.sh -e staging -b your-cloudformation-templates-bucket

# Deploy with custom parameters
./deploy.sh -e production -p my-logging-project -r us-west-2 -b my-templates-bucket
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
├── main.yaml                 # Main orchestration template
├── core-infrastructure.yaml  # S3, DynamoDB, KMS, IAM resources
├── kinesis-stack.yaml        # Firehose and Glue catalog
├── lambda-stack.yaml         # Lambda functions and event mappings
├── monitoring-stack.yaml     # CloudWatch, SNS/SQS, alerting
├── deploy.sh                 # Deployment script
├── MIGRATION_GUIDE.md        # Migration from Terraform guide
├── README.md                 # This file
└── parameters/               # Parameter files for different environments
    ├── production.json
    ├── staging.json
    └── development.json
```

## Parameters

### Main Template Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| Environment | Environment name | production | Yes |
| ProjectName | Project name for resource naming | multi-tenant-logging | Yes |
| EksOidcIssuer | OIDC issuer URL for EKS cluster | "" | No |
| LambdaReservedConcurrency | Reserved concurrency for Lambda | 100 | No |
| FirehoseBufferSizeMB | Firehose buffer size in MB | 128 | No |
| AlertEmailEndpoints | Email addresses for alerts | "" | No |
| EnableAnalytics | Enable analytics pipeline | false | No |
| EnableS3Encryption | Enable S3 encryption | true | No |
| CostCenter | Cost center for billing | "" | No |

### Environment-Specific Parameters

Create parameter files for different environments:

#### `parameters/production.json`
```json
{
  "Environment": "production",
  "ProjectName": "multi-tenant-logging",
  "LambdaReservedConcurrency": 200,
  "FirehoseBufferSizeMB": 128,
  "AlertEmailEndpoints": "ops@company.com,alerts@company.com",
  "EnableDetailedMonitoring": "true",
  "EnableEnhancedMonitoring": "true",
  "CostCenter": "platform-engineering"
}
```

#### `parameters/staging.json`
```json
{
  "Environment": "staging",
  "ProjectName": "multi-tenant-logging",
  "LambdaReservedConcurrency": 50,
  "FirehoseBufferSizeMB": 64,
  "AlertEmailEndpoints": "dev-team@company.com",
  "EnableDetailedMonitoring": "false",
  "CostCenter": "development"
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
    --profile PROFILE           AWS CLI profile
    --dry-run                   Show what would be deployed
    --validate-only             Only validate templates
    -h, --help                  Show help
```

#### Examples
```bash
# Production deployment
./deploy.sh -e production -b my-templates-bucket

# Staging with custom profile
./deploy.sh -e staging -b my-templates-bucket --profile staging-profile

# Validate only
./deploy.sh -b my-templates-bucket --validate-only

# Dry run
./deploy.sh -b my-templates-bucket --dry-run
```

## Resource Outputs

### Main Stack Outputs

| Output | Description |
|--------|-------------|
| CentralLoggingBucketName | S3 bucket for central logging |
| TenantConfigTableName | DynamoDB table for tenant configs |
| FirehoseDeliveryStreamName | Kinesis Firehose stream name |
| LogDistributorFunctionName | Lambda function name |
| CloudWatchDashboardURL | CloudWatch dashboard URL |
| VectorRoleArn | IAM role ARN for Vector |

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

## Monitoring and Alerting

### CloudWatch Dashboard

The deployment creates a comprehensive dashboard showing:
- Firehose delivery metrics
- Lambda function performance
- SQS queue metrics
- DynamoDB performance
- Cost and usage metrics

Access URL: `https://console.aws.amazon.com/cloudwatch/home#dashboards:name=multi-tenant-logging-production-overview`

### CloudWatch Alarms

Automatically configured alarms for:
- Lambda function errors and throttles
- Firehose delivery failures
- SQS queue depth and message age
- DynamoDB throttling
- Cost anomalies

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

- **FirehoseRole**: Allows Firehose to write to S3 and access Glue catalog
- **VectorRole**: Allows Vector to put records to Firehose
- **LogDistributorRole**: Allows Lambda to read from SQS, DynamoDB, and assume cross-account roles
- **DLQProcessorRole**: Allows DLQ processing Lambda to send alerts

### Encryption

- **S3**: Server-side encryption with KMS
- **DynamoDB**: Encryption at rest
- **SQS/SNS**: Encryption with AWS managed keys
- **Firehose**: Encryption in transit and at rest

### Cross-Account Access

Lambda functions use ABAC (Attribute-Based Access Control) for secure cross-account log delivery:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CENTRAL-ACCOUNT:role/LogDistributorRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "CENTRAL-ACCOUNT",
          "aws:RequestedRegion": "us-east-1"
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

### Firehose Optimization

- Parquet format conversion (80-90% storage savings)
- Dynamic partitioning for efficient querying
- Optimized buffer settings (128MB/15 minutes)

### Lambda Optimization

- Reserved concurrency to prevent runaway costs
- Batch processing (10 SQS messages per invocation)
- Efficient error handling with DLQ

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

## Migration from Terraform

See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for detailed instructions on migrating from the existing Terraform infrastructure.

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