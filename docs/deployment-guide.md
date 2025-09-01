# Multi-Tenant Logging Pipeline Deployment Guide

This guide provides comprehensive deployment instructions for the multi-tenant logging pipeline across different environments and use cases.

## Prerequisites

- **AWS CLI** configured with appropriate permissions
- **S3 bucket** for storing CloudFormation templates
- **kubectl** configured for your Kubernetes clusters
- **Python 3.13+** with pip
- **Podman** for containerized testing
- **Access to ECR** for container image storage

## Deployment Architecture

The infrastructure is organized into four independent deployment types:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Global    │    │  Regional   │    │  Customer   │    │  Cluster    │
│             │    │             │    │             │    │             │
│ Central IAM │───▶│Core Infra-  │───▶│Cross-Account│    │Cluster IAM  │
│ Role        │    │structure    │    │Roles        │    │Roles (IRSA) │
│             │    │S3, DynamoDB │    │             │    │             │
│(Deploy Once │    │SNS, Optional│    │(Per Customer│    │(Per Cluster)│
│   Global)   │    │SQS, Lambda) │    │   Region)   │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

## Environment Setup

### 1. Configure Environment Variables

Copy and customize the environment file:
```bash
cp .env.sample .env
vim .env  # Edit with your values
source .env
```

**Required Environment Variables:**
- `AWS_PROFILE`: Your AWS CLI profile name
- `AWS_REGION`: Target AWS region for deployment
- `AWS_ACCOUNT_ID`: Your AWS account ID
- `TEMPLATE_BUCKET`: S3 bucket for CloudFormation templates
- `ENVIRONMENT`: Environment name (development, staging, production)
- `CENTRAL_LOG_DISTRIBUTION_ROLE_ARN`: ARN of the global central role
- `ECR_IMAGE_URI`: Container image URI for Lambda deployment

## Deployment Patterns

### Pattern 1: Core Infrastructure Only

Deploy minimal infrastructure for external processing:

```bash
# 1. Deploy global infrastructure (one-time per AWS account)
./cloudformation/deploy.sh -t global

# 2. Deploy regional core infrastructure only
./cloudformation/deploy.sh -t regional \
  -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN"
```

**Use Case**: External log processing, custom consumers, development testing

### Pattern 2: SQS-Based Processing

Deploy infrastructure with SQS for external or container-based processing:

```bash
# 1. Deploy global infrastructure
./cloudformation/deploy.sh -t global

# 2. Deploy regional with SQS for external consumers
./cloudformation/deploy.sh -t regional \
  -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  --include-sqs
```

**Use Case**: Custom processing applications, Kubernetes-based processors, cost optimization

### Pattern 3: Full Lambda Processing

Deploy complete serverless processing with container-based Lambda:

#### Step 1: Build and Push Containers
```bash
cd container/

# Build multi-stage containers
podman build -f Containerfile.collector -t log-collector:latest .
podman build -f Containerfile.processor -t log-processor:latest .

# Push to ECR
aws ecr get-login-password --region "$AWS_REGION" | \
  podman login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

podman tag log-processor:latest "$ECR_IMAGE_URI"
podman push "$ECR_IMAGE_URI"
```

#### Step 2: Deploy Infrastructure
```bash
# Deploy global + regional + SQS + Lambda
./cloudformation/deploy.sh -t global

./cloudformation/deploy.sh -t regional \
  -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  --include-sqs --include-lambda \
  --ecr-image-uri "$ECR_IMAGE_URI"
```

**Use Case**: Production serverless processing, automatic scaling, fully managed infrastructure

### Pattern 4: API Management (Optional)

Deploy REST API for tenant configuration management:

#### Step 1: Create Authentication Parameter
```bash
# Create SSM parameter for API authentication
aws ssm put-parameter \
  --name "/logging/api/psk" \
  --value "your-256-bit-base64-encoded-key" \
  --type "SecureString" \
  --description "PSK for tenant management API authentication"
```

#### Step 2: Build and Push API Containers
```bash
cd api/

# Build API containers
podman build -f Containerfile.authorizer -t logging-authorizer:latest .
podman build -f Containerfile.api -t logging-api:latest .

# Push to ECR
ECR_AUTH_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/logging-authorizer:latest"
ECR_API_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/logging-api:latest"

podman tag logging-authorizer:latest "$ECR_AUTH_URI"
podman tag logging-api:latest "$ECR_API_URI"
podman push "$ECR_AUTH_URI"
podman push "$ECR_API_URI"
```

#### Step 3: Deploy with API Management
```bash
./cloudformation/deploy.sh -t regional \
  -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  --include-api \
  --api-auth-ssm-parameter "/logging/api/psk" \
  --authorizer-image-uri "$ECR_AUTH_URI" \
  --api-image-uri "$ECR_API_URI"
```

