# Multi-Tenant Logging Infrastructure

CloudFormation templates for deploying a comprehensive multi-tenant logging infrastructure using a "Centralized Ingestion, Decentralized Delivery" architecture.

## Architecture Overview

This infrastructure implements a scalable, secure, and cost-effective logging pipeline that:
- **Collects logs** from multiple Kubernetes/OpenShift clusters
- **Stores logs centrally** in S3 with compression and lifecycle management
- **Delivers logs** to individual customer AWS accounts via cross-account roles
- **Supports multiple regions** with global and regional deployment patterns

### Deployment Model

The infrastructure is organized into four deployment types that can be deployed independently:

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

## Quick Start

### 1. Deploy Global Infrastructure (One-time)
```bash
# Deploy central log distribution role
./deploy.sh -t global
```
📖 **[Global Deployment Guide](global/README.md)**

### 2. Deploy Regional Infrastructure (Per Region)
```bash
# Deploy core infrastructure with SQS processing
./deploy.sh -t regional \
  -b my-cloudformation-templates \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs
```
📖 **[Regional Deployment Guide](regional/README.md)**

### 3. Deploy Customer Roles (Per Customer, Per Region)
```bash
# Customer deploys role in their account
./deploy.sh -t customer \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234
```
📖 **[Customer Deployment Guide](customer/README.md)**

### 4. Deploy Cluster Roles (Per Cluster)
```bash
# Deploy Vector and processor roles for cluster
./deploy.sh -t cluster \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123
```
📖 **[Cluster Deployment Guide](cluster/README.md)**

## Directory Structure

```
cloudformation/
├── README.md                          # This overview (start here)
├── deploy.sh                          # Unified deployment script
│
├── global/                            # Global resources (deploy once)
│   ├── central-log-distribution-role.yaml
│   └── README.md                      # Global deployment guide
│
├── regional/                          # Regional resources (per region)
│   ├── main.yaml                      # Main orchestration template
│   ├── core-infrastructure.yaml       # S3, DynamoDB, KMS, IAM, SNS
│   ├── sqs-stack.yaml                 # Optional SQS queue and DLQ
│   ├── lambda-stack.yaml              # Optional container-based Lambda
│   └── README.md                      # Regional deployment guide
│
├── customer/                          # Customer-deployed templates
│   ├── customer-log-distribution-role.yaml
│   └── README.md                      # Customer deployment guide
│
└── cluster/                           # Cluster-specific IAM roles
    ├── cluster-vector-role.yaml       # Vector IRSA role
    ├── cluster-processor-role.yaml    # Processor IRSA role
    └── README.md                      # Cluster deployment guide
```

## Deployment Patterns

### Core Infrastructure Only
Deploy minimal infrastructure for external processing:
```bash
# Global + Regional core only
./deploy.sh -t global
./deploy.sh -t regional -b my-templates --central-role-arn <global-role-arn>
```

### SQS-Based Processing  
Add message queuing for external applications:
```bash
# Include SQS for message-based processing
./deploy.sh -t regional -b my-templates --central-role-arn <arn> --include-sqs
```

### Full Lambda Processing
Complete serverless processing with containers:
```bash
# Build containers first
cd ../container/
podman build -f Containerfile.processor_go-t log-processor:latest .
# Push to ECR...

# Deploy with Lambda processing
./deploy.sh -t regional -b my-templates --central-role-arn <arn> \
  --include-sqs --include-lambda --ecr-image-uri <ecr-uri>
```

## Key Features

### 🔒 **Security**
- **Cross-account access** with ExternalId validation
- **IRSA integration** for Kubernetes service accounts
- **Encryption at rest** with KMS for S3 and DynamoDB
- **Least privilege** IAM roles and policies

### 💰 **Cost Optimization**
- **Direct S3 writes** eliminate Firehose costs (~$50/TB saved)
- **GZIP compression** reduces storage costs by ~30:1
- **S3 lifecycle policies** with automated tiering
- **Batch processing** optimizes Lambda execution costs

### 🌐 **Multi-Region Support**
- **Global role** deployed once, used across all regions
- **Regional infrastructure** deployed per target region
- **Customer roles** deployed per customer per region
- **Independent scaling** and management per region

### ⚡ **Processing Options**
- **Container-based Lambda** for serverless processing
- **SQS integration** for external applications
- **Direct S3 access** for custom processing pipelines
- **Vector integration** for reliable CloudWatch delivery

## Common Workflows

### New Customer Onboarding
1. Customer deploys role: `./deploy.sh -t customer --central-role-arn <arn>`
2. Customer provides role ARN to logging service provider
3. Provider configures tenant in DynamoDB table
4. Testing validates cross-account log delivery

