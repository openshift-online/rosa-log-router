# Multi-Tenant Logging Pipeline

This repository contains the implementation of a scalable, multi-tenant logging pipeline on AWS as described in the [DESIGN.md](../DESIGN.md) document.

## Architecture Overview

The solution implements a "Centralized Ingestion, Decentralized Delivery" model with the following key components:

- **Vector** log agents deployed as DaemonSets in Kubernetes clusters
- **Kinesis Data Firehose** for centralized ingestion with dynamic partitioning
- **S3** for staging and long-term storage with lifecycle policies
- **SNS/SQS** hub-and-spoke pattern for event-driven processing
- **Lambda** function for cross-account log delivery
- **DynamoDB** for tenant configuration management

## Repository Structure

```
├── cloudformation/
│   ├── main.yaml                       # Main CloudFormation orchestration template
│   ├── core-infrastructure.yaml        # S3, DynamoDB, KMS, IAM resources
│   ├── kinesis-stack.yaml              # Firehose delivery stream and Glue catalog
│   ├── lambda-stack.yaml               # Lambda functions and event mappings
│   ├── monitoring-stack.yaml           # CloudWatch, SNS/SQS, and alerting
│   ├── customer-account-template.yaml  # CloudFormation template for customer accounts
│   ├── deploy.sh                       # CloudFormation deployment script
│   ├── MIGRATION_GUIDE.md              # Migration from Terraform guide
│   └── README.md                       # CloudFormation-specific documentation
├── docs/
│   └── README.md                       # This file
├── k8s/
│   ├── vector-config.yaml             # Vector ConfigMap
│   └── vector-daemonset.yaml          # Vector DaemonSet deployment
├── lambda/
│   ├── log_distributor.py             # Main Lambda function
│   └── requirements.txt               # Python dependencies
├── terraform/
│   ├── dynamodb.tf                    # DynamoDB tenant configuration table
│   ├── firehose.tf                    # Kinesis Data Firehose configuration
│   ├── iam.tf                         # IAM roles and policies
│   ├── lambda.tf                      # Lambda function and event sources
│   ├── main.tf                        # Main Terraform configuration
│   ├── outputs.tf                     # Terraform outputs
│   ├── sns_sqs.tf                     # SNS topics and SQS queues
│   └── variables.tf                   # Terraform variables
└── DESIGN.md                          # Comprehensive architecture design
```

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate permissions
- **Option 1 (CloudFormation)**: S3 bucket for storing CloudFormation templates
- **Option 2 (Terraform)**: Terraform >= 1.0
- kubectl configured for your Kubernetes clusters
- Python 3.11+ (for Lambda development)

### 1. Deploy Core Infrastructure

**Option A: CloudFormation (Recommended)**

```bash
cd cloudformation/

# Deploy with minimal configuration
./deploy.sh -b your-cloudformation-templates-bucket

# Deploy to staging environment
./deploy.sh -e staging -b your-cloudformation-templates-bucket

# Deploy with custom parameters
./deploy.sh -e production -p my-logging-project -r us-west-2 -b my-templates-bucket
```

**Option B: Terraform**

```bash
cd terraform/
terraform init
terraform plan -var="eks_oidc_issuer=your-eks-oidc-issuer"
terraform apply
```

### 2. Deploy Vector to Kubernetes

```bash
# Create logging namespace
kubectl create namespace logging

# Deploy Vector configuration
kubectl apply -f k8s/vector-config.yaml
kubectl apply -f k8s/vector-daemonset.yaml
```

### 3. Package and Deploy Lambda Function

```bash
cd lambda/
pip install -r requirements.txt -t .
zip -r log_distributor.zip .
aws lambda update-function-code \
  --function-name log-distributor \
  --zip-file fileb://log_distributor.zip
```

### 4. Onboard Customer Accounts

Provide customers with the CloudFormation template:

```bash
aws cloudformation create-stack \
  --stack-name tenant-logging-infrastructure \
  --template-body file://cloudformation/customer-account-template.yaml \
  --parameters ParameterKey=TenantId,ParameterValue=your-tenant-id \
               ParameterKey=CentralLogDistributorRoleArn,ParameterValue=arn:aws:iam::ACCOUNT:role/LogDistributorRole \
  --capabilities CAPABILITY_NAMED_IAM
```

## Deployment Options

### CloudFormation vs Terraform

This project supports both CloudFormation and Terraform for infrastructure deployment:

- **CloudFormation**: Nested stack architecture with comprehensive parameter management, validation, and rollback capabilities. Includes automated deployment scripts. See [cloudformation/README.md](../cloudformation/README.md) for detailed documentation.
- **Terraform**: Modular configuration with state management. Original implementation method.

