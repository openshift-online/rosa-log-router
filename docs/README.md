# Multi-Tenant Logging Pipeline

This repository contains the implementation of a scalable, multi-tenant logging pipeline on AWS as described in the [DESIGN.md](../DESIGN.md) document.

## Architecture Overview

The solution implements a "Centralized Ingestion, Decentralized Delivery" model with the following key components:

- **Vector** log agents deployed as DaemonSets in Kubernetes clusters
- **S3** for direct log storage with dynamic partitioning by tenant
- **SNS/SQS** hub-and-spoke pattern for event-driven processing
- **Lambda** function for cross-account log delivery
- **DynamoDB** for tenant configuration management

### AWS Architecture Diagram

```mermaid
graph TB
    subgraph "Customer Kubernetes Clusters"
        K8s1[Kubernetes Cluster 1<br/>ROSA/OpenShift]
        K8s2[Kubernetes Cluster 2<br/>ROSA/OpenShift]
        K8s3[Kubernetes Cluster N<br/>ROSA/OpenShift]
        
        subgraph "Vector DaemonSets"
            V1[Vector Agent<br/>Pod Logs + Metadata]
            V2[Vector Agent<br/>Pod Logs + Metadata]
            V3[Vector Agent<br/>Pod Logs + Metadata]
        end
        
        K8s1 --> V1
        K8s2 --> V2
        K8s3 --> V3
    end

    subgraph "Central AWS Account - Log Processing"
        subgraph "Storage Layer"
            S3[S3 Central Bucket<br/>Tenant Partitioned<br/>Lifecycle Policies]
            S3E[S3 Event Notifications]
        end
        
        subgraph "Event Processing"
            SNS[SNS Topic<br/>Hub-and-Spoke]
            SQS[SQS Queue<br/>+DLQ]
            Lambda[Lambda Function<br/>Log Distributor]
        end
        
        subgraph "Configuration"
            DDB[DynamoDB<br/>Tenant Config]
        end
        
        subgraph "Security"
            STS[AWS STS<br/>Cross-Account Roles]
            CentralRole[Central Log<br/>Distribution Role]
            S3WriterRole[Central S3<br/>Writer Role]
        end
        
        subgraph "Monitoring"
            CW[CloudWatch<br/>Metrics & Dashboards]
            Alarms[CloudWatch Alarms<br/>Budget Alerts]
        end
    end

    subgraph "Customer AWS Account A"
        subgraph "Log Delivery"
            CWL_A[CloudWatch Logs<br/>/ROSA/cluster-logs/*]
        end
        
        subgraph "Customer IAM"
            Role_A[Customer Log<br/>Distribution Role]
            Trust_A[Trust Policy<br/>Session Tag Validation]
        end
        
        subgraph "Customer Monitoring"
            Dash_A[CloudWatch Dashboard<br/>Log Insights Queries]
            Metric_A[Custom Metrics<br/>Error Filtering]
        end
    end

    subgraph "Customer AWS Account B"
        subgraph "Log Delivery "
            CWL_B[CloudWatch Logs<br/>/ROSA/cluster-logs/*]
        end
        
        subgraph "Customer IAM "
            Role_B[Customer Log<br/>Distribution Role]
            Trust_B[Trust Policy<br/>Session Tag Validation]
        end
    end

    %% Data Flow
    V1 -->|Enriched Logs<br/>customer_id, cluster_id| S3
    V2 -->|Enriched Logs<br/>customer_id, cluster_id| S3
    V3 -->|Enriched Logs<br/>customer_id, cluster_id| S3
    S3 --> S3E
    S3E -->|ObjectCreated Events| SNS
    SNS -->|Fan-out Events| SQS
    SQS -->|Batch Messages| Lambda
    
    Lambda -->|Tenant Lookup| DDB
    Lambda -->|Assume Role| STS
    STS -->|Session Tags<br/>tenant_id, cluster_id| CentralRole
    
    %% Cross-Account Access
    CentralRole -->|Double-Hop<br/>Assume Customer Role| Role_A
    CentralRole -->|Double-Hop<br/>Assume Customer Role| Role_B
    
    Role_A -->|Deliver Logs| CWL_A
    Role_B -->|Deliver Logs| CWL_B
    
    %% Trust Validation
    Trust_A -.->|Validate Session Tags| Role_A
    Trust_B -.->|Validate Session Tags| Role_B
    
    %% Monitoring Flows
    Lambda --> CW
    S3 --> CW
    SQS --> CW
    
    CW --> Alarms
    CWL_A --> Dash_A
    CWL_A --> Metric_A

    %% Styling
    classDef customer fill:#e1f5fe
    classDef central fill:#f3e5f5
    classDef security fill:#fff3e0
    classDef storage fill:#e8f5e8
    classDef processing fill:#fce4ec
    
    class K8s1,K8s2,K8s3,V1,V2,V3 customer
    class Lambda,SQS,SNS central
    class STS,CentralRole,S3WriterRole,Role_A,Role_B,Trust_A,Trust_B security
    class S3,DDB storage
    class CWL_A,CWL_B,CW,Dash_A,Metric_A processing
```

