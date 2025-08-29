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

#### Environment Configuration

The project includes a `.env.sample` file for simplified environment variable management:

```bash
# Copy the sample environment file and customize with your values
cp .env.sample .env

# Edit the .env file with your AWS configuration
vim .env  # or use your preferred editor

# Source the environment variables for the current session
source .env

# Verify configuration
echo "AWS Profile: $AWS_PROFILE"
echo "AWS Region: $AWS_REGION"
echo "Template Bucket: $TEMPLATE_BUCKET"
```

**Key Environment Variables in .env:**
- `AWS_PROFILE`: Your AWS CLI profile name
- `AWS_REGION`: Target AWS region for deployment
- `AWS_ACCOUNT_ID`: Your AWS account ID
- `TEMPLATE_BUCKET`: S3 bucket for CloudFormation templates
- `ENVIRONMENT`: Environment name (development, staging, production)
- `CENTRAL_LOG_DISTRIBUTION_ROLE_ARN`: ARN of the global central role
- `ECR_IMAGE_URI`: Container image URI for Lambda deployment

**Security Note**: Never commit the `.env` file to version control. It's included in `.gitignore`.

#### Direct Python Execution

First, install dependencies locally:
```bash
cd container/
pip3 install --user -r requirements.txt
```

**SQS Polling Mode** (polls live queue for messages):
```bash
cd container/
# Source environment variables from .env file
source ../.env

python3 log_processor.py --mode sqs
```

**Manual Mode** (test with sample S3 event):
```bash
cd container/
# Source environment variables from .env file
source ../.env

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
# Source environment variables
source .env

podman run --rm \
  -e AWS_PROFILE="$AWS_PROFILE" \
  -e AWS_REGION="$AWS_REGION" \
  -e SQS_QUEUE_URL="$SQS_QUEUE_URL" \
  -e TENANT_CONFIG_TABLE="$TENANT_CONFIG_TABLE" \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN="$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  -e EXECUTION_MODE="$EXECUTION_MODE" \
  -v ~/.aws:/home/logprocessor/.aws:ro \
  log-processor:latest
```

**Option 2: AWS Credentials via Environment Variables**
```bash
# Source environment variables
source .env

# Extract credentials (do not save these in files!)
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile "$AWS_PROFILE")
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile "$AWS_PROFILE")

# Run container with explicit credentials
podman run --rm \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_REGION="$AWS_REGION" \
  -e SQS_QUEUE_URL="$SQS_QUEUE_URL" \
  -e TENANT_CONFIG_TABLE="$TENANT_CONFIG_TABLE" \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN="$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  -e EXECUTION_MODE="$EXECUTION_MODE" \
  log-processor:latest
```

**Manual Testing with Container**:
```bash
echo '{"Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"test-bucket\"}, \"object\": {\"key\": \"test-customer/test-cluster/test-app/test-pod/20240101-test.json.gz\"}}}]}"}' | podman run --rm -i \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_REGION=YOUR_AWS_REGION \
  -e TENANT_CONFIG_TABLE=multi-tenant-logging-development-tenant-configs \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=arn:aws:iam::AWS_ACCOUNT_ID:role/ROSA-CentralLogDistributionRole-XXXXXXXX \
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

#### Regional Deployment Workflow

The regional deployment model requires deploying in a specific order:

```bash
# Source environment variables
source .env

# 1. Deploy global infrastructure (one-time per AWS account)
./cloudformation/deploy.sh -t global

# Capture the global role ARN for regional deployments
CENTRAL_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-global \
  --query 'Stacks[0].Outputs[?OutputKey==`CentralLogDistributionRoleArn`].OutputValue' \
  --output text)

# 2. Deploy regional core infrastructure only (no SQS or Lambda)
./cloudformation/deploy.sh -t regional -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_ROLE_ARN"

# 3. Deploy regional with SQS stack for external processing
./cloudformation/deploy.sh -t regional -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_ROLE_ARN" --include-sqs

# 4. Deploy regional with both SQS and Lambda container-based processing
./cloudformation/deploy.sh -t regional -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_ROLE_ARN" \
  --include-sqs --include-lambda --ecr-image-uri "$ECR_IMAGE_URI"

