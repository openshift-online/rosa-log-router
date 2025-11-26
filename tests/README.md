# Multi-Tenant Logging Pipeline Testing

This directory contains comprehensive testing infrastructure for the multi-tenant logging pipeline, including unit tests, integration tests, SQS message handling tests, and Vector configuration testing.

## Testing Architecture Overview

The testing infrastructure is organized into multiple layers:

### 1. **Unit Tests** (`tests/unit/`)
Comprehensive unit tests (126 total) covering both container and API components with mocked AWS services:

- **`test_log_processor.py`** - Container log processor tests (70 tests)
  - S3 object key parsing and tenant info extraction
  - DynamoDB tenant configuration retrieval  
  - Log file processing (NDJSON and JSON array formats)
  - Cross-account role assumption (double-hop)
  - Vector subprocess integration
  - SQS message processing and Lambda handler functionality
  - Error handling (recoverable vs non-recoverable errors)

- **API Component Tests** (56 tests):
  - `test_api_app_endpoints.py` - FastAPI endpoint functionality, request/response validation
  - `test_api_authorizer.py` - Lambda authorizer and HMAC authentication tests  
  - `test_api_dynamo_service.py` - DynamoDB tenant service tests
  - `test_api_v1.py` - Original API integration tests
  - HTTP status codes and Pydantic model validation

### 2. **Integration Tests** (`tests/integration/`)
Real-world testing against actual services using DynamoDB Local in Minikube:

- **`test_api_integration.py`** - API integration tests (8 tests)
  - Complete CRUD operations with real DynamoDB Local
  - Concurrent tenant operations
  - Large dataset pagination testing
  - Error handling with real AWS service responses
  - Configuration validation end-to-end

- **Kubernetes Manifests** (`tests/integration/manifests/`):
  - `dynamodb-local.yaml` - DynamoDB Local deployment
  - `fake-log-generator.yaml` - Multi-replica log generators
  - `minio.yaml` - S3-compatible storage for testing

### 3. **SQS Message Handling Tests** (`tests/`)
Focused tests for SQS message processing and error handling:

- **`test_mock_sqs.py`** - Unit tests with mocked AWS dependencies (no credentials needed)
- **`test_sqs_handling.sh`** - Bash script testing various SQS message scenarios
- **`test_container_sqs.sh`** - Container-based testing of SQS processing
- **`test_data.py`** - Test data generator for different SQS message scenarios

### 4. **Vector Configuration Tests** (`tests/`)
Vector log collection and processing validation:

- **`vector-local-test.yaml`** - Local Vector configuration for testing
- **`test-vector.sh`** - Vector testing with real AWS infrastructure setup

## Test Infrastructure

### Core Testing Files

- **`conftest.py`** - Shared unit test fixtures with moto AWS mocking
- **`integration/conftest.py`** - Integration test fixtures for DynamoDB Local
- **`requirements.txt`** - Test dependencies (pytest, moto, boto3, etc.)
- **`integration/pytest.ini`** - Integration test configuration

## Running Tests

### Prerequisites
```bash
# Install test dependencies
pip3 install -r tests/requirements.txt

# For integration tests: ensure minikube is running
minikube start
```

### Unit Tests (No AWS credentials needed)
```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage report
pytest tests/unit/ --cov=container --cov=api/src --cov-report=html --cov-report=term-missing

# Run specific components
pytest tests/unit/test_log_processor.py -v      # Container tests
pytest tests/unit/test_api_*.py -v             # API tests
```

### Integration Tests (Requires minikube)
```bash
# Deploy DynamoDB Local to minikube
kubectl apply -f tests/integration/manifests/dynamodb-local.yaml
kubectl wait --for=condition=ready pod -l app=dynamodb-local --timeout=300s

# Run integration tests
pytest tests/integration/ -v -m integration

# Run specific integration tests
pytest tests/integration/test_api_integration.py::TestTenantServiceIntegration::test_tenant_crud_operations -v
```

