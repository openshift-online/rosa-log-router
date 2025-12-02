# Regional Infrastructure for Multi-Tenant Logging

This directory contains CloudFormation templates for deploying regional infrastructure components of the multi-tenant logging system. These templates create the core logging infrastructure that can be deployed in multiple AWS regions.

## Overview

Regional deployments create the core infrastructure needed for log collection, processing, and delivery within a specific AWS region. This includes S3 storage, DynamoDB configuration, SNS notifications, and optional SQS/Lambda processing components.

## Templates

### `main.yaml`
**Main orchestration template** that coordinates nested stack deployments with conditional inclusion of optional components.

**Features**:
- Conditional deployment of SQS and Lambda stacks
- Parameter passing between nested stacks
- Centralized outputs for integration
- Environment-specific configuration

### `core-infrastructure.yaml`
**Core regional resources** including S3, DynamoDB, KMS, IAM, and SNS components.

**Components**:
- Central logging S3 bucket with lifecycle policies
- Tenant configuration DynamoDB table
- KMS encryption key (optional)
- Regional IAM roles for processors
- SNS topic for S3 event notifications

### `sqs-stack.yaml` (Optional)
**SQS infrastructure** for message-based log processing with dead letter queue support.

**Components**:
- SQS queue for log delivery events
- Dead letter queue for failed messages
- Integration with SNS topic

### `lambda-stack.yaml` (Optional)
**Container-based Lambda functions** for serverless log processing.

**Components**:
- Lambda function using ECR container images
- IAM roles and policies for Lambda execution
- SQS event source mapping
- CloudWatch Logs integration

## Prerequisites

Before deploying regional infrastructure:

1. **Global Role Deployed**: The [global central role](../global/) must be deployed first
2. **S3 Template Bucket**: Bucket for storing nested CloudFormation templates
3. **ECR Repository**: Container repository if using Lambda processing (optional)
4. **Container Images**: Built and pushed to ECR if using Lambda (optional)

## Deployment Patterns

### Core Infrastructure Only
Deploy minimal infrastructure for external processing systems:

```bash
# Deploy core infrastructure only
./deploy.sh -t regional \
  -b my-cloudformation-templates \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

# Stack name: multi-tenant-logging-development-us-east-2
```

### Core + SQS Processing
Add SQS queue for message buffering and external processing:

```bash
# Deploy core infrastructure + SQS
./deploy.sh -t regional \
  -b my-cloudformation-templates \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs

# Enables external applications to poll SQS for log events
```

### Full Container-Based Processing
Complete serverless processing with Lambda containers:

```bash
# First, build and push container images
cd ../container/
podman build -f Containerfile.collector -t log-collector:latest .
podman build -f Containerfile.processor_go -t log-processor:local .

# Push to ECR
aws ecr get-login-password --region us-east-2 | \
  podman login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-2.amazonaws.com
podman tag log-processor:latest 123456789012.dkr.ecr.us-east-2.amazonaws.com/log-processor:latest
podman push 123456789012.dkr.ecr.us-east-2.amazonaws.com/log-processor:latest

# Deploy full infrastructure
./deploy.sh -t regional \
  -b my-cloudformation-templates \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs --include-lambda \
  --ecr-image-uri 123456789012.dkr.ecr.us-east-2.amazonaws.com/log-processor:latest
```

### Environment-Specific Deployments

```bash
# Development environment
./deploy.sh -t regional -e development \
  -b my-templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs

# Production environment with Lambda processing
./deploy.sh -t regional -e production -r us-west-2 \
  -b my-templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs --include-lambda \
  --ecr-image-uri 123456789012.dkr.ecr.us-west-2.amazonaws.com/log-processor:latest
```

## Parameters

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `CentralLogDistributionRoleArn` | ARN from [global deployment](../global/) | `arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234` |
| `TemplateBucket` | S3 bucket for nested templates | `my-cloudformation-templates` |

### Optional Parameters

| Parameter | Description | Default | Notes |
|-----------|-------------|---------|-------|
| `Environment` | Environment name | `development` | Used in resource naming |
| `ProjectName` | Project name | `multi-tenant-logging` | Used in resource naming |
| `EksOidcIssuer` | OIDC issuer for EKS/OpenShift | `""` | Required for cluster integration |
| `IncludeSQSStack` | Deploy SQS infrastructure | `false` | Enable with `--include-sqs` |
| `IncludeLambdaStack` | Deploy Lambda processing | `false` | Enable with `--include-lambda` |
| `ECRImageUri` | Container image URI | `""` | Required if Lambda enabled |
| `S3DeleteAfterDays` | S3 object retention | `7` | Lifecycle policy setting |
| `EnableS3Encryption` | Enable S3 KMS encryption | `true` | Recommended for production |

