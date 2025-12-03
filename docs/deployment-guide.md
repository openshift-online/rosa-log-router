# Multi-Tenant Logging Pipeline Deployment Guide

This guide provides comprehensive deployment instructions for the multi-tenant logging pipeline for both local development and production environments.

## Prerequisites

### Local Development
- **Podman** for container builds and LocalStack
- **Go 1.21+** for log processor development
- **Terraform** for infrastructure as code
- **Make** for development workflow automation

### Production Deployments
- **AWS CLI** configured with appropriate permissions
- **kubectl** configured for your Kubernetes clusters
- **Access to ECR** for container image storage (production only)

## Deployment Architecture

### Local Development (LocalStack)
```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  LocalStack  │───▶│   Terraform  │───▶│     Make     │
│              │    │              │    │              │
│ S3, DynamoDB │    │ Multi-Account│    │   Workflow   │
│ IAM, Lambda  │    │  Simulation  │    │  Automation  │
└──────────────┘    └──────────────┘    └──────────────┘
```

### Production (AWS)
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Clusters   │───▶│   Central   │───▶│  Customer   │
│             │    │             │    │             │
│   Vector    │    │ S3, DynamoDB│    │ CloudWatch  │
│ Collection  │    │  IAM Roles  │    │     S3      │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Local Development Setup

### Quick Start with Make

```bash
# View all available commands
make help

# Start LocalStack
make start

# Build the log processor container
make build

# Deploy infrastructure to LocalStack
make deploy

# Run integration tests
make test-e2e

# Clean up everything
make clean
```

### Manual Setup (without Make)

#### 1. Start LocalStack
```bash
docker compose up -d

# Wait for LocalStack to be ready
curl http://localhost:4566/_localstack/health
```

#### 2. Build Container
```bash
cd container/
podman build -f Containerfile.processor_go -t log-processor:local .
```

#### 3. Deploy with Terraform
```bash
cd terraform/local/

# Initialize Terraform
terraform init

# Plan deployment
terraform plan

# Deploy infrastructure
terraform apply -auto-approve
```

#### 4. Run Tests
```bash
cd container/
go test -count=1 -tags=integration ./integration -v -timeout 5m
```

## Kubernetes Deployment

### Prerequisites for Production

1. **Set up OIDC Provider** for your cluster:

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

2. **Deploy Cluster-Specific IAM Roles** (see production infrastructure documentation)

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

## Customer Onboarding (Production)

### Customer AWS Account Setup

For production deployments, customers need to:

1. **Set up IAM roles** for cross-account log delivery
2. **Configure S3 buckets** (if using S3 delivery)
3. **Set up CloudWatch Log Groups** (if using CloudWatch delivery)
4. **Provide role ARNs** back to the logging service provider

See production infrastructure documentation for detailed IAM role requirements.

## Tenant Configuration

### LocalStack (Development)

Tenant configurations are automatically created by Terraform in LocalStack:

```bash
# View tenant configs
TABLE_NAME=$(cd terraform/local && terraform output -raw central_dynamodb_table)
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name $TABLE_NAME

# Check specific tenant
aws --endpoint-url=http://localhost:4566 dynamodb get-item \
  --table-name $TABLE_NAME \
  --key '{"tenant_id":{"S":"customer1"},"type":{"S":"cloudwatch"}}'
```

### Production

For production deployments, configure tenants via the API or directly in DynamoDB with appropriate IAM permissions.

## Testing and Validation

### Integration Testing (LocalStack)

```bash
# Run full integration test suite
make test-e2e

# Or manually
cd container/
go test -count=1 -tags=integration ./integration -v -timeout 5m
```

### Validate Vector Flow

```bash
# Test Vector log routing to customer buckets
make validate-vector-flow
```

### Health Checks (LocalStack)

```bash
# Check LocalStack health
curl http://localhost:4566/_localstack/health

# View LocalStack logs
make logs

# Check Vector status (if deployed to cluster)
kubectl get pods -n logging
kubectl logs -n logging daemonset/vector-logs --tail=50
```

## Troubleshooting

For detailed troubleshooting information, see the [Troubleshooting Guide](troubleshooting.md).

### Quick Diagnostics (LocalStack)

```bash
# Check LocalStack health
curl http://localhost:4566/_localstack/health

# View LocalStack logs
make logs

# Check terraform state
cd terraform/local && terraform show

# Verify tenant configurations
TABLE_NAME=$(cd terraform/local && terraform output -raw central_dynamodb_table)
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name $TABLE_NAME
```

## Next Steps

After successful local setup:

1. **Run Tests**: Validate functionality with `make test-e2e`
2. **Explore Terraform**: Review infrastructure in `terraform/local/`
3. **Modify Configuration**: Adjust tenant configs in Terraform
4. **Test Vector Flow**: Run `make validate-vector-flow`
5. **Production Planning**: Review architecture and IAM requirements

For ongoing development, see:
- [Development Guide](../CLAUDE.md) - Local development workflow
- [API Management Guide](../api/README.md) - Tenant configuration API
- [Architecture Documentation](../DESIGN.md) - System design
- [Makefile](../Makefile) - Available development commands