### SQS Message Handling Tests
```bash
# Mock tests (no AWS credentials needed)
python3 tests/test_mock_sqs.py

# Local tests with manual input
python3 tests/test_data.py invalid-format | python3 container/log_processor.py --mode manual

# Container-based tests
./tests/test_container_sqs.sh

# Real AWS infrastructure tests
source .env
python3 tests/test_data.py existing-tenant | python3 container/log_processor.py --mode manual
```

### Vector Configuration Tests
```bash
# Set up Vector testing environment
chmod +x tests/test-vector.sh
source tests/test-vector.sh

# Test Vector with fake logs
cd test_container/
python3 fake_log_generator.py --total-batches 10 | vector --config ../tests/vector-local-test.yaml
```

## GitHub Actions Integration Tests

The repository includes comprehensive end-to-end integration tests that run automatically in GitHub Actions (`.github/workflows/integration-tests.yaml`):

### Complete Pipeline Testing
1. **Minikube Setup** - Kubernetes cluster with proper networking
2. **MinIO Deployment** - S3-compatible storage for log delivery testing  
3. **DynamoDB Local** - Real DynamoDB for tenant configuration testing
4. **Fake Log Generators** - Mixed format log generation (60% plain text, 40% JSON)
5. **Vector Collector** - Full Vector pipeline with intelligent JSON parsing
6. **Log Processing Verification** - Validates compressed log file creation and structure
7. **API Integration Tests** - Complete CRUD operations with real DynamoDB Local

### Test Validation
The GitHub Actions workflow verifies:
- ✅ Log directory structure creation in MinIO (`test-cluster/default/fake-log-generator/`)
- ✅ Compressed log file generation (`.json.gz` objects)
- ✅ Multi-pod log collection from 2 replica fake log generators
- ✅ Vector's intelligent parsing of mixed plain text and JSON logs
- ✅ S3 object counting and verification (20,000+ objects created during testing)
- ✅ API integration tests with DynamoDB Local (8 tests covering CRUD, concurrency, validation)

### Recent Improvements
- **Fixed file detection issues**: Replaced incompatible `find` commands with `ls` commands for MinIO container
- **Enhanced S3 object verification**: Updated logic to properly count `.json.gz` objects in MinIO's S3-compatible storage
- **Increased processing time**: Extended wait from 120s to 180s for reliable Vector log delivery
- **Comprehensive logging**: Added detailed debugging output for troubleshooting

## Test Features and Capabilities

### Mocking and Isolation
- **AWS Service Mocking**: Uses `moto` library for S3, DynamoDB, STS, CloudWatch Logs
- **Environment Management**: Automatic test environment setup and cleanup
- **Time Mocking**: Uses `freezegun` for consistent timestamp testing
- **Isolated Tests**: Each test uses fresh mocked AWS resources

### Error Scenario Testing
- **SQS Message Handling**: Distinguishes recoverable vs non-recoverable errors
- **Cross-Account Role Assumption**: Tests double-hop authentication failures
- **Tenant Configuration**: Tests missing tenants, invalid configurations
- **Network Failures**: Simulated AWS service errors and timeouts

### Performance and Scale Testing
- **Concurrent Operations**: Multi-threaded tenant creation and access
- **Large Datasets**: Bulk tenant creation (25+ tenants) with pagination
- **Batch Processing**: SQS message batching (up to 10 messages per Lambda invocation)
- **Log Volume**: High-volume log generation for Vector performance testing

## Test Data and Scenarios

### SQS Message Test Scenarios
1. **Non-existent tenant** - Valid S3 notification but tenant not in DynamoDB
2. **Invalid message format** - Malformed JSON in SQS message body
3. **Invalid S3 event** - Missing required S3 event fields
4. **Invalid object key format** - S3 object key doesn't match expected pattern  
5. **Recoverable errors** - Network/AWS service errors that should be retried

### Expected Error Behavior

