# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-tenant logging pipeline infrastructure for AWS that implements a "Centralized Ingestion, Decentralized Delivery" architecture. The system collects logs from Kubernetes/OpenShift clusters using Vector agents, processes them through AWS services, and delivers them to individual customer AWS accounts.

## Development Commands

### Infrastructure Management
```bash
# Deploy infrastructure
cd terraform/
terraform init
terraform plan -var="eks_oidc_issuer=your-eks-oidc-issuer"
terraform apply

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

### Testing and Validation
```bash
# Validate Terraform configuration
cd terraform/
terraform validate
terraform plan

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

# Check Firehose status
aws firehose describe-delivery-stream --delivery-stream-name central-logging-stream
```

## Architecture Overview

The system consists of 5 main stages:

1. **Collection**: Vector agents deployed as DaemonSets collect logs from Kubernetes pods and enrich them with tenant metadata
2. **Ingestion**: Kinesis Data Firehose provides centralized, scalable ingestion with dynamic partitioning
3. **Staging**: S3 serves as a staging area with lifecycle policies for cost optimization
4. **Notification**: SNS/SQS hub-and-spoke pattern for event-driven processing
5. **Delivery**: Lambda function assumes cross-account roles to deliver logs to customer CloudWatch Logs

## Key Components

### Vector Configuration (`k8s/vector-config.yaml`)
- Collects logs from `/var/log/pods/**/*.log`
- Enriches with tenant metadata from pod labels (`customer-tenant-id`, `cluster-id`, `environment`)
- Filters out system logs and unknown tenants
- Structures data for Firehose dynamic partitioning
- Uses disk-based buffering for reliability

### Lambda Function (`lambda/log_distributor.py`)
- Processes SQS messages containing S3 events
- Extracts tenant information from S3 object keys
- Assumes cross-account roles using ABAC (Attribute-Based Access Control)
- Handles both Parquet and JSON log formats
- Delivers logs to customer CloudWatch Logs in batches

### Terraform Infrastructure (`terraform/`)
- Modular configuration with separate files for each service
- Comprehensive monitoring with CloudWatch dashboards and alarms
- Cost optimization features (S3 lifecycle, Parquet conversion, intelligent tiering)
- Security best practices (encryption, least privilege IAM)

## Security Model

The system uses Attribute-Based Access Control (ABAC) for cross-account access:
- Single Lambda execution role in central account
- Customer-specific "log distribution" roles in customer accounts
- Session tags for tenant isolation (`tenant_id`, `cluster_id`, `environment`)
- Trust policies that validate session tags match customer's tenant ID

## Environment Variables

### Lambda Function
- `TENANT_CONFIG_TABLE`: DynamoDB table for tenant configurations
- `MAX_BATCH_SIZE`: Maximum events per CloudWatch Logs batch (default: 1000)
- `RETRY_ATTEMPTS`: Number of retry attempts for failed operations (default: 3)

### Vector ConfigMap
- `AWS_REGION`: AWS region for Firehose stream
- `KINESIS_STREAM_NAME`: Name of the Firehose delivery stream
- `CLUSTER_ID`: Cluster identifier for log metadata

## Cost Optimization

The architecture prioritizes cost efficiency:
- Firehose buffer: 128MB/15 minutes for optimal batching
- Parquet format conversion reduces S3 storage costs by 80-90%
- S3 lifecycle policies with tiered storage
- Lambda batch processing (10 SQS messages per invocation)
- Intelligent tiering for infrequently accessed data

## Common Issues and Solutions

### Vector Not Sending Logs
- Check IAM role permissions for Firehose access
- Verify Kubernetes RBAC configuration
- Ensure pod labels include required tenant metadata

### Lambda Function Errors
- Check CloudWatch Logs: `/aws/lambda/log-distributor`
- Verify DynamoDB tenant configuration table
- Check cross-account role trust policies and session tags

### High Costs
- Review Firehose buffer settings (increase for better batching)
- Verify S3 lifecycle policies are active
- Monitor CloudWatch billing alerts

## Development Guidelines

- Follow existing code patterns and conventions
- Use Terraform for all infrastructure changes
- Tag all resources with project and environment labels
- Implement comprehensive error handling and logging
- Use least privilege IAM policies
- Enable encryption for all data at rest and in transit