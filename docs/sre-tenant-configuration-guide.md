# SRE Tenant Configuration Manual

This guide provides comprehensive instructions for Site Reliability Engineers (SREs) to manually configure tenant configurations in the multi-tenant logging pipeline DynamoDB table.

## Prerequisites

### Required Access
- **AWS Access**: SREs need the [log-delivery-prod-update-tenant-configs](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/aws/log-delivery-prod/roles/update-tenant-configs.yml?ref_type=heads) role
- **OCM CLI**: Access to OpenShift Cluster Manager for cluster information

### Customer Information Required
Before configuring a tenant, gather the following information from the customer onboarding process:

- **Cluster details**: Cluster ID and cluster name
- **Delivery types**: CloudWatch, S3, or both
- **For CloudWatch delivery**:
  - `log_distribution_role_arn`
  - `log_group_name`
- **For S3 delivery**:
  - `bucket_name`
  - `bucket_prefix` (optional)
- **Log filters**: Desired log types for example:
  - `kube-apiserver`
  - `openshift-apiserver`
  - `oauth-server`
  - `oauth-apiserver`
  - `kube-controller-manager`
  - `openshift-controller-manager`
  - `openshift-route-controller-manager`
  - `kube-scheduler`

## Setup Process

### 1. AWS Account Login

Install and use the Red Hat AWS SAML login tool:

```bash
# Install rh-aws-saml-login if not already installed
# See: https://github.com/app-sre/rh-aws-saml-login

rh-aws-saml-login log-delivery-prod
```

### 2. Set Customer Cluster Region

```bash
export AWS_REGION=$(ocm get cluster <cluster_id> | jq .region.id | tr -d '"')
echo "Using region: $AWS_REGION"
```

### 3. Verify CloudWatch Configuration (if applicable)

```bash
# Get the CentralLogDistributionRole ARN
CENTRAL_ROLE_ARN=$(aws iam list-roles | jq -r '.Roles[] | select(.RoleName | contains("CentralLogDistributionRole")) | .Arn')
echo "Central Role ARN: $CENTRAL_ROLE_ARN"

# Assume CentralLogDistributionRole
export $(printf "AWS_ACCESS_KEY_ID=%s AWS_SECRET_ACCESS_KEY=%s AWS_SESSION_TOKEN=%s" \
$(aws sts assume-role \
--role-arn $CENTRAL_ROLE_ARN \
--role-session-name RHVerify \
--query "Credentials.[AccessKeyId,SecretAccessKey,SessionToken]" \
--output text))

# Get current account ID for external-id
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Test customer's log distribution role assumption
export $(printf "AWS_ACCESS_KEY_ID=%s AWS_SECRET_ACCESS_KEY=%s AWS_SESSION_TOKEN=%s" \
$(aws sts assume-role \
--role-arn <log_distribution_role_arn> \
--role-session-name RHVerify \
--external-id $ACCOUNT_ID \
--query "Credentials.[AccessKeyId,SecretAccessKey,SessionToken]" \
--output text))

# Verify CloudWatch log group exists and check region
aws logs describe-log-groups --log-group-name-prefix <log_group_name>
```

**CloudWatch Log Group Response Interpretation:**

- **Log group doesn't exist:**
  ```json
  {
      "logGroups": []
  }
  ```
If the log group doesn't exist, contact the customer to create it.

- **Log group exists:**
  ```json
  {
      "logGroups": [
          {
              "logGroupName": "cw-log-delivery",
              "arn": "arn:aws:logs:us-east-1:123456789012:log-group:cw-log-delivery:*",
              ...
          }
      ]
  }
  ```

**Important:** Verify that the region in the ARN (`arn:aws:logs:us-east-1:...`) matches the cluster region. If they don't match, ask the customer to create the log group in the correct region.

**Re-login after verification:**
```bash
rh-aws-saml-login log-delivery-prod
```

### 4. Verify S3 Configuration (if applicable)

Check if the bucket exists and verify its region matches the cluster region:

```bash
curl -sI https://<bucket_name>.s3.amazonaws.com
```