### Data Flow Summary

1. **Collection**: Vector agents collect logs from Kubernetes pods and enrich with tenant metadata
2. **Direct Write**: Vector writes logs directly to S3 with dynamic partitioning by customer_id/cluster_id/application/pod_name
3. **Notification**: S3 events trigger SNS hub, which distributes to SQS queue
4. **Processing**: Lambda function processes SQS messages and delivers logs cross-account
5. **Security**: Double-hop role assumption with session tag validation ensures tenant isolation
6. **Delivery**: Logs delivered to customer CloudWatch Logs in `/ROSA/cluster-logs/*` format

## Repository Structure

```
├── cloudformation/
│   ├── main.yaml                          # Main CloudFormation orchestration template
│   ├── core-infrastructure.yaml           # S3, DynamoDB, KMS, IAM resources
│   ├── lambda-stack.yaml                  # Lambda functions and event mappings
│   ├── monitoring-stack.yaml              # CloudWatch, SNS/SQS, and alerting
│   ├── customer-log-distribution-role.yaml # Customer account CloudFormation template
│   ├── deploy.sh                          # CloudFormation deployment script
│   └── README.md                          # CloudFormation-specific documentation
├── docs/
│   └── README.md                          # This file
├── k8s/
│   ├── vector-config.yaml                # Vector ConfigMap
│   └── vector-daemonset.yaml             # Vector DaemonSet deployment
├── lambda/
│   ├── log_distributor.py                # Main Lambda function
│   └── requirements.txt                  # Python dependencies
└── DESIGN.md                             # Comprehensive architecture design
```

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate permissions
- S3 bucket for storing CloudFormation templates
- kubectl configured for your Kubernetes clusters
- Python 3.11+ (for Lambda development)

### 1. Deploy Core Infrastructure

```bash
cd cloudformation/

# Deploy with minimal configuration
./deploy.sh -b your-cloudformation-templates-bucket

# Deploy to staging environment
./deploy.sh -e staging -b your-cloudformation-templates-bucket

# Deploy with custom parameters
./deploy.sh -e production -p my-logging-project -r us-west-2 -b my-templates-bucket

# Deploy using environment variables
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-2
./deploy.sh -b your-cloudformation-templates-bucket
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
  --stack-name customer-logging-infrastructure \
  --template-body file://cloudformation/customer-log-distribution-role.yaml \
  --parameters ParameterKey=CentralLogDistributionRoleArn,ParameterValue=arn:aws:iam::CENTRAL-ACCOUNT:role/CentralLogDistributionRole \
               ParameterKey=LogRetentionDays,ParameterValue=90 \
  --capabilities CAPABILITY_NAMED_IAM
```

## CloudFormation Infrastructure

This project uses CloudFormation for infrastructure deployment with a nested stack architecture providing comprehensive parameter management, validation, and rollback capabilities. See [cloudformation/README.md](../cloudformation/README.md) for detailed deployment documentation.

### Recent Infrastructure Updates

