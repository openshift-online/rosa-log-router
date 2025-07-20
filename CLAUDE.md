# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**This is a PROOF OF CONCEPT (POC) project** for a multi-tenant logging pipeline infrastructure on AWS that implements a "Centralized Ingestion, Decentralized Delivery" architecture. The system collects logs from Kubernetes/OpenShift clusters using Vector agents, writes them directly to S3, and delivers them to individual customer AWS accounts.

**POC Status**: This project is focused on demonstrating core functionality with minimal complexity. The infrastructure provides basic observability through AWS native services. Advanced monitoring, custom metrics, and alerting features should be added incrementally after the core pipeline is validated.

## Development Commands

### Local Development

#### Prerequisites
- Python 3.13+ with pip
- Podman for containerized testing
- AWS CLI configured with your AWS profile
- Access to deployed CloudFormation stack with SQS queue

#### Direct Python Execution

First, install dependencies locally:
```bash
cd container/
pip3 install --user -r requirements.txt
```

**SQS Polling Mode** (polls live queue for messages):
```bash
cd container/
export AWS_PROFILE=YOUR_AWS_PROFILE
export AWS_REGION=YOUR_AWS_REGION
export TENANT_CONFIG_TABLE=multi-tenant-logging-development-tenant-configs
export CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=arn:aws:iam::AWS_ACCOUNT_ID:role/multi-tenant-logging-development-log-distributor-role
export SQS_QUEUE_URL=https://sqs.YOUR_AWS_REGION.amazonaws.com/AWS_ACCOUNT_ID/multi-tenant-logging-development-log-delivery-queue

python3 log_processor.py --mode sqs
```

**Manual Mode** (test with sample S3 event):
```bash
cd container/
export AWS_PROFILE=YOUR_AWS_PROFILE
export AWS_REGION=YOUR_AWS_REGION
export TENANT_CONFIG_TABLE=multi-tenant-logging-development-tenant-configs
export CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=arn:aws:iam::AWS_ACCOUNT_ID:role/multi-tenant-logging-development-log-distributor-role

# Test with sample S3 event
echo '{"Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"test-bucket\"}, \"object\": {\"key\": \"test-customer/test-cluster/test-app/test-pod/20240101-test.json.gz\"}}}]}"}' | python3 log_processor.py --mode manual
```

#### Container-based Execution

Build the containers:
```bash
cd container/
# Build collector container first (contains Vector)
podman build -f Containerfile.collector -t log-collector:latest .
# Build processor container (includes Vector from collector)
podman build -f Containerfile.processor -t log-processor:latest .
```

**Option 1: AWS Profile with Volume Mount**
```bash
podman run --rm \
  -e AWS_PROFILE=YOUR_AWS_PROFILE \
  -e AWS_REGION=YOUR_AWS_REGION \
  -e SQS_QUEUE_URL=https://sqs.YOUR_AWS_REGION.amazonaws.com/AWS_ACCOUNT_ID/multi-tenant-logging-development-log-delivery-queue \
  -e TENANT_CONFIG_TABLE=multi-tenant-logging-development-tenant-configs \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=arn:aws:iam::AWS_ACCOUNT_ID:role/multi-tenant-logging-development-log-distributor-role \
  -e EXECUTION_MODE=sqs \
  -v ~/.aws:/home/logprocessor/.aws:ro \
  log-processor:latest
```

**Option 2: AWS Credentials via Environment Variables**
```bash
# Extract credentials (do not save these in files!)
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile YOUR_AWS_PROFILE)
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile YOUR_AWS_PROFILE)

# Run container with explicit credentials
podman run --rm \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_REGION=YOUR_AWS_REGION \
  -e SQS_QUEUE_URL=https://sqs.YOUR_AWS_REGION.amazonaws.com/AWS_ACCOUNT_ID/multi-tenant-logging-development-log-delivery-queue \
  -e TENANT_CONFIG_TABLE=multi-tenant-logging-development-tenant-configs \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=arn:aws:iam::AWS_ACCOUNT_ID:role/multi-tenant-logging-development-log-distributor-role \
  -e EXECUTION_MODE=sqs \
  log-processor:latest
```