**Non-Recoverable Errors (Message Removed):**
- Log Level: WARNING
- Message: "Message will be removed from queue"
- Exit Code: 0 (success)
- Lambda: Not added to `batchItemFailures`

**Recoverable Errors (Message Retried):**
- Log Level: ERROR  
- Message: "Message will be retried"
- Exit Code: 1 (failure)
- Lambda: Added to `batchItemFailures`

### Test Data Format
```json
{
  "Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"bucket-name\"}, \"object\": {\"key\": \"cluster/tenant/app/pod/file.json.gz\"}}}]}"
}
```

## Configuration and Environment

### Environment Variables
Tests use environment variables for configuration:
```bash
# AWS Configuration (for integration tests)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test  # DynamoDB Local
AWS_SECRET_ACCESS_KEY=test

# Service Configuration  
TENANT_CONFIG_TABLE=integration-test-tenant-configs
MAX_BATCH_SIZE=1000
RETRY_ATTEMPTS=3
```

### Test Configuration Files
- **`integration/pytest.ini`** - Pytest configuration for integration tests
- **`vector-local-test.yaml`** - Vector configuration for local testing
- **`.env.sample`** - Template environment configuration

## Adding New Tests

### Unit Tests
1. Add test functions to appropriate `test_*.py` files
2. Use existing fixtures from `conftest.py`
3. Follow naming convention: `test_feature_scenario()`
4. Include both happy path and error scenarios

### Integration Tests  
1. Add test cases to `test_api_integration.py`
2. Use DynamoDB Local fixtures from `integration/conftest.py`
3. Mark tests with `@pytest.mark.integration`
4. Ensure proper cleanup in fixtures

### SQS Message Tests
1. Add test data to `test_data.py`
2. Update `test_sqs_handling.sh` and `test_mock_sqs.py`
3. Test both recoverable and non-recoverable error scenarios
4. Verify proper SQS message handling behavior

## Troubleshooting

### Common Issues

**"Unable to locate credentials" errors:**
- Expected for tenant lookup tests without AWS credentials
- Use mock tests for testing without AWS access
- Set up `.env` file for integration tests

**Container build failures:**
- Ensure podman/docker is installed and running
- Build manually: `cd container && podman build -f Containerfile.processor -t log-processor:local .`

**DynamoDB Local connection failures:**
- Verify minikube is running and DynamoDB Local pod is ready
- Check port forwarding: `kubectl port-forward service/dynamodb-local 8000:8000`
- Ensure no other processes are using port 8000

**Integration test timeouts:**
- Increase timeout values in test fixtures
- Check minikube resource allocation
- Verify all pods are in Ready state before running tests

### Debugging Commands
```bash
# Check test pod status
kubectl get pods -l app=dynamodb-local
kubectl logs -l app=dynamodb-local

# Test DynamoDB Local connectivity
curl http://localhost:8000/

# Run specific test with verbose output
pytest tests/integration/test_api_integration.py::TestTenantServiceIntegration::test_tenant_crud_operations -v -s

# Check minikube logs
minikube logs
```

## Benefits of This Testing Strategy

1. **Comprehensive Coverage**: Unit tests (70% code coverage) + integration tests + end-to-end pipeline validation
2. **No Infinite Retries**: SQS message handling properly removes invalid messages from queues
3. **Cost Optimization**: Reduces SQS processing costs through proper error classification
4. **Monitoring Friendly**: Clear error patterns for alerting and debugging
5. **Container Compatible**: Works in Lambda, Kubernetes, and local development environments
6. **Real Service Validation**: Integration tests use actual DynamoDB Local for realistic behavior
7. **CI/CD Ready**: GitHub Actions integration provides automated validation for all changes
8. **Scalable Testing**: Supports concurrent operations and large dataset testing
9. **Error Isolation**: Distinguishes between temporary failures and permanent configuration issues
10. **Developer Experience**: Fast feedback loop with mocked services for rapid development