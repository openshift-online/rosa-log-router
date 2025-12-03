# Troubleshooting Guide

This guide covers common issues, debugging techniques, and solutions for the multi-tenant logging pipeline.

## Quick Diagnostic Commands

### LocalStack Health Check (Development)
```bash
# Check LocalStack status
curl http://localhost:4566/_localstack/health

# View LocalStack logs
make logs

# Check Terraform state
cd terraform/local && terraform show

# Verify deployed resources
cd terraform/local && terraform state list
```

### Infrastructure Health Check (Production)
```bash
# Check S3 bucket
aws s3 ls s3://YOUR-CENTRAL-BUCKET/

# Check DynamoDB table
aws dynamodb describe-table \
  --table-name YOUR-TENANT-CONFIG-TABLE

# List IAM roles
aws iam list-roles --query 'Roles[?contains(RoleName, `log`)].RoleName'
```

### Vector Health Check (Cluster Deployments)
```bash
# Check Vector pod status
kubectl get pods -n logging
kubectl describe daemonset vector-logs -n logging

# Check Vector logs for errors
kubectl logs -n logging daemonset/vector-logs --tail=100

# Check Vector metrics endpoint
kubectl port-forward -n logging daemonset/vector-logs 8686:8686
curl http://localhost:8686/metrics
```

### Processing Pipeline Health Check (LocalStack)
```bash
# Check tenant configurations
TABLE_NAME=$(cd terraform/local && terraform output -raw central_dynamodb_table)
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name $TABLE_NAME

# List S3 buckets and contents
aws --endpoint-url=http://localhost:4566 s3 ls
aws --endpoint-url=http://localhost:4566 s3 ls s3://central-source-logs/ --recursive

# Run integration tests
make test-e2e
```

## Common Issues and Solutions

### 1. Vector Not Sending Logs

#### Symptoms
- No files appearing in S3 bucket
- Vector pods running but no metrics
- Empty Vector logs

#### Diagnostics
```bash
# Check Vector configuration
kubectl get configmap vector-config -n logging -o yaml

# Check Vector pod logs
kubectl logs -n logging daemonset/vector-logs

# Check IRSA configuration
kubectl describe serviceaccount vector -n logging

# Test S3 access manually
aws s3 ls s3://$S3_BUCKET_NAME/ --profile $AWS_PROFILE
```

#### Common Causes and Solutions

**IAM Role Permissions**
```bash
# Verify S3WriterRole exists and has correct permissions
aws iam get-role --role-name multi-tenant-logging-${ENVIRONMENT}-central-s3-writer-role

# Check trust policy allows OIDC provider
aws iam get-role --role-name multi-tenant-logging-${ENVIRONMENT}-central-s3-writer-role \
  --query 'Role.AssumeRolePolicyDocument' --output json
```

**Vector Configuration Issues**
```bash
# Check environment variables in Vector config
kubectl get configmap vector-config -n logging -o yaml | grep -E "(AWS_REGION|S3_BUCKET_NAME|S3_WRITER_ROLE_ARN|CLUSTER_ID)"

# Verify S3 bucket exists and is accessible
aws s3api head-bucket --bucket "$S3_BUCKET_NAME"
```

**Namespace Filtering Issues**
```bash
# Check if namespaces have required labels
kubectl get namespaces -l "hypershift.openshift.io/hosted-control-plane"

# Verify Vector is collecting from correct namespaces
kubectl logs -n logging daemonset/vector-logs | grep "namespace"
```

### 2. Lambda Function Errors

#### Symptoms
- SQS messages not being processed
- High error rates in CloudWatch metrics
- Tenant logs not delivered to CloudWatch

#### Diagnostics
```bash
# Check Lambda function logs
aws logs describe-log-streams \
  --log-group-name "/aws/lambda/multi-tenant-logging-${ENVIRONMENT}-log-distributor" \
  --order-by LastEventTime --descending

# Get recent Lambda errors
aws logs filter-log-events \
  --log-group-name "/aws/lambda/multi-tenant-logging-${ENVIRONMENT}-log-distributor" \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000
```

#### Common Causes and Solutions

**DynamoDB Permission Issues**
```bash
# Check if tenant configuration table exists
aws dynamodb describe-table \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs

# Test Lambda role can access DynamoDB
aws dynamodb scan \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --select "COUNT"
```