**S3 Bucket Response Interpretation:**

- **HTTP 404 Not Found**: Bucket doesn't exist - contact customer to create it
  ```
  HTTP/1.1 404 Not Found
  x-amz-request-id: STETV4PW25TJQRYQ
  ```

- **HTTP 403 Forbidden**: Bucket exists but no access (This is expected) - check the `x-amz-bucket-region` header
  ```
  HTTP/1.1 403 Forbidden
  x-amz-bucket-region: us-east-2
  x-amz-request-id: PDZ4S49SQG7NS00Z
  ```

**Important:** The bucket region (`x-amz-bucket-region`) must match the cluster region. If they don't match, ask the customer to create a bucket in the correct region.

## Configuration Overview

The tenant configuration system supports two delivery types:
- **CloudWatch Logs**: Delivers logs to customer CloudWatch log groups
- **S3**: Delivers logs to customer S3 buckets

Each tenant can have multiple delivery configurations (both CloudWatch and S3) active simultaneously.

## DynamoDB Table Schema

The tenant configurations table uses a composite primary key:

| Attribute | Type | Description |
|-----------|------|-------------|
| `tenant_id` (PK) | String | Unique tenant identifier |
| `type` (SK) | String | Delivery type: `cloudwatch` or `s3` |
| `enabled` | Boolean | Whether this configuration is active |
| Additional attributes | Varies | Delivery-specific configuration |

## CloudWatch Logs Configuration

### Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `tenant_id` | Yes | Unique customer identifier | `ocm-production-<cluster_id>-<cluster_name>` |
| `type` | Yes | Must be `cloudwatch` | `cloudwatch` |
| `log_distribution_role_arn` | Yes | Customer's log distribution role ARN | `arn:aws:iam::123456789012:role/CustomerLogDistribution-RH` |
| `log_group_name` | Yes | Target CloudWatch log group | `cw-log-delivery` |
| `target_region` | Yes | AWS region for log delivery | `us-east-1` |
| `enabled` | Yes | Configuration active status | `true` |
| `desired_logs` | Yes | Application filter list | `["kube-apiserver", "openshift-apiserver"]` |

### Example Configuration

```bash
aws dynamodb put-item \
  --table-name hcp-log-prod-tenant-configs \
  --item '{
    "tenant_id": {"S": "ocm-production-clusterid-clustername"},
    "type": {"S": "cloudwatch"},
    "log_distribution_role_arn": {"S": "arn:aws:iam::123456789012:role/CustomerLogDistribution-RH"},
    "log_group_name": {"S": "cw-log-delivery"},
    "target_region": {"S": "us-east-1"},
    "enabled": {"BOOL": true},
    "desired_logs": {"SS": ["kube-apiserver", "openshift-apiserver"]}
  }'
```

## S3 Configuration

### Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `tenant_id` | Yes | Unique customer identifier | `ocm-production-<cluster_id>-<cluster_name>` |
| `type` | Yes | Must be `s3` | `s3` |
| `bucket_name` | Yes | Target S3 bucket name | `customer-logs-bucket` |
| `bucket_prefix` | Optional | S3 key prefix for logs | `logs/` |
| `target_region` | Yes | AWS region for S3 bucket | `us-east-1` |
| `enabled` | Yes | Configuration active status | `true` |
| `desired_logs` | Yes | Application filter list | `["kube-apiserver", "openshift-apiserver"]` |

### Example Configuration

```bash
aws dynamodb put-item \
  --table-name hcp-log-prod-tenant-configs \
  --item '{
    "tenant_id": {"S": "ocm-production-clusterid-clustername"},
    "type": {"S": "s3"},
    "bucket_name": {"S": "customer-enterprise-logging"},
    "bucket_prefix": {"S": "openshift/prod-clusters/"},
    "target_region": {"S": "us-west-2"},
    "enabled": {"BOOL": true},
    "desired_logs": {"SS": ["kube-apiserver", "openshift-apiserver"]}
  }'
```

## Configuration Management

### List All Configurations

```bash
# List all tenant configurations
aws dynamodb scan \
  --table-name hcp-log-prod-tenant-configs \
  --output json
```