**Use Case**: Programmatic tenant management, integration with existing systems

## Kubernetes Deployment

### Prerequisites

1. **Deploy Infrastructure First** to get required IAM role ARNs
2. **Create OIDC Provider** for your cluster:

```bash
# For OpenShift/ROSA clusters
OIDC_URL=$(oc get authentication.config.openshift.io cluster -o json | \
  jq -r .spec.serviceAccountIssuer | sed 's|https://||')

# For EKS clusters  
OIDC_URL=$(aws eks describe-cluster --name YOUR_CLUSTER \
  --query "cluster.identity.oidc.issuer" --output text | sed 's|https://||')

# Create OIDC provider in AWS
aws iam create-open-id-connect-provider \
  --url https://${OIDC_URL} \
  --client-id-list openshift  # or "sts.amazonaws.com" for EKS
```

3. **Deploy Cluster-Specific IAM Roles**:

```bash
# Deploy Vector collector role
./cloudformation/deploy.sh -t cluster \
  --cluster-template vector \
  --cluster-name YOUR-CLUSTER \
  --oidc-provider ${OIDC_URL} \
  --oidc-audience openshift

# Deploy log processor role (if using Kubernetes-based processing)
./cloudformation/deploy.sh -t cluster \
  --cluster-template processor \
  --cluster-name YOUR-CLUSTER \
  --oidc-provider ${OIDC_URL} \
  --oidc-audience openshift
```

### Vector Deployment

#### Standard Kubernetes
```bash
# Create logging namespace
kubectl create namespace logging

# Deploy using Kustomize base configuration
kubectl apply -k k8s/collector/base

# Verify deployment
kubectl get pods -n logging
kubectl logs -n logging daemonset/vector-logs
```

#### OpenShift/ROSA
```bash
# Create logging namespace
kubectl create namespace logging

# Deploy using OpenShift overlay with SecurityContextConstraints
kubectl apply -k k8s/collector/overlays/cuppett

# Verify deployment
kubectl get pods -n logging
kubectl get scc vector-scc
```

#### Environment-Specific Configuration

Update Vector ConfigMap with your environment values:

```yaml
# In k8s/collector/overlays/YOUR-ENV/vector-config-patch.yaml
configMapGenerator:
  - name: vector-config
    behavior: merge
    literals:
      - AWS_REGION=us-east-1
      - S3_BUCKET_NAME=your-central-logging-bucket
      - S3_WRITER_ROLE_ARN=arn:aws:iam::ACCOUNT:role/your-s3-writer-role
      - CLUSTER_ID=your-cluster-identifier
```

### Log Processor Deployment (Optional)

For Kubernetes-based processing instead of Lambda:

```bash
# Deploy log processor
kubectl apply -k k8s/processor/overlays/cuppett

# Verify deployment
kubectl get pods -n logging
kubectl logs -n logging deployment/log-processor
```

## Customer Onboarding

### Customer AWS Account Setup

Provide customers with the CloudFormation template for their account:

```bash
# Customer deploys in their AWS account
aws cloudformation create-stack \
  --stack-name customer-logging-infrastructure \
  --template-body file://cloudformation/customer/customer-log-distribution-role.yaml \
  --parameters \
    ParameterKey=CentralLogDistributionRoleArn,ParameterValue=arn:aws:iam::CENTRAL-ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX \
    ParameterKey=LogRetentionDays,ParameterValue=90 \
  --capabilities CAPABILITY_NAMED_IAM

# Customer provides role ARN back to logging service provider
aws cloudformation describe-stacks \
  --stack-name customer-logging-infrastructure \
  --query 'Stacks[0].Outputs[?OutputKey==`CustomerLogDistributionRoleArn`].OutputValue' \
  --output text
```

### Multi-Region Customer Deployment

For customers requiring multi-region support:

```bash
# Deploy customer roles in multiple regions
for region in us-east-2 us-west-2 eu-west-1; do
  aws cloudformation create-stack \
    --region $region \
    --stack-name customer-logging-infrastructure-$region \
    --template-body file://cloudformation/customer/customer-log-distribution-role.yaml \
    --parameters \
      ParameterKey=CentralLogDistributionRoleArn,ParameterValue=arn:aws:iam::CENTRAL-ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX \
    --capabilities CAPABILITY_NAMED_IAM
done
```

## Tenant Configuration

### CloudWatch Logs Delivery