# 5. Deploy cluster IAM roles for IRSA (optional)
./cloudformation/deploy.sh -t cluster \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123
```

#### Kubernetes/OpenShift Deployment

```bash
# Deploy Vector to Kubernetes/OpenShift using Kustomize
kubectl create namespace logging

# Deploy Vector collector (for standard Kubernetes)
kubectl apply -k k8s/collector/base

# Deploy Vector collector (for OpenShift with SecurityContextConstraints)
kubectl apply -k k8s/collector/overlays/development

# Deploy log processor to Kubernetes/OpenShift
kubectl apply -k k8s/processor/overlays/development
```

### Customer Onboarding

Customers deploy cross-account roles in their AWS accounts to enable log delivery:

```bash
# Customer deploys their log distribution role using the deploy script
./cloudformation/deploy.sh -t customer \
  --central-role-arn arn:aws:iam::CENTRAL-ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX

# Alternative: Multi-region customer deployment
for region in us-east-2 us-west-2 eu-west-1; do
  ./cloudformation/deploy.sh -t customer -r $region \
    --central-role-arn arn:aws:iam::CENTRAL-ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX
done

# Customer provides role ARN back to logging service provider
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-customer-us-east-2 \
  --query 'Stacks[0].Outputs[?OutputKey==`CustomerLogDistributionRoleArn`].OutputValue' \
  --output text
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

### Unit Testing

The project includes comprehensive unit tests for both the API and container components:

#### Prerequisites
```bash
# Install test dependencies
pip3 install -r tests/requirements.txt
```

#### Running Unit Tests

**Run all unit tests:**
```bash
# From project root
pytest tests/unit/ -v

# With coverage report
pytest tests/unit/ --cov=container --cov=api/src --cov-report=html --cov-report=term-missing
```

**Run specific test files:**
```bash
# Test log processor only
pytest tests/unit/test_log_processor.py -v

# Test API components only
pytest tests/unit/test_api_app.py -v
```

**Run with specific markers:**
```bash
# Run only unit tests (if integration tests are added later)
pytest tests/unit/ -m "unit" -v

# Run slow tests separately
pytest tests/unit/ -m "slow" -v
```

#### Test Structure

- `tests/unit/test_log_processor.py`: Tests for container/log_processor.py
  - S3 object key parsing and tenant info extraction
  - DynamoDB tenant configuration retrieval
  - Log file processing (NDJSON and JSON array formats)
  - Cross-account role assumption (double-hop)
  - Vector subprocess integration
  - SQS message processing and Lambda handler functionality
  - Error handling (recoverable vs non-recoverable errors)

- `tests/unit/test_api_app.py`: Tests for API components
  - FastAPI endpoint functionality
  - Request/response validation
  - Error handling and HTTP status codes
  - Pydantic model validation

- `tests/conftest.py`: Shared test fixtures and configuration
  - AWS service mocking with moto
  - Environment variable management
  - Test database setup

#### Test Features

- **AWS Service Mocking**: Uses `moto` library to mock AWS services (S3, DynamoDB, STS, CloudWatch Logs)
- **Comprehensive Coverage**: Tests both happy path and error scenarios
- **Isolated Tests**: Each test uses fresh mocked AWS resources
- **Environment Management**: Automatic environment variable setup and cleanup
- **Time Mocking**: Uses `freezegun` for consistent timestamp testing

#### Adding New Tests

When adding new functionality, ensure tests cover:

1. **Happy Path**: Successful execution with valid inputs
2. **Input Validation**: Invalid or malformed inputs
3. **Error Scenarios**: Network failures, AWS service errors, missing resources
4. **Edge Cases**: Empty data, boundary conditions, concurrent access
5. **Security**: Authentication, authorization, data sanitization

#### Continuous Integration

Tests are designed to run in CI/CD environments:
- No external AWS dependencies (all mocked)
- Deterministic results with time/UUID mocking
- Clear test isolation and cleanup
- Comprehensive logging for debugging test failures

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

The regional deployment model organizes infrastructure into four deployment types:

- **Global Infrastructure**: Central log distribution role (deployed once per AWS account)
  - `global/central-log-distribution-role.yaml`: Cross-account IAM role
- **Regional Infrastructure**: Per-region core resources
  - `regional/core-infrastructure.yaml`: S3, DynamoDB, SNS, IAM roles
  - `regional/sqs-stack.yaml`: Optional SQS queue and DLQ for message processing  
  - `regional/lambda-stack.yaml`: Optional container-based Lambda function for serverless processing
- **Customer Infrastructure**: Customer-deployed cross-account roles
  - `customer/customer-log-distribution-role.yaml`: Regional customer roles
- **Cluster Infrastructure**: Cluster-specific IRSA roles
  - `cluster/cluster-vector-role.yaml`: Vector IAM role for log collection
  - `cluster/cluster-processor-role.yaml`: Processor IAM role for log processing
- **Container**: Unified Python processor supporting Lambda, SQS polling, and manual modes

## Key Components

### Vector Configuration (`k8s/collector/base/vector-config.yaml`, `vector-local-test.yaml`)
- Collects logs from `/var/log/pods/**/*.log` in production
- **Namespace Filtering**: Uses `extra_namespace_label_selector` to only collect from namespaces with `hypershift.openshift.io/hosted-control-plane=true`
- Enriches logs with metadata: cluster_id, namespace, application (from pod label), pod_name
- Writes directly to S3 with dynamic key prefixing: `cluster_id/namespace/application/pod_name/`
- Output format: NDJSON (newline-delimited JSON) with all logs in a single JSON array per file
- Uses disk-based buffering for reliability (10GB max)
- Batch settings: 64MB / 5 minutes (Note: Vector has known issues with batch sizing)
- **Role Assumption**: Uses IRSA or base AWS credentials to assume S3WriterRole for secure S3 access
- **Compression**: GZIP compression is properly working with ~30-35:1 compression ratios

### Unified Log Processor (`container/log_processor.py`)
- **Multi-mode execution**: Lambda runtime, SQS polling, manual input
- Processes SQS messages containing S3 events
- Extracts tenant information from S3 object keys (cluster_id/namespace/application/pod_name)
- **Log Processing**: 
  - Downloads and decompresses gzipped files from S3
  - Parses Vector's JSON array format (single line with array of log objects)
  - Extracts only the 'message' field from each log record
- **CloudWatch Delivery**:
  - Log streams named: `application-pod_name-date`
  - Sends only message content (no Vector metadata wrapper)
- **Cross-Account Access**:
  - Double-hop role assumption with ExternalId validation
  - Lambda role → Central distribution role → Customer role
- **Vector Integration**: Spawns Vector subprocess for reliable CloudWatch Logs delivery
  - Generates temporary Vector config with customer credentials
  - Streams raw log messages to Vector via stdin
  - Vector handles batching, retries, and CloudWatch API interactions
  - Enhanced logging: environment variables, stdout/stderr, return codes
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

The regional deployment model implements a secure double-hop role assumption architecture for cross-account access:

### Role Hierarchy and Access Chain
```
Regional Processor → Global Central Role → Customer Regional Role → CloudWatch Logs
```

1. **Regional Processor Role**: Lambda or container execution role in regional infrastructure
2. **Global Central Role**: `ROSA-CentralLogDistributionRole-{suffix}` deployed once globally
3. **Customer Regional Role**: `CustomerLogDistribution-{region}` deployed per customer per region
4. **CloudWatch Logs**: Target destination in customer account

### Security Features
- **ExternalId Validation**: Customer roles require ExternalId matching central account ID
- **Regional Isolation**: Customer roles scoped to specific AWS regions
- **Double-Hop Access**: Two-step role assumption provides security boundaries and audit trail
- **Least Privilege**: Minimal permissions with resource-specific restrictions
- **IRSA Integration**: Kubernetes service accounts use IAM Roles for Service Accounts

### Regional Security Benefits
- **Isolated Permissions**: Each regional customer role only grants access to that region's CloudWatch Logs
- **Independent Trust Policies**: Customer roles can be managed independently per region
- **Compliance Support**: Supports data residency requirements through regional role deployment
- **Fault Isolation**: Security issues in one region don't affect others

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