**Cross-Account Role Assumption Failures**
```bash
# Check if central role can assume customer roles
aws sts assume-role \
  --role-arn "arn:aws:iam::CUSTOMER-ACCOUNT:role/CustomerLogDistribution-us-east-1" \
  --role-session-name "test-assumption" \
  --external-id "$AWS_ACCOUNT_ID"
```

**Container Image Issues**
```bash
# Verify ECR image exists and is accessible
aws ecr describe-images \
  --repository-name log-processor \
  --image-ids imageTag=latest

# Check Lambda function configuration
aws lambda get-function-configuration \
  --function-name multi-tenant-logging-${ENVIRONMENT}-log-distributor
```

### 3. Tenant Configuration Issues

#### Symptoms
- Tenant logs not being processed
- "Tenant not found" errors in Lambda logs
- Logs processed but not delivered

#### Diagnostics
```bash
# Check if tenant configuration exists
aws dynamodb get-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"},"type":{"S":"cloudwatch"}}'

# List all tenant configurations
aws dynamodb scan \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --projection-expression "tenant_id, #t, enabled" \
  --expression-attribute-names '{"#t": "type"}'
```

#### Common Causes and Solutions

**Tenant Disabled**
```bash
# Check if tenant is enabled
aws dynamodb get-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"},"type":{"S":"cloudwatch"}}' \
  --query 'Item.enabled.BOOL'

# Enable a tenant
aws dynamodb update-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"},"type":{"S":"cloudwatch"}}' \
  --update-expression "SET enabled = :val" \
  --expression-attribute-values '{":val":{"BOOL":true}}'
```

**Invalid Role ARN**
```bash
# Verify customer role exists and is accessible
aws sts assume-role \
  --role-arn "CUSTOMER_ROLE_ARN" \
  --role-session-name "validation-test" \
  --external-id "$AWS_ACCOUNT_ID"
```

**Application Filtering Issues**
```bash
# Check desired_logs configuration
aws dynamodb get-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"},"type":{"S":"cloudwatch"}}' \
  --query 'Item.desired_logs.SS'

# Verify application names match log entries
grep "application.*APPLICATION_NAME" recent_s3_log_file.json
```

### 4. High Costs

#### Symptoms
- Unexpectedly high AWS bills
- High S3 storage costs
- Excessive Lambda invocations

#### Diagnostics
```bash
# Check S3 bucket size and object count
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name BucketSizeBytes \
  --dimensions Name=BucketName,Value="$S3_BUCKET_NAME" Name=StorageType,Value=StandardStorage \
  --start-time $(date -d '24 hours ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 86400 \
  --statistics Average

# Check Lambda invocation count
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=multi-tenant-logging-${ENVIRONMENT}-log-distributor \
  --start-time $(date -d '24 hours ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 3600 \
  --statistics Sum
```

#### Cost Optimization Solutions

**Review Vector Batch Settings**
```yaml
# In Vector configuration, ensure efficient batching
batch:
  max_bytes: 67108864  # 64MB
  timeout_secs: 300    # 5 minutes
```

**Verify S3 Lifecycle Policies**
```bash
# Check if S3 lifecycle policies are active
aws s3api get-bucket-lifecycle-configuration \
  --bucket "$S3_BUCKET_NAME"

# Enable intelligent tiering if not already enabled
aws s3api put-bucket-intelligent-tiering-configuration \
  --bucket "$S3_BUCKET_NAME" \
  --id "EntireBucket" \
  --intelligent-tiering-configuration '{
    "Id": "EntireBucket",
    "Status": "Enabled",
    "Filter": {"Prefix": ""},
    "Tierings": [
      {"Days": 1, "AccessTier": "ARCHIVE_ACCESS"},
      {"Days": 90, "AccessTier": "DEEP_ARCHIVE_ACCESS"}
    ]
  }'
```

**Optimize Lambda Memory Allocation**
```bash
# Check current Lambda memory configuration
aws lambda get-function-configuration \
  --function-name multi-tenant-logging-${ENVIRONMENT}-log-distributor \
  --query 'MemorySize'

# Consider using SQS polling instead of Lambda for high-volume scenarios
# See deployment guide for container-based processing options
```

