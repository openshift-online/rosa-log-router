# Integration Tests for ROSA Log Router

This directory contains end-to-end integration tests for the multi-tenant log delivery pipeline. These tests verify the complete workflow from log upload to delivery in customer accounts via both S3 and CloudWatch Logs.

## Overview

The integration tests validate:
- **S3 delivery**: Logs uploaded to central bucket are delivered to customer S3 buckets
- **CloudWatch delivery**: Logs are delivered to customer CloudWatch Log Groups
- **Mixed delivery**: Both delivery types work concurrently for different customers
- **Concurrent processing**: Multiple customers can have logs processed simultaneously
- **Multi-tenant isolation**: Customer logs are properly isolated and routed

## Test Architecture

### Test Environment
- **LocalStack**: Simulates AWS services locally (S3, DynamoDB, CloudWatch Logs, IAM, STS)
- **Multi-account simulation**: Uses different AWS credentials as account namespaces
  - Central Account: `111111111111`
  - Customer 1 (ACME Corp): `222222222222`
  - Customer 2 (Globex): `333333333333`
- **Go container**: Runs in scan mode, periodically scanning central S3 bucket for new logs

### Test Customers
1. **ACME Corp** (`acme-corp`)
   - Delivery type: S3
   - Bucket: `acme-corp-logs`
   - Service: `payment-service`

2. **Globex Industries** (`globex-industries`)
   - Delivery types: S3 + CloudWatch Logs
   - S3 Bucket: `globex-industries-logs`
   - CloudWatch Log Group: `/aws/logs/globex-industries/application`
   - Service: `platform-api`

## Prerequisites

Before running integration tests, you need:

1. **LocalStack running**:
   ```bash
   make start
   ```

2. **Infrastructure deployed** - choose based on processor implementation:

   **Option A: Python Lambda (current production)**
   ```bash
   make deploy
   ```
   This deploys the Python Lambda function that processes logs via SQS triggers.

   **Option B: Go Processor in Scan Mode (for Go rewrite development)**
   ```bash
   make deploy-go  # Deploys infrastructure without Lambda
   ```

   Then in a separate terminal, run the Go processor in scan mode:
   ```bash
   make run-go-scan
   ```

   This starts the Go log processor in scan mode, which polls the central S3 bucket every 10 seconds.

   > **Note:** Running Go as a Lambda container image requires LocalStack Pro. The free version only supports scan mode for Go testing.

## Running Tests

### Run All Integration Tests
```bash
cd container
go test -tags=integration ./integration -v
```

### Run Specific Test
```bash
cd container
go test -tags=integration ./integration -run TestE2ES3Delivery -v
```

### Run With Custom Timeout
```bash
cd container
go test -tags=integration ./integration -v -timeout 5m
```

### Run From Project Root (using Makefile)
```bash
make test-e2e-go
```

## Test Cases

### 1. TestE2ES3Delivery
**Purpose**: Verify S3-to-S3 log delivery for Customer 1 (ACME Corp)

**Flow**:
1. Generate test log with unique UUID embedded in message
2. Upload to central bucket: `{cluster}/{tenant}/{service}/{pod}/{file}.json.gz`
3. Wait for Go container scan interval (20s includes buffer)
4. Verify log delivered to customer bucket with UUID intact

**Expected Result**: Log file appears in customer S3 bucket with UUID in content

### 2. TestE2ECloudWatchDelivery
**Purpose**: Verify CloudWatch Logs delivery for Customer 2 (Globex)

**Flow**:
1. Generate test log with unique UUID
2. Upload to central bucket
3. Wait for processing
4. Query CloudWatch Logs API for log events
5. Verify UUID found in delivered log message

**Expected Result**: Log event appears in CloudWatch with UUID in message

### 3. TestE2EMixedDelivery
**Purpose**: Verify both S3 and CloudWatch delivery work simultaneously

**Flow**:
1. Upload logs for both customers at the same time
2. Wait for processing
3. Verify both delivery types succeed

**Expected Result**: Both customers receive their logs via their configured delivery method

### 4. TestE2EConcurrentCustomers
**Purpose**: Verify multi-tenant isolation and concurrent processing

**Flow**:
1. Use `t.Parallel()` to run customer tests concurrently
2. Upload multiple logs for same customer
3. Verify all deliveries complete successfully

**Expected Result**: All logs delivered correctly with proper tenant isolation

## Test Helpers

The `helpers.go` file provides utilities:

### E2ETestHelper
Main test helper struct with AWS client configuration for LocalStack.

