# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-tenant logging pipeline infrastructure for AWS that implements a "Centralized Ingestion, Decentralized Delivery" architecture. The system collects logs from Kubernetes/OpenShift clusters using Vector agents, writes them directly to S3, and delivers them to individual customer AWS accounts.

## Development Commands

### Infrastructure Management
```bash
# Deploy Vector to Kubernetes
kubectl create namespace logging
kubectl apply -f k8s/vector-config.yaml
kubectl apply -f k8s/vector-daemonset.yaml

# Package and deploy Lambda function
cd lambda/
pip install -r requirements.txt -t .
zip -r log_distributor.zip .
aws lambda update-function-code --function-name log-distributor --zip-file fileb://log_distributor.zip
```

### Customer Onboarding
```bash
# Customer deploys their logging infrastructure
aws cloudformation create-stack \
  --stack-name customer-logging-infrastructure \
  --template-body file://cloudformation/customer-log-distribution-role.yaml \
  --parameters ParameterKey=CentralLogDistributionRoleArn,ParameterValue=arn:aws:iam::CENTRAL-ACCOUNT:role/CentralLogDistributionRole \
               ParameterKey=LogRetentionDays,ParameterValue=90 \
  --capabilities CAPABILITY_NAMED_IAM
```

### Testing and Validation
```bash
# Test Lambda function locally (if tests exist)
cd lambda/
python -m pytest tests/

# Check Vector status
kubectl get pods -n logging
kubectl describe daemonset vector-logs -n logging
kubectl logs -n logging daemonset/vector-logs
```

### Debugging Commands
```bash
# Check Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=log-distributor \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600 \
  --statistics Sum

# Check S3 bucket metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name NumberOfObjects \
  --dimensions Name=BucketName,Value=multi-tenant-logging-production-central \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600 \
  --statistics Average
```

## Architecture Overview

The system consists of 5 main stages:

1. **Collection**: Vector agents deployed as DaemonSets collect logs from Kubernetes pods and enrich them with tenant metadata
2. **Direct Storage**: Vector writes logs directly to S3 with dynamic partitioning by customer_id/cluster_id/application/pod_name
3. **Notification**: S3 event notifications trigger SNS/SQS hub-and-spoke pattern for event-driven processing
4. **Processing**: Lambda function processes S3 events from SQS queue
5. **Delivery**: Lambda function assumes cross-account roles to deliver logs to customer CloudWatch Logs

## Key Components

### Vector Configuration (`k8s/vector-config.yaml`)
- Collects logs from `/var/log/pods/**/*.log`
- Enriches with tenant metadata from pod annotations (`customer-id`, `cluster-id`, `environment`, `application`)
- Filters out system logs and unknown tenants
- Writes directly to S3 with dynamic key prefixing
- Uses disk-based buffering for reliability
- Batch settings: 10MB / 5 minutes

### Lambda Function (`lambda/log_distributor.py`)
- Processes SQS messages containing S3 events
- Extracts tenant information from S3 object keys (customer_id/cluster_id/application/pod_name)
- Assumes cross-account roles using ABAC (Attribute-Based Access Control)
- Handles gzip-compressed JSON log formats
- Delivers logs to customer CloudWatch Logs in batches

### CloudFormation Infrastructure (`cloudformation/`)
- Customer-deployed logging infrastructure with single template
- Comprehensive monitoring with CloudWatch dashboards and alarms
- Cost optimization features (S3 lifecycle, GZIP compression, intelligent tiering)
- Security best practices (encryption, least privilege IAM)

## Security Model

The system uses a double-hop Attribute-Based Access Control (ABAC) architecture for cross-account access:
- Lambda execution role in central account (assumes central log distribution role)
- Central log distribution role in central account (assumes customer roles)
- Customer-specific "log distribution" roles in customer accounts
- Session tags for tenant isolation (`tenant_id`, `cluster_id`, `environment`)
- Trust policies that validate session tags match customer's tenant ID
- Two-step role assumption provides additional security boundaries

## Environment Variables

### Lambda Function
- `TENANT_CONFIG_TABLE`: DynamoDB table for tenant configurations
- `MAX_BATCH_SIZE`: Maximum events per CloudWatch Logs batch (default: 1000)
- `RETRY_ATTEMPTS`: Number of retry attempts for failed operations (default: 3)
- `CENTRAL_LOG_DISTRIBUTION_ROLE_ARN`: ARN of the central log distribution role for double-hop access

### Vector ConfigMap
- `AWS_REGION`: AWS region for S3 bucket
- `S3_BUCKET_NAME`: Name of the central S3 bucket
- `S3_WRITER_ROLE_ARN`: ARN of the S3 writer role
- `CLUSTER_ID`: Cluster identifier for log metadata

## Cost Optimization

The architecture prioritizes cost efficiency:
- Direct S3 writes eliminate Firehose costs (~$50/TB saved)
- GZIP compression reduces storage costs
- S3 lifecycle policies with tiered storage
- Lambda batch processing (10 SQS messages per invocation)
- Intelligent tiering for infrequently accessed data

## Common Issues and Solutions

### Vector Not Sending Logs
- Check IAM role permissions for S3 access
- Verify S3WriterRole trust policy configuration
- Ensure pod annotations include required tenant metadata

### Lambda Function Errors
- Check CloudWatch Logs: `/aws/lambda/log-distributor`
- Verify DynamoDB tenant configuration table
- Check cross-account role trust policies and session tags

### High Costs
- Review Vector batch settings (increase for better batching)
- Verify S3 lifecycle policies are active
- Monitor CloudWatch billing alerts

## Development Guidelines

- Follow existing code patterns and conventions
- Use CloudFormation for all infrastructure changes
- Tag all resources with project and environment labels
- Implement comprehensive error handling and logging
- Use least privilege IAM policies
- Enable encryption for all data at rest and in transit