### New Region Expansion
1. Deploy regional infrastructure: `./deploy.sh -t regional --central-role-arn <global-arn>`
2. Customers deploy regional roles: `./deploy.sh -t customer -r <new-region>`
3. Update cluster configurations for new region
4. Validate log delivery to new region

### New Cluster Integration
1. Register OIDC provider in AWS IAM
2. Deploy cluster roles: `./deploy.sh -t cluster --cluster-name <name>`
3. Configure service account annotations
4. Deploy Vector and processor workloads

## Prerequisites

### AWS Requirements
- AWS CLI configured with appropriate permissions
- Access to target AWS regions
- IAM permissions for role creation and management

### Infrastructure Requirements
- S3 bucket for CloudFormation templates (regional deployments)
- ECR repository for container images (Lambda processing)
- Kubernetes/OpenShift clusters with OIDC providers

### Build Tools
- **Container builds**: Podman or Docker
- **Template validation**: AWS CLI
- **JSON processing**: jq (for deployment script)

## Monitoring and Observability

### Built-in AWS Services
- **CloudWatch Logs**: Lambda and application logging
- **CloudWatch Metrics**: S3, Lambda, SQS, DynamoDB metrics
- **CloudTrail**: Role assumption and API call auditing
- **X-Ray**: Optional distributed tracing for Lambda

### Resource Tagging
All resources tagged for:
- **Cost allocation**: Project, Environment, ManagedBy
- **Operational tracking**: Component identification
- **Automation**: Programmatic resource discovery

## Security Model

### Cross-Account Access Chain
```
Regional Processor → Global Central Role → Customer Role → CloudWatch Logs
```

1. **Regional processors** assume global central role
2. **Global central role** assumes customer role with ExternalId
3. **Customer role** provides CloudWatch Logs permissions
4. **Logs delivered** to customer's CloudWatch in specific region

### Key Security Features
- **Double-hop role assumption** with ExternalId validation
- **Regional permission scoping** for customer roles
- **IRSA integration** for secure Kubernetes authentication
- **Minimal privilege** roles with specific resource access

## Cost Considerations

### Storage Optimization
- **GZIP compression**: ~30:1 compression ratio
- **S3 lifecycle**: Standard → IA → Glacier → Deep Archive → Delete
- **Intelligent tiering**: Automatic optimization for access patterns

### Processing Optimization
- **Batch processing**: Multiple messages per Lambda invocation
- **Container reuse**: Efficient cold start performance
- **Reserved concurrency**: Optional cost controls for Lambda

### Operational Costs
- **No Firehose fees**: Direct S3 writes save ~$50/TB
- **IAM roles**: No charges for role existence or usage
- **STS calls**: AssumeRole operations are free

## Troubleshooting

### Common Issues
1. **Role assumption failures**: Check trust policies and ExternalId
2. **Template validation errors**: Verify S3 bucket access and template syntax
3. **Lambda container issues**: Check ECR access and image availability
4. **Cross-account delivery failures**: Validate customer role permissions

### Debugging Resources
- **Stack events**: CloudFormation console for deployment issues
- **CloudWatch Logs**: Lambda and application error logs
- **CloudTrail**: Role assumption and API call history
- **VPC Flow Logs**: Network connectivity issues (if applicable)

## Migration from Previous Structure

If upgrading from the previous monolithic structure:

1. **Deploy global stack** first to create central role
2. **Update regional deployments** with new template structure
3. **Update customer roles** to regional naming pattern
4. **Note stack name changes** include region identifiers

## Support and Documentation

### Detailed Guides
- **[Global Deployment](global/README.md)** - Central role deployment and management
- **[Regional Deployment](regional/README.md)** - Core infrastructure and processing options
- **[Customer Deployment](customer/README.md)** - Customer-side role configuration
- **[Cluster Deployment](cluster/README.md)** - IRSA setup and cluster integration

### Additional Resources
- **[Container Documentation](../container/README.md)** - Container builds and ECR deployment
- **[Kubernetes Manifests](../k8s/README.md)** - Vector and processor deployment
- **[CLAUDE.md](../CLAUDE.md)** - Development commands and procedures

### Getting Help
For issues and questions:
1. Check the appropriate deployment guide above
2. Review troubleshooting sections in relevant README
3. Check CloudFormation stack events and CloudWatch Logs
4. Create issues in the repository for bugs or enhancement requests

---

**🎯 Ready to deploy?** Start with the [Global Deployment Guide](global/README.md) to deploy the central log distribution role.