# Multi-Tenant Logging Pipeline Design

## Overview

This document describes the architecture and design of a multi-tenant logging pipeline that implements a "Centralized Ingestion, Decentralized Delivery" model. The system collects logs from Kubernetes/OpenShift clusters using Vector agents and delivers them to customer-specified destinations through multiple delivery methods.

## Architecture Principles

- **Centralized Collection**: Single Vector deployment per cluster collects all tenant logs
- **Flexible Delivery**: Support for multiple delivery destinations per tenant (CloudWatch Logs, S3)
- **Security Isolation**: Each tenant's logs are delivered using their own IAM roles and permissions
- **Cost Optimization**: Direct S3 writes and efficient batching reduce operational costs
- **Scalability**: Composite key DynamoDB schema enables flexible configuration management

## System Components

### 1. Log Collection (Vector)

**Technology**: Vector 0.48+ deployed as Kubernetes DaemonSet

**Responsibilities**:
- Collect logs from all pods on Kubernetes nodes
- Filter logs based on namespace labels (`hypershift.openshift.io/hosted-control-plane=true`)
- Parse and enrich log messages with metadata (cluster_id, namespace, application, pod_name)
- Handle both JSON and plain text log formats with intelligent timestamp extraction
- Write logs directly to central S3 bucket with tenant-based partitioning

**Key Features**:
- **Intelligent Parsing**: Automatically detects JSON logs and extracts structured fields
- **Timestamp Extraction**: Supports multiple timestamp formats (ISO, Unix, Kubernetes logs, Go logs)
- **Metadata Enrichment**: Adds cluster and tenant context to every log record
- **Namespace Validation**: Enhanced logic prevents empty namespace extraction failures
- **Buffer Management**: Disk-based buffering with 10GB capacity for reliability

### 2. Event Processing (Log Processor)

**Technology**: Python 3.13+ container running in AWS Lambda or Kubernetes

**Responsibilities**:
- Process S3 event notifications via SQS
- Extract tenant information from S3 object keys
- Retrieve tenant delivery configurations from DynamoDB
- Execute multiple delivery methods per tenant (fan-out delivery)
- Handle cross-account role assumptions for secure delivery

**Execution Modes**:
- **Lambda Runtime**: Serverless processing with SQS triggers
- **SQS Polling**: Container-based long polling for cost optimization
- **Manual Mode**: Development and testing with stdin input

### 3. Configuration Management (DynamoDB)

**Technology**: DynamoDB with composite primary key

**Schema Design**:
```
Primary Key: tenant_id (Partition Key) + type (Sort Key)
```

**Table Structure**:

| Field          | Type       | Required | Description                                |
|----------------|------------|----------|--------------------------------------------|
| tenant_id      | String     | Yes      | Unique tenant identifier                   |
| type           | String     | Yes      | Delivery type: "cloudwatch" or "s3"        |
| enabled        | Boolean    | No       | Enable/disable delivery (defaults to True) |
| desired_logs   | StringList | No       | Application filter list (defaults to all)  |
| groups         | StringList | No       | Application group filter list (see Application Groups) |
| target_region  | String     | No       | AWS region (defaults to processor region)  |
| ttl            | Number     | No       | Unix timestamp for automatic expiration    |
| created_at     | String     | No       | ISO timestamp (auto-generated)             |
| updated_at     | String     | No       | ISO timestamp (auto-updated)               |

**CloudWatch-Specific Fields**:

| Field                       | Type   | Required | Description               |
|-----------------------------|--------|----------|---------------------------|
| log_distribution_role_arn   | String | Yes      | Customer IAM role ARN     |
| log_group_name              | String | Yes      | CloudWatch log group name |

**S3-Specific Fields**:

| Field          | Type    | Required | Description                                      |
|----------------|---------|----------|--------------------------------------------------|
| bucket_name    | String  | Yes      | Target S3 bucket name                            |
| bucket_prefix  | String  | No       | S3 object prefix (default: "ROSA/cluster-logs/") |

### 4. Application Groups

**Purpose**: Pre-defined application groups simplify filtering configuration for common sets of related applications.

**Available Groups**:

| Group Name         | Applications                                                                          |
|--------------------|---------------------------------------------------------------------------------------|
| `API`              | `kube-apiserver`, `openshift-apiserver`                                              |
| `Authentication`   | `oauth-server`, `oauth-apiserver`                                                    |
| `Controller Manager` | `kube-controller-manager`, `openshift-controller-manager`, `openshift-route-controller-manager` |
| `Scheduler`        | `kube-scheduler`                                                                      |

**Usage**:
- Groups are specified in the `groups` field as a list of group names
- Group names are case-insensitive (`"API"`, `"api"`, and `"Api"` are equivalent)
- Application matching is case-sensitive (must match exact application names)
- Applications from groups are combined with applications from `desired_logs`
- Duplicates are automatically filtered out
- Invalid group names log warnings but don't cause errors