## Resource Naming Convention

Regional resources use **deterministic naming** based on AWS built-in values for global uniqueness:

- **S3 Bucket**: `${ProjectName}-${Environment}-${AWS::AccountId}-${AWS::Region}`
  - Example: `multi-tenant-logging-development-123456789012-us-east-2`
- **SNS Topic**: `${ProjectName}-${Environment}-log-delivery-${AWS::AccountId}-${AWS::Region}`
- **DynamoDB Table**: `${ProjectName}-${Environment}-tenant-configs`
- **IAM Roles**: `${ProjectName}-${Environment}-{role-purpose}-role`

This approach provides:
- **Global uniqueness** without requiring random suffixes
- **Predictable names** for operations and debugging
- **Self-documenting** resource identification (account, region, environment visible)

## Stack Outputs

Regional deployments provide comprehensive outputs for integration with other deployment types:

### Core Outputs
- **CentralLoggingBucketName**: S3 bucket for log storage (named: `${ProjectName}-${Environment}-${AccountId}-${Region}`)
- **TenantConfigTableName**: DynamoDB table for tenant configurations
- **CentralLogDistributionRoleArn**: Passed-through global role ARN
- **VectorRoleArn**: IAM role for Vector agents (if OIDC configured)
- **LogDeliveryTopicArn**: SNS topic for S3 event notifications

### SQS Outputs (when enabled)
- **LogDeliveryQueueArn**: SQS queue ARN for log processing events
- **LogDeliveryQueueUrl**: SQS queue URL for polling applications

### Lambda Outputs (when enabled)  
- **LogDistributorFunctionName**: Lambda function name for log processing
- **LogDistributorFunctionArn**: Lambda function ARN

### Integration Outputs
- **RegionalLogProcessorRoleArn**: IAM role for regional log processors
- **CentralS3WriterRoleArn**: IAM role for S3 write access
- **VectorAssumeRolePolicyArn**: Managed policy for Vector role assumption

## Integration with Other Deployments

### Cluster Integration
Regional outputs are used by [cluster deployments](../cluster/):

```bash
# Get outputs for cluster deployment
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-development-us-east-2 \
  --query 'Stacks[0].Outputs'

# Use in cluster deployment
./deploy.sh -t cluster \
  --cluster-name my-cluster \
  --vector-assume-role-policy-arn <VectorAssumeRolePolicyArn-from-regional>
```

### Customer Integration
Regional infrastructure supports customer log delivery:

```bash
# Customer roles trust the global role that integrates with regional infrastructure
./deploy.sh -t customer \
  --central-role-arn <CentralLogDistributionRoleArn-from-regional>
```

## Processing Architecture

### Direct S3 Processing
Vector agents write logs directly to the regional S3 bucket:

```
Vector Agents → S3 Bucket → S3 Events → SNS Topic → SQS Queue → Processor
```

### Lambda Container Processing
Container-based Lambda functions process log events:

```
S3 Events → SNS → SQS → Lambda Container → Cross-Account Delivery
```

### External Processing
Custom applications can process events via SQS:

```
S3 Events → SNS → SQS → Custom Application → CloudWatch/Other Destinations
```

## Cost Optimization Features

### S3 Lifecycle Management
- **Standard → Standard-IA**: 30 days
- **Standard-IA → Glacier**: 90 days  
- **Glacier → Deep Archive**: 365 days
- **Final Deletion**: Configurable (default 7 days for POC)

### Storage Optimization
- **GZIP Compression**: Vector compresses logs before S3 upload
- **Dynamic Partitioning**: `customer_id/cluster_id/application/pod_name/`
- **Intelligent Tiering**: Optional for infrequently accessed data

### Processing Optimization
- **Batch Processing**: Lambda processes multiple SQS messages per invocation
- **Container Reuse**: ECR containers provide efficient cold start performance
- **Reserved Concurrency**: Optional Lambda concurrency limits prevent runaway costs

## Monitoring and Observability

### Built-in AWS Monitoring
- **CloudWatch Logs**: All Lambda and application logs
- **CloudWatch Metrics**: S3, Lambda, SQS, and DynamoDB metrics
- **X-Ray Tracing**: Optional distributed tracing for Lambda functions

### Resource Tagging
All resources are tagged for:
- **Cost allocation**: Project, Environment, ManagedBy
- **Operational tracking**: StackType, Component identification
- **Automation**: Programmatic resource discovery

### Alerts and Notifications
- **SNS Integration**: S3 events trigger downstream notifications
- **SQS Dead Letter Queue**: Failed message handling and alerting
- **Lambda Error Handling**: Comprehensive error capture and logging