### Key Functions
- `NewE2ETestHelper(t)`: Creates configured test helper
- `GenerateTestLog(customer, service, pod)`: Generates test log with UUID
- `UploadTestLog(t, bucket, key, data)`: Uploads log to S3
- `WaitForS3Delivery(t, account, bucket, prefix, uuid, timeout)`: Polls for S3 delivery
- `WaitForCloudWatchDelivery(t, account, logGroup, stream, uuid, timeout)`: Polls for CloudWatch delivery
- `Cleanup(t)`: Cleanup after tests

## Configuration

### Constants (in e2e_test.go)
```go
CentralSourceBucket = "multi-tenant-logging-int-central-local"
Customer1Bucket     = "acme-corp-logs"
Customer2LogGroup   = "/aws/logs/globex-industries/application"
ProcessingWaitTime  = 20 * time.Second
```

### Environment Variables (helpers.go)
```go
LocalStackEndpoint  = "http://localhost:4566"
LocalStackRegion    = "us-east-1"
DefaultTimeout      = 30 * time.Second
```

## Troubleshooting

### Test Fails: "timeout waiting for S3 delivery"
**Cause**: Go container may not be running or processing logs

**Solutions**:
1. Check Go container is running: `docker ps | grep log-processor-go`
2. Check container logs: `docker logs <container-id>`
3. Verify LocalStack is running: `docker-compose ps`
4. Check central S3 bucket exists: `aws --endpoint-url=http://localhost:4566 s3 ls`

### Test Fails: "timeout waiting for CloudWatch delivery"
**Cause**: Log stream may not exist or delivery failed

**Solutions**:
1. Check log group exists:
   ```bash
   AWS_ACCESS_KEY_ID=333333333333 aws --endpoint-url=http://localhost:4566 \
     logs describe-log-groups
   ```
2. Check for log streams:
   ```bash
   AWS_ACCESS_KEY_ID=333333333333 aws --endpoint-url=http://localhost:4566 \
     logs describe-log-streams --log-group-name /aws/logs/globex-industries/application
   ```
3. Check DynamoDB tenant config is correct:
   ```bash
   make test-check-central
   ```

### Test Fails: "failed to create AWS config"
**Cause**: LocalStack endpoint not reachable

**Solutions**:
1. Verify LocalStack is running: `make logs`
2. Check endpoint is accessible: `curl http://localhost:4566`
3. Restart LocalStack: `make stop && make start`

### All Tests Fail
**Solutions**:
1. Full reset:
   ```bash
   make clean
   make start
   make deploy-go
   # In separate terminal:
   make run-go-scan
   # Then run tests
   ```

## Testing Approach

### Primary Test Suite: Go Integration Tests

The Go integration tests (`go test -tags=integration`) are the **primary and recommended** way to test the log delivery pipeline:

**Advantages:**
- ✅ Native Go testing framework with proper assertions
- ✅ Better IDE integration and debugging support
- ✅ Reusable test utilities and helpers
- ✅ Type-safe test data structures
- ✅ Parallel test execution support
- ✅ Comprehensive coverage (S3, CloudWatch, concurrent, mixed delivery)
- ✅ Used in CI/CD pipeline

**Run with:** `make test-e2e-go-quick` or `cd container && go test -tags=integration ./integration -v`

### Quick Manual Debugging

For quick manual inspection, use these AWS CLI commands directly:

```bash
# Check DynamoDB tenant configs
aws --endpoint-url=http://localhost:4566 dynamodb scan \
  --table-name $(cd terraform/local && terraform output -raw central_dynamodb_table)

# Check customer S3 bucket
AWS_ACCESS_KEY_ID=222222222222 AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url=http://localhost:4566 s3 ls \
  s3://$(cd terraform/local && terraform output -raw customer1_bucket)/logs/ --recursive
```

The old Makefile shell test targets have been removed as they were redundant with the Go test suite.

## Adding New Tests

To add a new integration test:

1. Create a new test function in `e2e_test.go`:
   ```go
   func TestE2EMyNewFeature(t *testing.T) {
       helper := NewE2ETestHelper(t)
       defer helper.Cleanup(t)

       // Your test logic here
   }
   ```

2. Use build tag at the top of file:
   ```go
   //go:build integration
   // +build integration
   ```

3. Use helper functions for common operations

4. Follow existing test patterns for consistency

## Contributing

When adding new integration tests:
- Use descriptive test names
- Add proper logging with `t.Logf()`
- Use `t.Helper()` in helper functions
- Document expected behavior in comments
- Ensure tests clean up after themselves
- Consider adding both sequential and parallel test variants

## References

- [Go Testing Documentation](https://golang.org/pkg/testing/)
- [Testify Assertions](https://github.com/stretchr/testify)
- [LocalStack Documentation](https://docs.localstack.cloud/)
- [AWS SDK for Go v2](https://aws.github.io/aws-sdk-go-v2/)