**Example Configuration**:
```json
{
  "tenant_id": "acme-corp",
  "type": "cloudwatch",
  "enabled": true,
  "desired_logs": ["custom-app-1", "custom-app-2"],
  "groups": ["API", "Authentication"],
  "target_region": "us-east-1",
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp"
}
```

This configuration will process logs from:
- `custom-app-1` and `custom-app-2` (from `desired_logs`)
- `kube-apiserver` and `openshift-apiserver` (from `API` group)
- `oauth-server` and `oauth-apiserver` (from `Authentication` group)

### 5. API Layer

**Technology**: FastAPI with Pydantic validation

**Endpoints**:
- `GET /tenants/{tenant_id}/delivery-configs` - List all delivery configurations
- `GET /tenants/{tenant_id}/delivery-configs/{type}` - Get specific configuration
- `POST /tenants/{tenant_id}/delivery-configs` - Create new configuration
- `PUT /tenants/{tenant_id}/delivery-configs/{type}` - Update configuration
- `DELETE /tenants/{tenant_id}/delivery-configs/{type}` - Delete configuration
- `PATCH /tenants/{tenant_id}/delivery-configs/{type}` - Partial update

## Delivery Methods

### CloudWatch Logs Delivery

**Flow**:
1. Processor assumes Central Log Distribution Role
2. Central Role assumes Customer Log Distribution Role (double-hop)
3. Vector subprocess delivers logs to CloudWatch Logs API
4. Logs are batched and delivered with proper timestamps

**Authentication**:
```
Lambda/Container → Central Role → Customer Role → CloudWatch Logs
```

**Configuration Example**:
```json
{
  "tenant_id": "acme-corp",
  "type": "cloudwatch",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service"],
  "groups": ["API", "Scheduler"],
  "target_region": "us-east-1",
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp"
}
```

### S3 Delivery

**Flow**:
1. Processor assumes Central Log Distribution Role (single-hop)
2. Central Role performs S3-to-S3 copy operation
3. Destination object includes bucket-owner-full-control ACL
4. Custom metadata added for traceability

**Authentication**:
```
Lambda/Container → Central Role → S3 Copy Operation
```

**Object Path Structure**:
```
{bucket_prefix}{tenant_id}/{cluster_id}/{application}/{pod_name}/{filename}
```

**Configuration Example**:
```json
{
  "tenant_id": "acme-corp",
  "type": "s3",
  "enabled": true,
  "desired_logs": [],
  "groups": ["Controller Manager"],
  "target_region": "us-east-1",
  "bucket_name": "acme-corp-logs",
  "bucket_prefix": "ROSA/cluster-logs/"
}
```

