# Migration Guide: Terraform to CloudFormation

This guide provides step-by-step instructions for migrating from the existing Terraform infrastructure to the new CloudFormation nested stack architecture.

## Overview

The migration involves:
- Converting 53 Terraform resources across 8 files to 4 CloudFormation nested stacks
- Preserving all existing functionality and configurations
- Maintaining zero downtime during the migration
- Ensuring data integrity and security

## Pre-Migration Checklist

### 1. Backup Current Infrastructure
```bash
# Export current Terraform state
cd terraform/
terraform show > terraform-state-backup.txt

# Document current resource identifiers
terraform output > terraform-outputs.txt

# Backup S3 data
aws s3 sync s3://your-central-logging-bucket s3://your-backup-bucket/migration-backup/
```

### 2. Verify Current State
```bash
# Check Terraform state is clean
terraform plan

# Verify all resources are healthy
terraform refresh
```

### 3. Prepare CloudFormation Environment
```bash
# Create S3 bucket for CloudFormation templates
aws s3 mb s3://your-cloudformation-templates-bucket

# Ensure you have appropriate permissions
aws iam get-user
```

## Migration Strategy

### Option A: Blue-Green Migration (Recommended)
Deploy new CloudFormation stack alongside existing Terraform infrastructure, then switch traffic.

### Option B: In-Place Migration
Import existing resources into CloudFormation stack.

## Step-by-Step Migration (Blue-Green)

### Step 1: Deploy CloudFormation Stack
```bash
cd cloudformation/

# Validate templates
./deploy.sh -b your-cloudformation-templates-bucket --validate-only

# Deploy to staging environment first
./deploy.sh -e staging -b your-cloudformation-templates-bucket

# Deploy to production
./deploy.sh -e production -b your-cloudformation-templates-bucket
```

### Step 2: Update Vector Configuration
Update the Vector configuration to point to the new Firehose stream:

```yaml
# k8s/vector-config.yaml
sinks:
  firehose:
    inputs:
      - logs_processed
    type: aws_kinesis_firehose
    stream_name: "multi-tenant-logging-production-stream"  # New stream name
    region: "us-east-1"
    encoding:
      codec: json
```

### Step 3: Update Lambda Function Code
Replace the Lambda function code with the new version:

```bash
# Package new Lambda code
cd lambda/
zip -r log_distributor_new.zip . -x "*.pyc" "__pycache__/*"

# Update Lambda function
aws lambda update-function-code \
  --function-name multi-tenant-logging-production-log-distributor \
  --zip-file fileb://log_distributor_new.zip
```

### Step 4: Update Tenant Configurations
Migrate tenant configurations to the new DynamoDB table:

```bash
# Export from old table
aws dynamodb scan \
  --table-name tenant-configurations \
  --output json > tenant-configs-export.json

# Import to new table
aws dynamodb batch-write-item \
  --request-items file://tenant-configs-import.json
```

### Step 5: Switch Traffic
1. Update DNS/load balancer to point to new infrastructure
2. Monitor logs and metrics
3. Verify all tenants are receiving logs

### Step 6: Validate Migration
```bash
# Check CloudFormation stack status
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-production

# Verify metrics in CloudWatch
aws cloudwatch get-metric-statistics \
  --namespace AWS/Kinesis/Firehose \
  --metric-name DeliveryToS3.Records \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T01:00:00Z \
  --period 300 \
  --statistics Sum \
  --dimensions Name=DeliveryStreamName,Value=multi-tenant-logging-production-stream
```

### Step 7: Cleanup Terraform Resources
Once migration is verified successful:

```bash
# Destroy Terraform infrastructure
cd terraform/
terraform destroy
```

## Step-by-Step Migration (In-Place)

### Step 1: Prepare Resource Import
```bash
# Generate import script
cat > import-resources.sh << 'EOF'
#!/bin/bash

# Import existing resources into CloudFormation
aws cloudformation import-stack-resources-to-stack \
  --stack-name multi-tenant-logging-production \
  --resources-to-import file://resources-to-import.json
EOF

chmod +x import-resources.sh
```

### Step 2: Create Resource Import File
```json
{
  "ResourcesToImport": [
    {
      "ResourceType": "AWS::S3::Bucket",
      "LogicalResourceId": "CentralLoggingBucket",
      "ResourceIdentifier": {
        "BucketName": "central-logging-abcd1234"
      }
    },
    {
      "ResourceType": "AWS::DynamoDB::Table",
      "LogicalResourceId": "TenantConfigTable",
      "ResourceIdentifier": {
        "TableName": "tenant-configurations"
      }
    }
  ]
}
```

### Step 3: Execute Import
```bash
# Deploy stack with import
./deploy.sh -b your-cloudformation-templates-bucket --import-resources

# Verify import was successful
aws cloudformation describe-stack-resources \
  --stack-name multi-tenant-logging-production
```