The CloudFormation templates have undergone a major architectural change:
- **Removed Kinesis Data Firehose**: Vector agents now write directly to S3 for better cost efficiency
- **Added CentralS3WriterRole**: New IAM role for secure cross-account S3 access from Vector
- **Updated Vector Configuration**: Changed from aws_kinesis_firehose sink to aws_s3 sink
- **Modified Lambda Function**: Updated to parse new S3 key format: `customer_id/cluster_id/application/pod_name/`
- **Integrated S3 Events**: Connected S3 event notifications with existing SNS/SQS infrastructure

Previous fixes included:
- **IAM Policy Fixes**: Corrected S3 bucket ARN format in IAM policies to use proper CloudFormation intrinsic functions
- **Template URL Format**: Updated nested stack URLs to use the legacy S3 format (`https://s3.amazonaws.com/bucket/key`) required by CloudFormation
- **Resource Type Validation**: Removed invalid `AWS::DynamoDB::Item` resources that aren't supported by CloudFormation
- **Encryption Configuration**: Fixed DynamoDB SSE configuration to include required `SSEType` parameter
- **Environment Variable Support**: Deployment script now properly honors `AWS_PROFILE` and `AWS_REGION` environment variables

## Configuration

### Environment Variables

The following environment variables can be configured:

- `AWS_REGION`: AWS region for deployment (default: us-east-1)
- `S3_BUCKET_NAME`: Name of the central S3 bucket for logs
- `S3_WRITER_ROLE_ARN`: ARN of the S3 writer role for Vector
- `TENANT_CONFIG_TABLE`: DynamoDB table name for tenant configurations

### CloudFormation Parameters

Key parameters for customization:

```json
{
  "Environment": "production",
  "ProjectName": "multi-tenant-logging",
  "LambdaReservedConcurrency": 100,
  "EnableS3Encryption": true,
  "EnableDetailedMonitoring": true,
  "AlertEmailEndpoints": "ops@company.com",
  "CostCenter": "platform-engineering"
}
```

## Monitoring and Alerts

The infrastructure includes comprehensive monitoring:

### CloudWatch Dashboards
- **Multi-tenant logging overview**: System-wide metrics
- **Per-tenant dashboards**: Individual tenant monitoring

### CloudWatch Alarms
- Lambda function errors and duration
- SQS queue depth and message age
- DynamoDB throttling
- Dead letter queue messages

### Cost Monitoring
- AWS Cost Budget alerts with threshold notifications
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
- Vector S3 batch configuration: 10MB / 5 minutes
- Lambda SQS batch size: 10 messages
- CloudWatch Logs API batching: 1000 events

### Format Conversion
- GZIP compression for storage and transfer optimization
- Dynamic partitioning by customer/cluster/app for query performance

### Concurrency Management
- Lambda reserved concurrency: 100
- SQS visibility timeout: 15 minutes
- Dead letter queue for error handling

## Cost Management

### Estimated Costs (1TB/month)
- S3 storage (with lifecycle): ~$25
- Lambda execution: ~$15
- SNS/SQS: ~$5
- DynamoDB: ~$5
- **Total: ~$50/month** (vs $600+ for direct CloudWatch Logs)

### Cost Optimization Features
- S3 lifecycle policies with tiered storage
- GZIP compression
- Intelligent tiering
- Right-sized Lambda memory allocation

## Troubleshooting

### Common Issues

1. **Vector not sending logs**
   - Check IAM role permissions for S3
   - Verify S3WriterRole trust policy
   - Check Vector pod logs: `kubectl logs -n logging daemonset/vector-logs`

2. **Lambda function errors**
   - Check CloudWatch Logs: `/aws/lambda/log-distributor`
   - Verify DynamoDB tenant configuration
   - Check cross-account role trust policies

3. **High costs**
   - Review Vector batch settings
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

## Development

### Local Testing

```bash
# Test Lambda function locally
cd lambda/
python -m pytest tests/

# Validate CloudFormation templates
cd cloudformation/
./deploy.sh --validate-only -b your-templates-bucket
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