### Query Specific Tenant

```bash
# Get all configurations for a specific tenant
aws dynamodb query \
  --table-name hcp-log-prod-tenant-configs \
  --key-condition-expression "tenant_id = :tenant_id" \
  --expression-attribute-values '{":tenant_id":{"S":"ocm-production-clusterid-clustername"}}' \
  --output json

# Get specific delivery type for a tenant
aws dynamodb get-item \
  --table-name hcp-log-prod-tenant-configs \
  --key '{"tenant_id":{"S":"ocm-production-clusterid-clustername"},"type":{"S":"cloudwatch"}}' \
  --output json
```

### Update Configurations

#### Enable/Disable Configuration

```bash
# Disable a configuration
aws dynamodb update-item \
  --table-name hcp-log-prod-tenant-configs \
  --key '{"tenant_id":{"S":"ocm-production-clusterid-clustername"},"type":{"S":"cloudwatch"}}' \
  --update-expression "SET enabled = :val" \
  --expression-attribute-values '{":val":{"BOOL":false}}'

# Re-enable a configuration
aws dynamodb update-item \
  --table-name hcp-log-prod-tenant-configs \
  --key '{"tenant_id":{"S":"ocm-production-clusterid-clustername"},"type":{"S":"cloudwatch"}}' \
  --update-expression "SET enabled = :val" \
  --expression-attribute-values '{":val":{"BOOL":true}}'
```

#### Update Application Filters

```bash
# Update desired_logs filter
aws dynamodb update-item \
  --table-name hcp-log-prod-tenant-configs \
  --key '{"tenant_id":{"S":"ocm-production-clusterid-clustername"},"type":{"S":"cloudwatch"}}' \
  --update-expression "SET desired_logs = :logs" \
  --expression-attribute-values '{":logs":{"SS":["kube-apiserver","openshift-apiserver","oauth-server"]}}'
```

#### Update Target Configuration

```bash
# Update CloudWatch log group
aws dynamodb update-item \
  --table-name hcp-log-prod-tenant-configs \
  --key '{"tenant_id":{"S":"ocm-production-clusterid-clustername"},"type":{"S":"cloudwatch"}}' \
  --update-expression "SET log_group_name = :group" \
  --expression-attribute-values '{":group":{"S":"new-log-group-name"}}'

# Update S3 bucket prefix
aws dynamodb update-item \
  --table-name hcp-log-prod-tenant-configs \
  --key '{"tenant_id":{"S":"ocm-production-clusterid-clustername"},"type":{"S":"s3"}}' \
  --update-expression "SET bucket_prefix = :prefix" \
  --expression-attribute-values '{":prefix":{"S":"new/prefix/path/"}}'
```

### Delete Configuration

```bash
# Delete specific delivery configuration
aws dynamodb delete-item \
  --table-name hcp-log-prod-tenant-configs \
  --key '{"tenant_id":{"S":"ocm-production-clusterid-clustername"},"type":{"S":"s3"}}'
```

## Monitoring and Troubleshooting

### Check Lambda Processing Logs

```bash
# Check recent Lambda executions (Linux)
aws logs filter-log-events \
  --log-group-name "/aws/lambda/hcp-log-prod-log-distributor" \
  --filter-pattern "<cluster_id>" \
  --start-time $(date -d '1 hour ago' +%s)000

# Alternative for macOS
aws logs filter-log-events \
  --log-group-name "/aws/lambda/hcp-log-prod-log-distributor" \
  --filter-pattern "<cluster_id>" \
  --start-time $(date -v-1H +%s)000
```

### Monitoring Dashboard

Access the Grafana dashboard for comprehensive monitoring:

**Hypershift Log Forwarding Dashboard:**  
https://grafana.app-sre.devshift.net/d/fez5435mhhibka/hypershift-log-forwarding

## Additional Resources

For additional support and troubleshooting, refer to:
- [Deployment Guide](deployment-guide.md)
- [Development Guide](../CLAUDE.md)  
- [Troubleshooting Guide](troubleshooting.md)