### 5. Container Build Issues

#### Symptoms
- Container builds failing
- ECR push failures
- Lambda function deployment errors

#### Diagnostics
```bash
# Test container build locally
cd container/
podman build -f Containerfile.collector -t log-collector:latest .
podman build -f Containerfile.processor_go -t log-processor:local .

# Test container run locally
podman run --rm log-processor:local /bin/bash -c "go version && vector --version"
```

#### Common Solutions

**Build Dependencies**
```bash
# Ensure base images are accessible
podman pull golang:1.24-alpine

# Clear build cache if needed
podman build --no-cache -f Containerfile.processor -t log-processor:local .
```

**ECR Authentication**
```bash
# Refresh ECR authentication
aws ecr get-login-password --region "$AWS_REGION" | \
  podman login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Verify ECR repository exists
aws ecr describe-repositories --repository-names log-processor
```

### 6. Kubernetes Deployment Issues

#### Symptoms
- Vector pods not starting
- Permission denied errors
- IRSA authentication failures

#### Diagnostics
```bash
# Check pod status and events
kubectl describe pods -n logging -l app=vector

# Check service account annotations
kubectl describe serviceaccount vector -n logging

# Verify RBAC permissions
kubectl auth can-i list pods --as=system:serviceaccount:logging:vector
```

#### Common Solutions

**OIDC Provider Issues**
```bash
# Verify OIDC provider exists in AWS
aws iam list-open-id-connect-providers

# Check cluster OIDC provider URL
kubectl get authentication.config.openshift.io cluster -o json | \
  jq -r .spec.serviceAccountIssuer
```

**SecurityContextConstraints (OpenShift)**
```bash
# Check if Vector SCC exists
kubectl get scc vector-scc

# Verify SCC is bound to service account
kubectl describe scc vector-scc
```

**ConfigMap Issues**
```bash
# Verify Vector ConfigMap has correct values
kubectl get configmap vector-config -n logging -o yaml

# Check for environment variable substitution issues
kubectl describe pod -n logging -l app=vector | grep -A 10 "Environment:"
```

### 7. Vector Namespace Bug (Issue #40)

#### Symptoms
- S3 paths with double slashes (e.g., `scuppett-oepz//hosted-cluster-config-operator/`)
- Empty namespace fields in log records
- Tenant ID detection failures

#### Diagnostics
```bash
# Check for files with empty namespaces
aws s3 ls s3://$S3_BUCKET_NAME/ --recursive | grep "//"

# Download and examine problematic log files
aws s3 cp s3://$S3_BUCKET_NAME/customer-id//application/pod/file.json.gz /tmp/
gunzip /tmp/file.json.gz
head -5 /tmp/file.json
```

