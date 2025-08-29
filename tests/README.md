# SQS Message Handling Tests

This directory contains tests to verify the improved SQS message handling that ensures non-recoverable errors (like missing tenant configurations or invalid S3 notifications) are properly removed from the queue instead of being retried indefinitely.

## Test Files

### Core Test Scripts

- **`test_data.py`** - Generates test SQS message payloads for different scenarios
- **`test_sqs_handling.sh`** - Bash script to test various SQS message scenarios
- **`test_mock_sqs.py`** - Python unit tests with mocked AWS dependencies (no credentials needed)
- **`test_container_sqs.sh`** - Tests the same scenarios using the containerized processor

### Test Scenarios

1. **Non-existent tenant** - Valid S3 notification but tenant not in DynamoDB
2. **Invalid message format** - Malformed JSON in SQS message body
3. **Invalid S3 event** - Missing required S3 event fields
4. **Invalid object key format** - S3 object key doesn't match expected pattern
5. **Recoverable errors** - Network/AWS service errors that should be retried

## Running Tests

### Quick Start (No AWS credentials needed)
```bash
# Run mock tests that don't require AWS
python3 test_mock_sqs.py
```

### Local Tests (No AWS credentials needed for most scenarios)
```bash
# Test individual scenarios
python3 test_data.py invalid-format | python3 ../container/log_processor.py --mode manual
python3 test_data.py invalid-object-key | python3 ../container/log_processor.py --mode manual

# Run all local tests
./test_sqs_handling.sh
```

### Container Tests
```bash
# Test with containerized processor
./test_container_sqs.sh
```

### Test with Real AWS Infrastructure
```bash
# Source your AWS environment
source ../.env

# Test with existing tenant (requires DynamoDB access)
python3 test_data.py existing-tenant | python3 ../container/log_processor.py --mode manual

# Test non-existent tenant (requires DynamoDB access)
python3 test_data.py nonexistent-tenant | python3 ../container/log_processor.py --mode manual
```

## Expected Behavior

### Non-Recoverable Errors (Message Removed from Queue)
- **Log Level**: WARNING
- **Message**: "Message will be removed from queue"
- **Exit Code**: 0 (success)
- **Lambda**: Not added to `batchItemFailures`
- **SQS Polling**: Message deleted from queue

Example output:
```
WARNING - Non-recoverable error processing SQS record: Invalid SQS message format: Expecting value: line 1 column 1 (char 0). Message will be removed from queue.
```

### Recoverable Errors (Message Retried)
- **Log Level**: ERROR
- **Message**: "Message will be retried"
- **Exit Code**: 1 (failure)
- **Lambda**: Added to `batchItemFailures`
- **SQS Polling**: Message remains in queue for retry

Example output:
```
ERROR - Recoverable error processing SQS record: Network error. Message will be retried.
```

## Test Data Format

The test data generator creates SQS messages in the expected format:

```json
{
  "Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"bucket-name\"}, \"object\": {\"key\": \"cluster/tenant/app/pod/file.json.gz\"}}}]}"
}
```

## Integration with Existing Testing

These tests complement the existing testing infrastructure:

- **`test_container/fake_log_generator.py`** - Generates realistic log data for end-to-end testing
- **`tests/test-vector.sh`** - Sets up Vector testing with real AWS infrastructure
- **Container testing** - Both collector and processor containers

## Customizing Tests

### Adding New Test Cases

1. Add test data to `test_data.py`:
```python
NEW_TEST_CASE = {
    "Message": json.dumps({
        "Records": [{"your": "test data"}]
    })
}
```

2. Add case to the main function and update the help text

3. Add test to `test_sqs_handling.sh` and `test_mock_sqs.py`

### Modifying Test Environment

Set environment variables in `../.env` or export them directly:
```bash
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-2
export TENANT_CONFIG_TABLE=your-table-name
```

## Troubleshooting

### "Unable to locate credentials" errors
- This is expected for tenant lookup tests without AWS credentials
- Use mock tests (`test_mock_sqs.py`) for testing without AWS access
- Set up `.env` file with AWS credentials for full integration tests

### Container build failures
- Ensure podman/docker is installed and running
- Build containers manually: `cd ../container && podman build -f Containerfile.processor -t log-processor:test .`

### Permission errors
- Make scripts executable: `chmod +x *.sh *.py`
- Check file permissions in the container directory

## Benefits of This Testing Approach

1. **No infinite retries** - Invalid messages are properly removed from SQS queues
2. **Clear logging** - Distinguishes between recoverable and non-recoverable errors
3. **Cost optimization** - Reduces SQS message processing costs
4. **Monitoring friendly** - Clear error patterns for alerting and debugging
5. **Container compatible** - Works in Lambda, Kubernetes, and local environments