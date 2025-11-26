# Local Multi-Account Testing with LocalStack

This Terraform configuration **reuses your existing modules** and sets up a multi-account environment in LocalStack.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Central Account (111111111111)                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Existing Modules (Reused!)                          │   │
│  │  • core-infrastructure (S3, DynamoDB, SNS)          │   │
│  │  • sqs-stack (SQS, Dead Letter Queue)               │   │
│  │  • Lambda (log-processor:local image)               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  Central Role: AssumeRole → Customer Accounts               │
└──────────────────────────┬───────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│ Customer 1     │  │ Customer 2     │  │ Customer N     │
│ (222222222222) │  │ (333333333333) │  │ (...)          │
│                │  │                │  │                │
│ • S3 Bucket    │  │ • S3 Bucket    │  │ • S3 Bucket    │
│ • IAM Role     │  │ • IAM Role     │  │ • IAM Role     │
│ • CloudWatch   │  │ • CloudWatch   │  │ • CloudWatch   │
└────────────────┘  └────────────────┘  └────────────────┘
```

## What's Reused from Your Existing Terraform

✅ **`modules/regional/modules/core-infrastructure`** - S3, DynamoDB, SNS, KMS
✅ **`modules/regional/modules/sqs-stack`** - SQS queues and subscriptions
✅ **IAM patterns** from your CloudFormation customer role template

## Prerequisites

1. **LocalStack running**:
   ```bash
   docker compose up -d
   ```

2. **Container image built**:
   ```bash
   cd container
   docker build -f Containerfile.processor-t log-processor:local .
   ```

3. **Terraform installed**

## Deploy

```bash
cd terraform/local

# Initialize
terraform init

# Plan
terraform plan

# Apply
terraform apply
```

## Test Cross-Account Flow

After deployment, Terraform outputs test commands. Here's the flow:

### 1. Upload a log to central bucket (ACME Corp namespace)

```bash
echo '{"timestamp":"2024-01-01T12:00:00Z","message":"Payment processed","amount":100}' | \
  gzip > test.json.gz

aws --endpoint-url=http://localhost:4566 s3 cp test.json.gz \
  s3://$(terraform output -raw central_source_bucket)/test-cluster/acme-corp/payment-service/pod-1/test-$(date +%s).json.gz
```

This triggers: **S3 → SNS → SQS → Lambda**

### 2. Lambda assumes role in customer account and delivers logs

Watch Lambda logs:
```bash
aws --endpoint-url=http://localhost:4566 logs tail \
  /aws/lambda/$(terraform output -raw central_lambda_function) --follow
```

### 3. Check customer bucket (cross-account!)

```bash
# View as customer account
AWS_ACCESS_KEY_ID=$(terraform output -raw customer1_account_id) \
  aws --endpoint-url=http://localhost:4566 \
  s3 ls s3://$(terraform output -raw customer1_bucket)/logs/ --recursive
```

### 4. Manually test AssumeRole

```bash
# Central account assumes customer role
AWS_ACCESS_KEY_ID=$(terraform output -raw central_account_id) \
  aws --endpoint-url=http://localhost:4566 \
  sts assume-role \
  --role-arn $(terraform output -raw customer1_role_arn) \
  --role-session-name test \
  --external-id $(terraform output -raw central_account_id)
```

## Account Structure

| Account | ID | Purpose | Resources |
|---------|-----|---------|-----------|
| Central | `111111111111` | Log processing | S3, SNS, SQS, Lambda, DynamoDB |
| ACME Corp | `222222222222` | Customer 1 | S3 bucket, IAM role, CloudWatch |
| Globex | `333333333333` | Customer 2 | S3 bucket, IAM role, CloudWatch |

## Tenant Configurations

Stored in central DynamoDB:

| Tenant | Type | Destination | Filters |
|--------|------|-------------|---------|
| `acme-corp` | S3 | Customer 1 account | `payment-service`, `user-database` |
| `globex-industries` | S3 | Customer 2 account | All logs |
| `test-tenant` | S3 | Central account | All logs |

## Testing Different Scenarios

### Test filtering (desired_logs)

```bash
# This WILL be delivered (payment-service is in desired_logs)
aws --endpoint-url=http://localhost:4566 s3 cp test.json.gz \
  s3://$(terraform output -raw central_source_bucket)/test-cluster/acme-corp/payment-service/pod-1/log.json.gz

# This will be FILTERED OUT (random-app not in desired_logs)
aws --endpoint-url=http://localhost:4566 s3 cp test.json.gz \
  s3://$(terraform output -raw central_source_bucket)/test-cluster/acme-corp/random-app/pod-1/log.json.gz
```

### Test multiple customers

```bash
# Globex Industries (different account, different bucket)
aws --endpoint-url=http://localhost:4566 s3 cp test.json.gz \
  s3://$(terraform output -raw central_source_bucket)/test-cluster/globex-industries/api-gateway/pod-1/log.json.gz

# Check Globex's bucket
AWS_ACCESS_KEY_ID=$(terraform output -raw customer2_account_id) \
  aws --endpoint-url=http://localhost:4566 \
  s3 ls s3://$(terraform output -raw customer2_bucket)/platform-logs/ --recursive
```

## Troubleshooting

### Cross-account access not working?

LocalStack Community has this limitation note:
> "multi-accounts may not work for use-cases that have cross-account and cross-service access"

If AssumeRole doesn't properly enforce permissions:

1. **Check if resources are isolated by account**:
   ```bash
   # As central account - should NOT see customer bucket
   AWS_ACCESS_KEY_ID=111111111111 aws --endpoint-url=http://localhost:4566 s3 ls

   # As customer account - should see their bucket
   AWS_ACCESS_KEY_ID=222222222222 aws --endpoint-url=http://localhost:4566 s3 ls
   ```

2. **Check STS AssumeRole response** - even if it doesn't enforce, it should return credentials

3. **If enforcement fails**, your code can detect LocalStack and skip AssumeRole:
   ```go
   if os.Getenv("AWS_ENDPOINT_URL") != "" {
       // LocalStack: use current credentials
   } else {
       // AWS: assume role
   }
   ```

## Clean Up

```bash
terraform destroy
```

## Next Steps

Once this works in LocalStack, you know your Terraform modules work correctly and can deploy to real AWS with confidence!