**Customer S3 Bucket Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowWriteToClusterLogs",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CENTRAL-ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXX"
      },
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::customer-bucket/ROSA/cluster-logs/*",
      "Condition": {
        "StringEquals": {
          "s3:x-amz-acl": "bucket-owner-full-control"
        }
      }
    }
  ]
}
```

## Multi-Destination Delivery

### Dual Delivery Support

The system supports multiple delivery configurations per tenant, enabling scenarios such as:

- **CloudWatch + S3**: Real-time monitoring via CloudWatch, long-term archival via S3
- **Multiple S3 Buckets**: Different buckets for different log types or retention policies
- **Regional Distribution**: Deliver to different regions based on compliance requirements

### Independent Configuration

Each delivery configuration operates independently:
- **Separate Filtering**: Different `desired_logs` per delivery type
- **Independent Enablement**: Enable/disable delivery types independently
- **Failure Isolation**: Failure in one delivery type doesn't affect others
- **Parallel Execution**: Multiple deliveries run concurrently for performance

### Example Multi-Configuration
```json
[
  {
    "tenant_id": "acme-corp",
    "type": "cloudwatch",
    "enabled": true,
    "desired_logs": ["critical-service"],
    "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
    "log_group_name": "/aws/logs/critical"
  },
  {
    "tenant_id": "acme-corp", 
    "type": "s3",
    "enabled": true,
    "desired_logs": [],
    "bucket_name": "acme-corp-archive",
    "bucket_prefix": "logs/archive/"
  }
]
```

## Security Model

### Role-Based Access Control

**Central Infrastructure Account**:
- **Central Log Distribution Role**: Single role trusted by all customer accounts
- **S3 Writer Role**: Vector uses this role for writing to central S3 bucket
- **Lambda/Container Execution Role**: Processor execution permissions

**Customer Account**:
- **Customer Log Distribution Role**: Grants CloudWatch Logs permissions
- **S3 Bucket Policy**: Grants S3 object write permissions to Central Role

### Authentication Flows

**CloudWatch Delivery (Double-Hop)**:
1. Processor assumes Central Role using execution role
2. Central Role assumes Customer Role using ExternalId validation
3. Customer Role credentials used for CloudWatch API calls

**S3 Delivery (Single-Hop)**:
1. Processor assumes Central Role using execution role
2. Central Role credentials used directly for S3 copy operation
3. Customer bucket policy allows Central Role write access

### Security Features

- **ExternalId Validation**: Customer roles require ExternalId matching central account ID
- **Regional Isolation**: Customer roles scoped to specific AWS regions
- **Least Privilege**: Minimal permissions with resource-specific restrictions
- **Audit Trail**: All role assumptions logged in CloudTrail
- **Encryption Support**: Both SSE-S3 and SSE-KMS encryption methods

## Data Flow

### Collection to Storage
1. **Vector Collection**: Kubernetes pods → Vector DaemonSet → Log parsing/enrichment
2. **Central Storage**: Vector → S3 Writer Role → Central S3 Bucket
3. **Event Notification**: S3 → SNS → SQS → Lambda/Container

### Processing to Delivery
1. **Event Processing**: SQS → Log Processor → Tenant configuration lookup
2. **Multi-Delivery**: For each enabled delivery configuration:
   - Application filtering based on desired_logs
   - Role assumption and credential management
   - Parallel delivery execution
3. **CloudWatch Path**: Processor → Vector subprocess → CloudWatch Logs API
4. **S3 Path**: Processor → S3 copy operation → Customer S3 bucket

## Performance Characteristics

### Throughput
- **Vector Collection**: ~20,000 events/second per node
- **S3 Write Batching**: 64MB batches / 5-minute intervals
- **Lambda Processing**: 10 SQS messages per invocation
- **Parallel Delivery**: Concurrent CloudWatch and S3 delivery

### Latency
- **End-to-End**: ~2-5 minutes from log generation to delivery
- **Vector Buffering**: 5-minute maximum batch timeout
- **SQS Processing**: Near real-time event processing
- **Single-Hop S3**: Reduced latency vs double-hop authentication

### Scalability
- **Horizontal Scaling**: Multiple processor instances supported
- **DynamoDB Performance**: Composite keys enable efficient queries
- **S3 Partitioning**: Tenant-based prefixes distribute load
- **Vector Memory**: 256Mi-2Gi per node based on log volume

## Cost Optimization

### Storage Costs
- **Direct S3 Writes**: Eliminates Kinesis Firehose costs (~$50/TB saved)
- **GZIP Compression**: ~30:1 compression ratio reduces storage
- **S3 Lifecycle Policies**: Automatic transition to cheaper storage classes
- **Intelligent Tiering**: Optimizes access patterns automatically

### Compute Costs
- **Lambda vs Container**: Choice based on log volume and processing patterns
- **Vector Efficiency**: Single agent per cluster reduces overhead
- **Batch Processing**: Reduces API call costs through aggregation
- **Regional Processing**: Avoid cross-region data transfer charges

### Operational Costs
- **Managed Services**: DynamoDB, Lambda, SQS reduce operational overhead
- **Monitoring Integration**: Native CloudWatch integration
- **Automated Scaling**: No manual capacity planning required

## Reliability and Monitoring

### Error Handling
- **Recoverable Errors**: Automatic retry with exponential backoff
- **Non-Recoverable Errors**: Removed from queue to prevent infinite loops
- **Partial Batch Failures**: Lambda partial batch failure responses
- **Dead Letter Queues**: Failed messages for investigation

### Monitoring
- **Vector Metrics**: Prometheus metrics via /api/v1/metrics endpoint
- **Processor Metrics**: CloudWatch metrics for success/failure rates
- **Infrastructure Metrics**: SQS queue depth, Lambda duration, DynamoDB performance
- **Custom Metrics**: Per-tenant delivery success rates

### High Availability
- **Multi-AZ Deployment**: DynamoDB and SQS are multi-AZ by default
- **Vector Redundancy**: DaemonSet ensures agent on every node
- **Lambda Scaling**: Automatic scaling based on SQS queue depth
- **Buffer Recovery**: Vector disk buffers survive pod restarts

## Future Enhancements

### Additional Delivery Types
- **Kafka**: Stream logs to Kafka topics
- **Webhook**: HTTP POST to customer endpoints
- **Elasticsearch**: Direct delivery to customer ES clusters
- **Custom Processors**: Plugin architecture for custom delivery logic

### Advanced Features
- **Log Transformation**: Customer-defined log parsing and enrichment
- **Real-time Filtering**: Stream processing for immediate alerting
- **Compliance Features**: Data residency, retention policies, audit logs
- **Cost Analytics**: Per-tenant cost tracking and optimization recommendations

### Performance Improvements
- **Vector Clustering**: Distribute load across multiple Vector instances
- **Smart Batching**: Dynamic batch sizes based on log patterns
- **Edge Processing**: Regional processing nodes for reduced latency
- **Caching Layer**: Cache delivery configurations for improved performance