## Post-Migration Tasks

### 1. Update Documentation
- Update README.md with CloudFormation deployment instructions
- Update CLAUDE.md with new resource names and ARNs
- Update monitoring runbooks

### 2. Test Disaster Recovery
```bash
# Test stack recreation
aws cloudformation delete-stack --stack-name multi-tenant-logging-staging
./deploy.sh -e staging -b your-cloudformation-templates-bucket
```

### 3. Set Up Monitoring
```bash
# Configure CloudWatch alarms
aws cloudwatch put-metric-alarm \
  --alarm-name "CloudFormation-Stack-Drift" \
  --alarm-description "Detect stack drift" \
  --metric-name StackDriftDetectionStatus \
  --namespace AWS/CloudFormation \
  --statistic Maximum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold
```

## Resource Mapping

### Terraform → CloudFormation Mapping

| Terraform Resource | CloudFormation Resource | Stack Location |
|-------------------|-------------------------|----------------|
| `aws_s3_bucket.central_logging` | `CentralLoggingBucket` | core-infrastructure.yaml |
| `aws_dynamodb_table.tenant_configurations` | `TenantConfigTable` | core-infrastructure.yaml |
| `aws_kinesis_firehose_delivery_stream.central_logging` | `FirehoseDeliveryStream` | kinesis-stack.yaml |
| `aws_lambda_function.log_distributor` | `LogDistributorFunction` | lambda-stack.yaml |
| `aws_sqs_queue.log_delivery` | `LogDeliveryQueue` | monitoring-stack.yaml |
| `aws_sns_topic.log_delivery_hub` | `LogDeliveryHubTopic` | monitoring-stack.yaml |
| `aws_cloudwatch_dashboard.main` | `MonitoringDashboard` | monitoring-stack.yaml |
| `aws_iam_role.firehose_role` | `FirehoseRole` | core-infrastructure.yaml |
| `aws_iam_role.log_distributor_role` | `LogDistributorRole` | core-infrastructure.yaml |
| `aws_kms_key.logging_key` | `LoggingKMSKey` | core-infrastructure.yaml |

## Rollback Plan

If migration fails:

### 1. Immediate Rollback
```bash
# Switch traffic back to Terraform infrastructure
# Update Vector configuration
kubectl apply -f k8s/vector-config-terraform.yaml

# Restore Lambda function
aws lambda update-function-code \
  --function-name log-distributor \
  --zip-file fileb://log_distributor_terraform.zip
```

### 2. Data Recovery
```bash
# Restore from backup if needed
aws s3 sync s3://your-backup-bucket/migration-backup/ s3://your-central-logging-bucket/

# Restore DynamoDB table
aws dynamodb restore-table-from-backup \
  --target-table-name tenant-configurations \
  --backup-arn arn:aws:dynamodb:us-east-1:123456789012:table/tenant-configurations/backup/01234567890123-abcd1234
```

### 3. Cleanup Failed Migration
```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name multi-tenant-logging-production

# Clean up S3 templates
aws s3 rm s3://your-cloudformation-templates-bucket/cloudformation/ --recursive
```

## Troubleshooting

### Common Issues

1. **Resource Name Conflicts**
   - Solution: Use different naming conventions or regions during migration

2. **IAM Permission Errors**
   - Solution: Ensure CloudFormation has necessary permissions for all resource types

3. **Parameter Validation Failures**
   - Solution: Review parameter constraints and defaults

4. **Stack Creation Timeouts**
   - Solution: Check resource dependencies and increase timeout values

### Validation Commands

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name multi-tenant-logging-production

# Check for drift
aws cloudformation detect-stack-drift --stack-name multi-tenant-logging-production

# Validate resource health
aws cloudformation describe-stack-resources --stack-name multi-tenant-logging-production
```

## Support and Contacts

For migration support:
- Infrastructure Team: infrastructure@company.com
- On-call Support: +1-555-ON-CALL
- Documentation: https://internal-wiki.company.com/cloudformation-migration

## Post-Migration Validation Checklist

- [ ] All CloudFormation stacks deployed successfully
- [ ] Vector agents sending logs to new Firehose stream
- [ ] Lambda functions processing logs correctly
- [ ] DynamoDB table contains all tenant configurations
- [ ] CloudWatch dashboards showing metrics
- [ ] Alarms configured and functioning
- [ ] Cost monitoring active
- [ ] Security groups and IAM roles properly configured
- [ ] Cross-account access working for all tenants
- [ ] Backup and recovery procedures tested
- [ ] Documentation updated
- [ ] Team trained on new deployment process
- [ ] Monitoring and alerting verified
- [ ] Terraform infrastructure decommissioned