### Migration from Terraform to CloudFormation

If you're currently using Terraform and want to migrate to CloudFormation, see [cloudformation/MIGRATION_GUIDE.md](../cloudformation/MIGRATION_GUIDE.md) for step-by-step migration instructions.

## Configuration

### Environment Variables

The following environment variables can be configured:

- `AWS_REGION`: AWS region for deployment (default: us-east-1)
- `KINESIS_STREAM_NAME`: Name of the Firehose stream
- `TENANT_CONFIG_TABLE`: DynamoDB table name for tenant configurations

### Terraform Variables

Key variables for customization:

```hcl
# Core configuration
aws_region = "us-east-1"
environment = "production"
project_name = "multi-tenant-logging"

# Performance tuning
lambda_reserved_concurrency = 100
firehose_buffer_size_mb = 128
firehose_buffer_interval_seconds = 900

# Cost optimization
enable_parquet_conversion = true
enable_s3_intelligent_tiering = true
s3_log_retention_days = 2555

# Security
enable_s3_encryption = true
enable_xray_tracing = true
```

## Monitoring and Alerts

The infrastructure includes comprehensive monitoring:

### CloudWatch Dashboards
- **Multi-tenant logging overview**: System-wide metrics
- **Per-tenant dashboards**: Individual tenant monitoring

### CloudWatch Alarms
- Firehose delivery failures
- Lambda function errors and duration
- SQS queue depth and message age
- DynamoDB throttling
- Dead letter queue messages

### Cost Monitoring
- AWS Cost Budget alerts
- Cost anomaly detection
- Resource tagging for cost allocation

## Security

### Cross-Account Access
- Attribute-Based Access Control (ABAC) with session tags
- Least-privilege IAM policies
- Temporary credentials with STS AssumeRole

### Data Encryption
- Server-side encryption for S3 buckets
- KMS encryption for SNS/SQS messages
- Encryption in transit for all data transfers

### Network Security
- VPC endpoints for service communication (optional)
- Security groups and NACLs for network isolation

## Performance Optimization

### Batching and Aggregation
- Firehose buffer configuration: 128MB / 15 minutes
- Lambda SQS batch size: 10 messages
- CloudWatch Logs API batching: 1000 events

### Format Conversion
- Parquet format for 80-90% storage cost reduction
- GZIP compression for data transfer optimization
- Dynamic partitioning for query performance

### Concurrency Management
- Lambda reserved concurrency: 100
- SQS visibility timeout: 15 minutes
- Dead letter queue for error handling

## Cost Management

### Estimated Costs (1TB/month)
- Kinesis Data Firehose: ~$50
- S3 storage (with lifecycle): ~$25
- Lambda execution: ~$15
- SNS/SQS: ~$5
- DynamoDB: ~$5
- **Total: ~$100/month** (vs $600+ for direct CloudWatch Logs)

### Cost Optimization Features
- S3 lifecycle policies with tiered storage
- Parquet format conversion
- Intelligent tiering
- Right-sized Lambda memory allocation

## Troubleshooting

### Common Issues

1. **Vector not sending logs**
   - Check IAM role permissions for Firehose
   - Verify Kubernetes RBAC configuration
   - Check Vector pod logs: `kubectl logs -n logging daemonset/vector-logs`

2. **Lambda function errors**
   - Check CloudWatch Logs: `/aws/lambda/log-distributor`
   - Verify DynamoDB tenant configuration
   - Check cross-account role trust policies

3. **High costs**
   - Review Firehose buffer settings
   - Check S3 lifecycle policies
   - Monitor CloudWatch billing alerts

### Debug Commands

```bash
# Check Vector status
kubectl get pods -n logging
kubectl describe daemonset vector-logs -n logging

# Check Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=log-distributor \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600 \
  --statistics Sum

# Check Firehose status
aws firehose describe-delivery-stream \
  --delivery-stream-name central-logging-stream
```

## Development

### Local Testing

```bash
# Test Lambda function locally
cd lambda/
python -m pytest tests/

# Validate Terraform configuration
cd terraform/
terraform validate
terraform plan
```

### Contributing

1. Follow the existing code structure
2. Update documentation for any changes
3. Test in a development environment first
4. Submit pull requests with detailed descriptions

## Support

For issues and questions:
- Check the troubleshooting guide above
- Review CloudWatch logs and metrics
- Consult the [DESIGN.md](../DESIGN.md) for architectural details
- Open an issue in the repository

## License

This project is licensed under the MIT License - see the LICENSE file for details.