**Manual Testing with Container**:
```bash
echo '{"Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"test-bucket\"}, \"object\": {\"key\": \"test-customer/test-cluster/test-app/test-pod/20240101-test.json.gz\"}}}]}"}' | podman run --rm -i \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_REGION=YOUR_AWS_REGION \
  -e TENANT_CONFIG_TABLE=multi-tenant-logging-development-tenant-configs \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=arn:aws:iam::AWS_ACCOUNT_ID:role/multi-tenant-logging-development-log-distributor-role \
  -e EXECUTION_MODE=manual \
  log-processor:latest
```

#### Security Notes
- **Never commit AWS credentials to any files**
- Use environment variables for temporary credential passthrough
- Volume mount ~/.aws for local development only
- The example credentials extraction commands above are for local development only

### Container Management
```bash
# Build collector container (contains Vector binary)
cd container/
podman build -f Containerfile.collector -t log-collector:latest .

# Build processor container (includes Vector from collector)
podman build -f Containerfile.processor -t log-processor:latest .

# Tag and push to ECR (for Lambda deployment)
aws ecr get-login-password --region YOUR_AWS_REGION | podman login --username AWS --password-stdin AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com
podman tag log-processor:latest AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com/log-processor:latest
podman push AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com/log-processor:latest
```

### Infrastructure Management
```bash
# Deploy Vector to Kubernetes
kubectl create namespace logging
kubectl apply -f k8s/vector-config.yaml
kubectl apply -f k8s/vector-daemonset.yaml

# Deploy core infrastructure only (no SQS or Lambda)
./cloudformation/deploy.sh

# Deploy with SQS stack for external processing
./cloudformation/deploy.sh --include-sqs

# Deploy with both SQS and Lambda container-based processing
./cloudformation/deploy.sh --include-sqs --include-lambda --ecr-image-uri AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com/log-processor:latest
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
# Test log processor with manual input
echo '{"Message": "{\"Records\": [...]}"}' | podman run --rm -i log-processor:latest --mode manual

# Test log processor against live SQS queue
podman run --rm \
  -e AWS_PROFILE=YOUR_AWS_PROFILE \
  -e SQS_QUEUE_URL=https://sqs.YOUR_AWS_REGION.amazonaws.com/AWS_ACCOUNT_ID/QUEUE-NAME \
  -v ~/.aws:/home/logprocessor/.aws:ro \
  log-processor:latest --mode sqs

# Test Vector with fake log generator and S3 role assumption
cd test_container/
pip3 install -r requirements.txt

# Set up environment for Vector role assumption (use test-vector.sh script)
../test-vector.sh

# Basic Vector test with realistic fake logs and role assumption
python3 fake_log_generator.py --total-batches 10 | vector --config ../vector-local-test.yaml

# High-volume Vector performance test
python3 fake_log_generator.py \
  --min-batch-size 50 --max-batch-size 100 \
  --min-sleep 0.1 --max-sleep 0.5 \
  --total-batches 100 | vector --config ../vector-local-test.yaml

# Multi-tenant Vector test
python3 fake_log_generator.py \
  --customer-id acme-corp \
  --cluster-id prod-cluster-1 \
  --application payment-service \
  --total-batches 20 | vector --config ../vector-local-test.yaml

# Container-based Vector test
podman build -f Containerfile -t fake-log-generator .
podman run --rm fake-log-generator --total-batches 10 | vector --config ../vector-local-test.yaml

# Manual role assumption setup (alternative to script)
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile scuppett-dev)
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile scuppett-dev)
export S3_WRITER_ROLE_ARN=arn:aws:iam::641875867446:role/multi-tenant-logging-development-central-s3-writer-role
export S3_BUCKET_NAME=multi-tenant-logging-development-central-12345678
export AWS_REGION=us-east-2

# Check Vector status
kubectl get pods -n logging
kubectl describe daemonset vector-logs -n logging
kubectl logs -n logging daemonset/vector-logs

# Check SQS queue metrics
aws sqs get-queue-attributes \
  --queue-url https://sqs.YOUR_AWS_REGION.amazonaws.com/AWS_ACCOUNT_ID/QUEUE-NAME \
  --attribute-names ApproximateNumberOfMessages,ApproximateNumberOfMessagesNotVisible
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

The system consists of 5 main stages with flexible processing options:

1. **Collection**: Vector agents deployed as DaemonSets collect logs from Kubernetes pods and enrich them with tenant metadata
2. **Direct Storage**: Vector writes logs directly to S3 with dynamic partitioning by customer_id/cluster_id/application/pod_name
3. **Notification**: S3 event notifications trigger SNS hub-and-spoke pattern for event-driven processing
4. **Processing**: Multiple options for log processing:
   - **Container-based Lambda**: ECR container image with unified Python processor
   - **External SQS consumers**: Custom applications polling SQS queue
   - **Local development**: Podman containers for testing and development
5. **Delivery**: Processor assumes cross-account roles to deliver logs to customer CloudWatch Logs

### Component Architecture

- **Core Infrastructure**: S3, DynamoDB, SNS, IAM roles (always deployed)
- **SQS Stack**: Optional SQS queue and DLQ for message processing
- **Lambda Stack**: Optional container-based Lambda function for serverless processing
- **Container**: Unified Python processor supporting Lambda, SQS polling, and manual modes

## Key Components

### Vector Configuration (`k8s/vector-config.yaml`, `vector-local-test.yaml`)
- Collects logs from `/var/log/pods/**/*.log` (production) or stdin (local testing)
- Enriches with tenant metadata from pod annotations (`customer-id`, `cluster-id`, `environment`, `application`)
- Filters out system logs and unknown tenants
- Writes directly to S3 with dynamic key prefixing using NDJSON format
- Uses disk-based buffering for reliability
- Batch settings: 10MB / 5 minutes
- **Role Assumption**: Uses base AWS credentials to assume S3WriterRole for secure S3 access

### Unified Log Processor (`container/log_processor.py`)
- **Multi-mode execution**: Lambda runtime, SQS polling, manual input
- Processes SQS messages containing S3 events
- Extracts tenant information from S3 object keys (customer_id/cluster_id/application/pod_name)
- Assumes cross-account roles with ExternalId validation
- Handles gzip-compressed NDJSON log formats from Vector
- **Vector Integration**: Spawns Vector subprocess for reliable CloudWatch Logs delivery
  - Generates temporary Vector config with customer credentials
  - Streams decompressed logs to Vector via stdin
  - Vector handles batching, retries, and CloudWatch API interactions
  - Cleans up temporary files and processes after delivery

### Container Infrastructure (`container/`)
- **Containerfile.collector**: Base container with Vector binary installation
- **Containerfile.processor**: Log processor container that includes Vector
- **Multi-stage build**: Processor builds on collector for consistent Vector version
- **Multi-mode entrypoint**: Supports Lambda runtime, SQS polling, and manual modes
- **Minimal dependencies**: Only boto3 and botocore required for Python
- **Rootless execution**: Runs as non-root user for security

### CloudFormation Infrastructure (`cloudformation/`)
- **Modular design**: Core infrastructure + optional SQS + optional Lambda stacks
- **Flexible deployment**: Deploy only needed components
- **Container support**: Lambda stack uses ECR container images
- **Cost optimization**: S3 lifecycle, GZIP compression, intelligent tiering
- **Security best practices**: Encryption, least privilege IAM

## Security Model

The system uses a double-hop role assumption architecture for cross-account access:
- Lambda/Container execution role in central account (assumes central log distribution role)
- Central log distribution role in central account (assumes customer roles)
- Customer-specific "log distribution" roles in customer accounts
- ExternalId validation for additional security
- Two-step role assumption provides security boundaries and audit trail

## Vector Authentication Configuration

### Local Testing with Role Assumption

For local Vector testing, the configuration requires base AWS credentials and role assumption:

```yaml
# vector-local-test.yaml
auth:
  assume_role: "${S3_WRITER_ROLE_ARN}"