The project uses a `.env` file for centralized configuration management. All environment variables can be sourced from this file:

### AWS Configuration
- `AWS_PROFILE`: Your AWS CLI profile name
- `AWS_REGION`: Target AWS region for deployment
- `AWS_ACCOUNT_ID`: Your AWS account ID
- `AWS_ACCESS_KEY_ID`: AWS access key (optional, prefer AWS_PROFILE)
- `AWS_SECRET_ACCESS_KEY`: AWS secret key (optional, prefer AWS_PROFILE)

### Infrastructure Configuration
- `TEMPLATE_BUCKET`: S3 bucket for CloudFormation templates
- `ENVIRONMENT`: Environment name (development, staging, production)
- `CENTRAL_LOG_DISTRIBUTION_ROLE_ARN`: ARN of the global central role
- `ECR_IMAGE_URI`: Container image URI for Lambda deployment

### Container/Lambda Function
- `EXECUTION_MODE`: Mode of operation (`lambda`, `sqs`, `manual`)
- `TENANT_CONFIG_TABLE`: DynamoDB table for tenant configurations
- `MAX_BATCH_SIZE`: Maximum events per CloudWatch Logs batch (default: 1000)
- `RETRY_ATTEMPTS`: Number of retry attempts for failed operations (default: 3)
- `SQS_QUEUE_URL`: URL of the SQS queue (for SQS polling mode)

### Vector ConfigMap
- `S3_BUCKET_NAME`: Name of the central S3 bucket
- `S3_WRITER_ROLE_ARN`: ARN of the S3 writer role
- `CLUSTER_ID`: Cluster identifier for log metadata

### Usage Example
```bash
# Copy and configure environment file
cp .env.sample .env
vim .env  # Edit with your values

# Source variables for current session
source .env

# Use variables in commands
./cloudformation/deploy.sh -t regional -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN"
```

## DynamoDB Tenant Configuration

The system uses a DynamoDB table to store tenant-specific configuration. The table supports the following fields:

### Required Fields
- `tenant_id` (String): Primary key identifier for the tenant
- `log_distribution_role_arn` (String): ARN of the customer's IAM role for log delivery
- `log_group_name` (String): CloudWatch Logs group name for log delivery  
- `target_region` (String): AWS region where logs should be delivered

### Optional Fields
- `enabled` (Boolean): Enable/disable log processing for this tenant (defaults to `true`)
- `desired_logs` (List): List of application names to process (case-insensitive, defaults to all apps)

### Example Configuration
```json
{
  "tenant_id": "acme-corp",
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp",
  "target_region": "us-east-1",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service", "api-gateway"]
}
```

### Managing Tenant Status
- **Enable tenant**: Set `enabled` to `true` or remove the field entirely
- **Disable tenant**: Set `enabled` to `false` to skip all log processing for this tenant
- **Partial processing**: Use `desired_logs` to filter specific applications while tenant is enabled

### Operational Commands
```bash
# Check tenant configuration
aws dynamodb get-item \
  --table-name multi-tenant-logging-development-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"}}'

# Disable a tenant
aws dynamodb update-item \
  --table-name multi-tenant-logging-development-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"}}' \
  --update-expression "SET enabled = :val" \
  --expression-attribute-values '{":val":{"BOOL":false}}'

# Enable a tenant
aws dynamodb update-item \
  --table-name multi-tenant-logging-development-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"}}' \
  --update-expression "SET enabled = :val" \
  --expression-attribute-values '{":val":{"BOOL":true}}'
```

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
- Verify DynamoDB tenant configuration table (check KMS permissions)
- Check cross-account role trust policies and ExternalId configuration
- **Tenant not processing**: Check if tenant `enabled` field is set to `false` in DynamoDB
- Ensure ECR image URI is correct (for Lambda deployment)
- **Lambda Permissions Required**:
  - S3: GetObject, GetBucketLocation, ListBucket
  - KMS: Decrypt, DescribeKey (for both S3 and DynamoDB)
  - DynamoDB: GetItem, Query, BatchGetItem
  - STS: AssumeRole (for central distribution role)
