# Fake Log Generator for Multi-Tenant Logging Pipeline Testing

This container generates realistic fake log data using the faker library for testing the multi-tenant logging pipeline with configurable volumes and patterns.

## Features

- **Realistic Log Data**: Generates JSON log messages with timestamps, levels, modules, line numbers, and variable-length messages
- **Configurable Volume**: Generates 1-50 logs per batch with random intervals
- **Message Size Control**: Variable message lengths from 100 bytes to 1KB
- **Metadata Support**: Includes customer_id, cluster_id, application, and pod_name for multi-tenant testing
- **NDJSON Output**: Compatible with Vector and other log processing tools
- **Graceful Shutdown**: Handles signals properly and provides statistics

## Log Format

Each generated log entry includes:

```json
{
  "timestamp": "2025-01-20T12:34:56.789Z",
  "level": "INFO",
  "module": "auth.service",
  "line": 142,
  "message": "Processing request for user johndoe with ID 12345...",
  "customer_id": "test-customer",
  "cluster_id": "test-cluster", 
  "application": "test-app",
  "pod_name": "test-pod",
  "source": "fake-log-generator",
  "additional_data": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "session_id": "abc12345",
    "ip_address": "192.168.1.100",
    "user_agent": "Mozilla/5.0..."
  }
}
```

## Usage

### Direct Python Execution

```bash
cd test_container/
pip3 install -r requirements.txt
python3 fake_log_generator.py --help
```

### Basic Usage

```bash
# Generate logs with default settings (1-50 logs per batch, 0.1-5s intervals)
python3 fake_log_generator.py

# Generate logs with specific metadata
python3 fake_log_generator.py \
  --customer-id acme-corp \
  --cluster-id prod-cluster-1 \
  --application payment-service \
  --pod-name payment-pod-123

# Generate high-volume logs for performance testing
python3 fake_log_generator.py \
  --min-batch-size 20 \
  --max-batch-size 100 \
  --min-sleep 0.05 \
  --max-sleep 1.0

# Generate logs with larger messages
python3 fake_log_generator.py \
  --min-message-bytes 500 \
  --max-message-bytes 2048
```

### Container Usage

#### Build Container

```bash
cd test_container/
podman build -f Containerfile -t fake-log-generator:latest .
```

#### Run Container

```bash
# Show help
podman run --rm fake-log-generator:latest

# Generate logs with default settings
podman run --rm fake-log-generator:latest \
  --customer-id test-customer \
  --total-batches 10

# High-volume testing
podman run --rm fake-log-generator:latest \
  --min-batch-size 50 \
  --max-batch-size 100 \
  --min-sleep 0.1 \
  --max-sleep 0.5 \
  --customer-id load-test
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--min-batch-size` | 1 | Minimum number of logs per batch |
| `--max-batch-size` | 50 | Maximum number of logs per batch |
| `--min-sleep` | 0.1 | Minimum sleep between batches (seconds) |
| `--max-sleep` | 5.0 | Maximum sleep between batches (seconds) |
| `--min-message-bytes` | 100 | Minimum message size in bytes |
| `--max-message-bytes` | 1024 | Maximum message size in bytes |
| `--customer-id` | test-customer | Customer ID for log metadata |
| `--cluster-id` | test-cluster | Cluster ID for log metadata |
| `--application` | test-app | Application name for log metadata |
| `--pod-name` | test-pod | Pod name for log metadata |
| `--total-batches` | 0 | Total batches to generate (0 = infinite) |
| `--stats-interval` | 100 | Print stats every N batches |

## Integration with Vector

### Pipe to Vector Directly

```bash
# Generate logs and pipe to Vector
python3 fake_log_generator.py \
  --customer-id acme-corp \
  --cluster-id prod-cluster-1 | vector --config ../vector-local-test.yaml
```

### Container to Vector Pipeline

```bash
# Generate logs in container and pipe to Vector
podman run --rm fake-log-generator:latest \
  --customer-id acme-corp \
  --total-batches 100 | vector --config vector-local-test.yaml
```

### Save to File for Later Processing

```bash
# Generate logs to file
python3 fake_log_generator.py \
  --total-batches 50 > sample_logs.ndjson

# Process file with Vector
cat sample_logs.ndjson | vector --config vector-local-test.yaml
```

## Testing Scenarios

### 1. Development Testing

```bash
# Generate small batches for development
python3 fake_log_generator.py \
  --min-batch-size 1 \
  --max-batch-size 5 \
  --min-sleep 2.0 \
  --max-sleep 5.0 \
  --total-batches 20
```

### 2. Performance Testing

```bash
# High-volume load testing
python3 fake_log_generator.py \
  --min-batch-size 100 \
  --max-batch-size 200 \
  --min-sleep 0.1 \
  --max-sleep 0.2 \
  --customer-id load-test-customer
```

### 3. Multi-Tenant Testing

```bash
# Simulate multiple tenants (run multiple instances)
python3 fake_log_generator.py --customer-id tenant-a --cluster-id cluster-1 &
python3 fake_log_generator.py --customer-id tenant-b --cluster-id cluster-2 &
python3 fake_log_generator.py --customer-id tenant-c --cluster-id cluster-1 &
```

### 4. Message Size Testing

```bash
# Test with large messages
python3 fake_log_generator.py \
  --min-message-bytes 2048 \
  --max-message-bytes 4096 \
  --min-batch-size 5 \
  --max-batch-size 10
```

## Log Level Distribution

The generator creates logs with realistic distribution:
- **DEBUG**: 30%
- **INFO**: 50% 
- **WARN**: 15%
- **ERROR**: 5%

## Module Names

Generates realistic module names including:
- `auth.service`, `payment.processor`, `user.controller`
- `inventory.manager`, `notification.sender`, `config.loader`
- `database.connection`, `api.gateway`, `security.validator`
- And many more...

## Output and Monitoring

The generator outputs:
- **STDOUT**: NDJSON log entries (one per line)
- **STDERR**: Statistics and progress information

Example stats output:
```
Starting fake log generator...
Batch size: 1-50
Sleep interval: 0.1-5.0s
Message size: 100-1024 bytes
Metadata: test-customer/test-cluster/test-app/test-pod

Generated 100 batches, 2847 logs, 47.8 logs/sec
Generated 200 batches, 5623 logs, 48.2 logs/sec

Final stats:
Total batches: 250
Total logs: 7089
Runtime: 147.3s
Average rate: 48.1 logs/sec
```

## Signal Handling

The generator handles shutdown signals gracefully:
- **SIGINT** (Ctrl+C): Graceful shutdown with final statistics
- **SIGTERM**: Clean container shutdown
- **Broken Pipe**: Handles when output is piped to tools that close early

## Error Handling

- Missing faker library: Clear error message with installation instructions
- Broken pipe: Graceful shutdown when piped to tools like `head`
- Invalid arguments: Helpful error messages and usage information
- Keyboard interrupt: Clean shutdown with statistics