## Security Features

### Encryption
- **S3**: Server-side encryption with KMS (optional but recommended)
- **DynamoDB**: Encryption at rest with KMS
- **SQS/SNS**: Encryption with AWS managed keys
- **Lambda**: Environment variables encryption

### IAM Security
- **Least Privilege**: Minimal permissions for all roles
- **Role Separation**: Distinct roles for different functions
- **Cross-Account Access**: Secure role assumption patterns
- **Regional Isolation**: Region-specific resource access only

### Network Security
- **VPC Endpoints**: Optional for S3 and DynamoDB access (not included in POC)
- **Bucket Policies**: Restrict S3 access to specific roles only
- **Private Subnets**: Lambda functions can be deployed in private subnets (configurable)

## Maintenance Operations

### Stack Updates
```bash
# Update existing regional deployment
./deploy.sh -t regional \
  -b my-templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

# Add SQS to existing deployment
./deploy.sh -t regional \
  -b my-templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs

# Update Lambda container image
./deploy.sh -t regional \
  -b my-templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs --include-lambda \
  --ecr-image-uri 123456789012.dkr.ecr.us-east-2.amazonaws.com/log-processor:v2.0
```

### Backup and Recovery
```bash
# Export stack configuration
aws cloudformation get-template \
  --stack-name multi-tenant-logging-development-us-east-2 \
  --template-stage Original > backup-template.yaml

# List stack resources for disaster recovery planning
aws cloudformation describe-stack-resources \
  --stack-name multi-tenant-logging-development-us-east-2
```

## Troubleshooting

### Common Issues

1. **Template Upload Failures**
   ```bash
   # Check S3 bucket permissions and region
   aws s3 ls s3://my-templates-bucket/cloudformation/templates/
   ```

2. **Nested Stack Failures**
   ```bash
   # Check nested stack events
   aws cloudformation describe-stack-events \
     --stack-name multi-tenant-logging-development-us-east-2-CoreInfrastructureStack-ABC123
   ```

3. **Lambda Container Issues**
   ```bash
   # Check ECR repository and image
   aws ecr describe-images --repository-name log-processor
   
   # Check Lambda function logs
   aws logs filter-log-events \
     --log-group-name /aws/lambda/multi-tenant-logging-development-log-distributor
   ```

4. **Cross-Account Role Issues**
   ```bash
   # Verify central role ARN parameter
   aws cloudformation describe-stacks \
     --stack-name multi-tenant-logging-development-us-east-2 \
     --query 'Stacks[0].Parameters[?ParameterKey==`CentralLogDistributionRoleArn`]'
   ```

### Debugging Commands

```bash
# Check stack status and events
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-development-us-east-2

# Monitor stack creation/update progress
aws cloudformation describe-stack-events \
  --stack-name multi-tenant-logging-development-us-east-2 \
  --query 'StackEvents[?ResourceStatus!=`CREATE_COMPLETE`]'

# Test SQS integration
aws sqs receive-message \
  --queue-url https://sqs.us-east-2.amazonaws.com/123456789012/multi-tenant-logging-development-log-delivery-queue

# Validate DynamoDB table
aws dynamodb scan --table-name multi-tenant-logging-development-tenant-configs --limit 5
```

## Performance Considerations

### S3 Performance
- **Prefix Distribution**: Dynamic partitioning distributes load across S3 prefixes
- **Transfer Acceleration**: Can be enabled for cross-region uploads
- **Multipart Upload**: Vector uses multipart uploads for large log files

### Lambda Performance
- **Container Images**: Faster cold starts compared to deployment packages
- **Reserved Concurrency**: Prevents Lambda throttling under high load
- **Provisioned Concurrency**: Can be added for consistent performance (additional cost)

### DynamoDB Performance
- **On-Demand Billing**: Scales automatically with load
- **Global Secondary Indexes**: Support efficient queries by account_id and status
- **Point-in-Time Recovery**: Enabled for data protection

## Related Documentation

- **[Global Deployment](../global/)** - Central log distribution role (required first)
- **[Customer Deployment](../customer/)** - Customer-side roles for log delivery
- **[Cluster Deployment](../cluster/)** - Cluster-specific IAM roles and IRSA setup
- **[Main Documentation](../)** - Complete architecture overview and workflows
- **[Container Documentation](../../container/)** - Container build and deployment guide

## Support

For regional infrastructure issues:
1. Verify global role deployment and ARN accuracy
2. Check template bucket accessibility and template uploads
3. Review nested stack events for specific component failures
4. Validate ECR repository access and container image availability
5. Monitor CloudWatch Logs for Lambda and application errors