```

**Required Environment Variables for Vector:**
- `AWS_ACCESS_KEY_ID`: Base access key from your AWS profile
- `AWS_SECRET_ACCESS_KEY`: Base secret key from your AWS profile
- `S3_WRITER_ROLE_ARN`: ARN of the S3 writer role to assume
- `S3_BUCKET_NAME`: Target S3 bucket for log storage
- `AWS_REGION`: AWS region

**Setup Process:**
1. Extract base credentials from AWS profile
2. Set environment variables for Vector
3. Vector uses base credentials to assume S3WriterRole
4. S3WriterRole provides permissions for S3 bucket access

## Environment Variables

### Container/Lambda Function
- `EXECUTION_MODE`: Mode of operation (`lambda`, `sqs`, `manual`)
- `TENANT_CONFIG_TABLE`: DynamoDB table for tenant configurations
- `MAX_BATCH_SIZE`: Maximum events per CloudWatch Logs batch (default: 1000)
- `RETRY_ATTEMPTS`: Number of retry attempts for failed operations (default: 3)
- `CENTRAL_LOG_DISTRIBUTION_ROLE_ARN`: ARN of the central log distribution role for double-hop access
- `SQS_QUEUE_URL`: URL of the SQS queue (for SQS polling mode)
- `AWS_REGION`: AWS region for services

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
- Verify Vector is producing NDJSON format with newline_delimited framing

### Container/Lambda Function Errors
- **Lambda mode**: Check CloudWatch Logs: `/aws/lambda/log-distributor`
- **SQS mode**: Check container logs with `podman logs CONTAINER_ID`
- **Manual mode**: Check stdin input format (SNS message with S3 event)
- Verify DynamoDB tenant configuration table
- Check cross-account role trust policies and ExternalId configuration
- Ensure ECR image URI is correct (for Lambda deployment)

### Container Build Issues
- Use `podman build --no-cache` to force rebuild
- Check Containerfile syntax and base image availability
- Verify requirements.txt dependencies are installable

### High Costs
- Review Vector batch settings (increase for better batching)
- Verify S3 lifecycle policies are active
- Monitor CloudWatch billing alerts
- Consider using SQS polling instead of Lambda for cost optimization

## Development Guidelines

- **Container-first approach**: Use podman for local development and testing
- **Modular infrastructure**: Deploy only needed CloudFormation stacks
- **Unified codebase**: Single Python script supports multiple execution modes
- Follow existing code patterns and conventions
- Use CloudFormation for all infrastructure changes
- Tag all resources with project and environment labels
- Implement comprehensive error handling and logging
- Use least privilege IAM policies
- Enable encryption for all data at rest and in transit

## Deployment Patterns

### Core Infrastructure Only
```bash
# Deploy just S3, DynamoDB, SNS, IAM - use external processing
./cloudformation/deploy.sh
```

### SQS-based Processing
```bash
# Deploy core + SQS for external consumers
./cloudformation/deploy.sh --include-sqs

# Run external processor with podman
podman run -e SQS_QUEUE_URL=... -e EXECUTION_MODE=sqs log-processor:latest
```

### Lambda Container Processing
```bash
# Build containers
cd container/
podman build -f Containerfile.collector -t log-collector:latest .
podman build -f Containerfile.processor -t log-processor:latest .

# Push to ECR
aws ecr get-login-password | podman login --username AWS --password-stdin ECR_URI
podman tag log-processor:latest ECR_URI/log-processor:latest
podman push ECR_URI/log-processor:latest

# Deploy with Lambda
./cloudformation/deploy.sh --include-sqs --include-lambda --ecr-image-uri ECR_URI/log-processor:latest
```

## Container Execution Modes

1. **Lambda Mode** (`EXECUTION_MODE=lambda`): Default mode for AWS Lambda runtime
2. **SQS Polling Mode** (`EXECUTION_MODE=sqs`): Continuously polls SQS queue for messages
3. **Manual Mode** (`EXECUTION_MODE=manual`): Reads JSON input from stdin for testing