#### Current Status
This is a known issue documented in [GitHub Issue #40](https://github.com/openshift-online/rosa-log-router/issues/40). The issue occurs when hosted-cluster-config-operator logs contain empty `"namespace":""` fields for node-level operations.

**Workaround**: The processor currently handles these cases, but S3 path structure remains malformed. A fix is planned for the Vector configuration.

## Performance Monitoring

### Key Metrics to Monitor

**Vector Metrics**
```bash
# Vector throughput metrics
kubectl port-forward -n logging daemonset/vector-logs 8686:8686
curl -s http://localhost:8686/metrics | grep vector_component_sent_events_total

# Vector error metrics
curl -s http://localhost:8686/metrics | grep vector_component_errors_total
```

**Lambda Metrics**
```bash
# Lambda duration and errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=multi-tenant-logging-${ENVIRONMENT}-log-distributor \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Average,Maximum

aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=multi-tenant-logging-${ENVIRONMENT}-log-distributor \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Sum
```

**S3 Metrics**
```bash
# S3 object count and size
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name NumberOfObjects \
  --dimensions Name=BucketName,Value="$S3_BUCKET_NAME" Name=StorageType,Value=AllStorageTypes \
  --start-time $(date -d '24 hours ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 3600 \
  --statistics Average
```

## Log Analysis Techniques

### Vector Log Analysis
```bash
# Check for Vector configuration errors
kubectl logs -n logging daemonset/vector-logs | grep -i error

# Monitor Vector restarts
kubectl get events -n logging --field-selector involvedObject.name=vector-logs

# Check Vector health endpoint
kubectl exec -n logging daemonset/vector-logs -- curl localhost:8686/health
```

### Lambda Log Analysis
```bash
# Search for specific error patterns
aws logs filter-log-events \
  --log-group-name "/aws/lambda/multi-tenant-logging-${ENVIRONMENT}-log-distributor" \
  --filter-pattern "{ $.level = \"ERROR\" }" \
  --start-time $(date -d '1 hour ago' +%s)000

# Check for timeout issues
aws logs filter-log-events \
  --log-group-name "/aws/lambda/multi-tenant-logging-${ENVIRONMENT}-log-distributor" \
  --filter-pattern "Task timed out" \
  --start-time $(date -d '1 hour ago' +%s)000
```

### S3 Log File Analysis
```bash
# Download recent log files for analysis
aws s3 ls s3://$S3_BUCKET_NAME/ --recursive | tail -10

# Analyze log structure
aws s3 cp s3://$S3_BUCKET_NAME/path/to/recent/file.json.gz /tmp/
gunzip /tmp/file.json.gz
jq '.timestamp, .message, .cluster_id, .namespace, .application' /tmp/file.json | head -20
```

## Emergency Procedures

### Stop Log Processing
```bash
# Disable Lambda function
aws lambda put-function-configuration \
  --function-name multi-tenant-logging-${ENVIRONMENT}-log-distributor \
  --reserved-concurrent-executions 0

# Scale down Vector (temporary)
kubectl scale daemonset vector-logs -n logging --replicas=0
```

### Emergency Tenant Disable
```bash
# Quickly disable a problematic tenant
aws dynamodb update-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --key '{"tenant_id":{"S":"PROBLEMATIC_TENANT"},"type":{"S":"cloudwatch"}}' \
  --update-expression "SET enabled = :val" \
  --expression-attribute-values '{":val":{"BOOL":false}}'
```

### Recover from SQS Message Buildup
```bash
# Check SQS queue depth
aws sqs get-queue-attributes \
  --queue-url "$SQS_QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages

# Temporarily increase Lambda concurrency
aws lambda put-function-configuration \
  --function-name multi-tenant-logging-${ENVIRONMENT}-log-distributor \
  --reserved-concurrent-execurrency 50

# Monitor processing rate
watch 'aws sqs get-queue-attributes --queue-url "$SQS_QUEUE_URL" --attribute-names ApproximateNumberOfMessages'
```

## Getting Help

### Useful Resources
- [Architecture Documentation](../DESIGN.md)
- [Development Guide](../CLAUDE.md)
- [Deployment Guide](deployment-guide.md)
- [GitHub Issues](https://github.com/openshift-online/rosa-log-router/issues)

### Support Escalation
1. **Gather diagnostic information** using commands above
2. **Check recent changes** to infrastructure or configuration
3. **Review CloudWatch logs** for error patterns
4. **Create GitHub issue** with full diagnostic output
5. **Include environment details** (region, cluster info, tenant IDs)

### Debug Information Collection
```bash
# Collect comprehensive diagnostic information
cat > debug-info.txt << EOF
=== Environment Information ===
AWS Region: $AWS_REGION
Environment: $ENVIRONMENT
Stack Name: multi-tenant-logging-${ENVIRONMENT}

=== Infrastructure Status (LocalStack) ===
$(curl -s http://localhost:4566/_localstack/health | jq -r '.services')

=== Infrastructure Status (Production) ===
$(aws dynamodb describe-table --table-name YOUR-TENANT-CONFIG-TABLE --query 'Table.TableStatus' 2>/dev/null || echo "N/A")

=== Vector Status ===
$(kubectl get pods -n logging)

=== SQS Queue Status ===
$(aws sqs get-queue-attributes --queue-url "$SQS_QUEUE_URL" --attribute-names All)

=== Recent Lambda Errors ===
$(aws logs filter-log-events --log-group-name "/aws/lambda/multi-tenant-logging-${ENVIRONMENT}-log-distributor" --filter-pattern "ERROR" --start-time $(date -d '1 hour ago' +%s)000 --max-items 10)
EOF

echo "Debug information saved to debug-info.txt"
```