- **Customer Role Permissions**:
  - CloudWatch Logs: DescribeLogGroups (on *), CreateLogGroup, CreateLogStream, PutLogEvents, PutRetentionPolicy
  - Trust relationship must include ExternalId condition

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

The regional deployment model supports multiple deployment patterns with proper dependency management:

### Global + Regional Core Infrastructure Only
```bash
# Source environment variables
source .env

# Deploy global infrastructure (one-time)
./cloudformation/deploy.sh -t global

# Deploy regional core only - use external processing
./cloudformation/deploy.sh -t regional -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN"
```

### Regional SQS-based Processing
```bash
# Source environment variables
source .env

# Deploy global + regional + SQS for external consumers
./cloudformation/deploy.sh -t global
./cloudformation/deploy.sh -t regional -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" --include-sqs

# Option 1: Run external processor with podman
podman run -e SQS_QUEUE_URL="$SQS_QUEUE_URL" -e EXECUTION_MODE=sqs log-processor:latest

# Option 2: Deploy processor to Kubernetes/OpenShift
# First, create processor IAM role:
./cloudformation/deploy.sh -t cluster \
  --cluster-name CLUSTER_NAME \
  --oidc-provider OIDC_PROVIDER_URL

# Then deploy to Kubernetes:
kubectl apply -k k8s/processor/overlays/development
```

### Regional Lambda Container Processing
```bash
# Source environment variables
source .env

# Build and push containers
cd container/
podman build -f Containerfile.collector -t log-collector:latest .
podman build -f Containerfile.processor -t log-processor:latest .

# Push to ECR
aws ecr get-login-password --region "$AWS_REGION" | \
  podman login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
podman tag log-processor:latest "$ECR_IMAGE_URI"
podman push "$ECR_IMAGE_URI"

# Deploy global + regional + SQS + Lambda
./cloudformation/deploy.sh -t global
./cloudformation/deploy.sh -t regional -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  --include-sqs --include-lambda --ecr-image-uri "$ECR_IMAGE_URI"
```

### Multi-Region Deployment
```bash
# Source environment variables
source .env

# Deploy global infrastructure once
./cloudformation/deploy.sh -t global

# Deploy to multiple regions
for region in us-east-2 us-west-2 eu-west-1; do
  ./cloudformation/deploy.sh -t regional -r $region \
    -b "templates-bucket-$region" \
    --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
    --include-sqs --include-lambda \
    --ecr-image-uri "${AWS_ACCOUNT_ID}.dkr.ecr.${region}.amazonaws.com/log-processor:latest"
done
```

## Container Execution Modes

1. **Lambda Mode** (`EXECUTION_MODE=lambda`): Default mode for AWS Lambda runtime
2. **SQS Polling Mode** (`EXECUTION_MODE=sqs`): Continuously polls SQS queue for messages
3. **Manual Mode** (`EXECUTION_MODE=manual`): Reads JSON input from stdin for testing

## Kubernetes Deployment Structure

The Kubernetes manifests are organized as:
```
k8s/
├── collector/          # Vector log collector (DaemonSet)
│   ├── base/          # Base Kubernetes resources
│   ├── openshift-base/# OpenShift-specific (includes SCC)
│   └── overlays/      # Environment-specific patches
└── processor/          # Log processor (Deployment)
    ├── base/          # Base Kubernetes resources
    ├── openshift-base/# OpenShift-specific (includes SCC)
    └── overlays/      # Environment-specific patches
```

### Known Issues and Workarounds

1. **Vector Batching**: Vector's S3 sink has known issues where batch settings (`max_bytes`, `timeout_secs`) are not strictly honored. Files are typically created every 2-3 minutes regardless of settings. The compression works correctly with ~30-35:1 ratios.

2. **Processor Health Checks**: The processor container uses `/proc/1/cmdline` for health checks as the `ps` command is not available in the minimal container image.

3. **IRSA Configuration**: Both Vector and processor use IAM Roles for Service Accounts (IRSA). Ensure the OIDC provider is registered in AWS IAM before deploying.