```bash
# Add CloudWatch delivery configuration
aws dynamodb put-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --item '{
    "tenant_id": {"S": "acme-corp"},
    "type": {"S": "cloudwatch"},
    "log_distribution_role_arn": {"S": "arn:aws:iam::123456789012:role/LogDistributionRole"},
    "log_group_name": {"S": "/aws/logs/acme-corp"},
    "target_region": {"S": "us-east-1"},
    "enabled": {"BOOL": true},
    "desired_logs": {"SS": ["payment-service", "user-service"]}
  }'
```

### S3 Delivery

```bash
# Add S3 delivery configuration
aws dynamodb put-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --item '{
    "tenant_id": {"S": "acme-corp"},
    "type": {"S": "s3"},
    "bucket_name": {"S": "acme-corp-logs"},
    "bucket_prefix": {"S": "ROSA/cluster-logs/"},
    "target_region": {"S": "us-east-1"},
    "enabled": {"BOOL": true},
    "desired_logs": {"SS": []}
  }'
```

### Multi-Delivery Configuration

Each tenant can have both CloudWatch and S3 delivery configurations simultaneously:

```bash
# List all delivery configurations for a tenant
aws dynamodb query \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --key-condition-expression "tenant_id = :tenant_id" \
  --expression-attribute-values '{":tenant_id":{"S":"acme-corp"}}'
```

## Multi-Region Deployment

### Global + Multiple Regional Deployments

```bash
# Deploy global infrastructure once
./cloudformation/deploy.sh -t global

# Deploy to multiple regions
for region in us-east-2 us-west-2 eu-west-1; do
  # Build and push region-specific container images
  ECR_REGIONAL_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${region}.amazonaws.com/log-processor:latest"
  podman tag log-processor:latest "$ECR_REGIONAL_URI"
  
  aws ecr get-login-password --region $region | \
    podman login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${region}.amazonaws.com"
  podman push "$ECR_REGIONAL_URI"
  
  # Deploy regional infrastructure
  ./cloudformation/deploy.sh -t regional \
    -r $region \
    -b "templates-bucket-$region" \
    --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
    --include-sqs --include-lambda \
    --ecr-image-uri "$ECR_REGIONAL_URI"
done
```

## Environment-Specific Deployments

### Development Environment

```bash
./cloudformation/deploy.sh -e development \
  -t regional \
  -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  --include-sqs
```

### Production Environment

```bash
./cloudformation/deploy.sh -e production \
  -t regional \
  -b "$TEMPLATE_BUCKET" \
  --central-role-arn "$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  --include-sqs --include-lambda \
  --ecr-image-uri "$ECR_IMAGE_URI"
```

## Validation and Testing

### Infrastructure Validation

```bash
# Validate CloudFormation templates
./cloudformation/deploy.sh --validate-only -b "$TEMPLATE_BUCKET"
./cloudformation/deploy.sh --validate-only -b "$TEMPLATE_BUCKET" --include-sqs --include-lambda
```

### End-to-End Testing

```bash
# Test Vector configuration locally
cd test_container/
pip3 install -r requirements.txt

# Generate test logs and send to Vector
python3 fake_log_generator.py --total-batches 10 | \
  vector --config ../vector-local-test.yaml

# Test log processor with manual input
cd ../container/
echo '{"Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"test-bucket\"}, \"object\": {\"key\": \"test-customer/test-cluster/test-app/test-pod/20240101-test.json.gz\"}}}]}"}' | \
  python3 log_processor.py --mode manual
```

### Health Checks

```bash
# Check Vector status
kubectl get pods -n logging
kubectl logs -n logging daemonset/vector-logs --tail=50

# Check SQS queue metrics
aws sqs get-queue-attributes \
  --queue-url "$SQS_QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages,ApproximateNumberOfMessagesNotVisible

# Check Lambda function health
aws lambda get-function \
  --function-name multi-tenant-logging-${ENVIRONMENT}-log-distributor
```

## Troubleshooting

For detailed troubleshooting information, see the [Troubleshooting Guide](troubleshooting.md).

### Quick Diagnostics

```bash
# Check infrastructure deployment status
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-${ENVIRONMENT}

# Verify tenant configurations
aws dynamodb scan \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --select "COUNT"

# Check recent log processing
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/multi-tenant-logging-${ENVIRONMENT}"
```

## Next Steps

After successful deployment:

1. **Configure Monitoring**: Set up CloudWatch dashboards and alarms
2. **Enable Alerting**: Configure SNS notifications for failures
3. **Optimize Costs**: Review S3 lifecycle policies and Lambda memory allocation
4. **Scale Testing**: Validate performance with production log volumes
5. **Security Review**: Audit IAM roles and cross-account access patterns

For ongoing management, see:
- [API Management Guide](../api/README.md)
- [Development Guide](../CLAUDE.md)
- [Architecture Documentation](../DESIGN.md)