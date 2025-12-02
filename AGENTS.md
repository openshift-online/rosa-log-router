# Development Guide

This guide provides comprehensive instructions for local development and testing of the multi-tenant logging pipeline.

## Prerequisites

- **Python 3.13+** with pip
- **Podman** for containerized testing
- **AWS CLI** configured with your AWS profile
- **kubectl** configured for your Kubernetes clusters
- **Access to deployed infrastructure** (see [Deployment Guide](docs/deployment-guide.md))

## Environment Setup

### Environment Configuration

The project uses a `.env` file for centralized environment variable management:

```bash
# Copy the sample environment file and customize with your values
cp .env.sample .env

# Edit the .env file with your AWS configuration
vim .env  # or use your preferred editor

# Source the environment variables for the current session
source .env

# Verify configuration
echo "AWS Profile: $AWS_PROFILE"
echo "AWS Region: $AWS_REGION"
echo "Template Bucket: $TEMPLATE_BUCKET"
```

**Key Environment Variables:**
- `AWS_PROFILE`: Your AWS CLI profile name
- `AWS_REGION`: Target AWS region for deployment
- `AWS_ACCOUNT_ID`: Your AWS account ID
- `TEMPLATE_BUCKET`: S3 bucket for CloudFormation templates
- `ENVIRONMENT`: Environment name (development, staging, production)
- `CENTRAL_LOG_DISTRIBUTION_ROLE_ARN`: ARN of the global central role
- `ECR_IMAGE_URI`: Container image URI for Lambda deployment

**Security Note**: Never commit the `.env` file to version control. It's included in `.gitignore`.

## Local Development

### Direct Python Execution

#### Install Dependencies
```bash
cd container/
pip3 install --user -r requirements.txt
```

#### SQS Polling Mode
Test against live SQS queue:
```bash
cd container/
source ../.env

python3 log_processor.py --mode sqs
```

#### Manual Testing Mode
Test with sample S3 event data:
```bash
cd container/
source ../.env

# Test with sample S3 event
echo '{"Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"test-bucket\"}, \"object\": {\"key\": \"test-customer/test-cluster/test-app/test-pod/20240101-test.json.gz\"}}}]}"}' | python3 log_processor.py --mode manual
```

### Container-Based Development

#### Build Containers
```bash
cd container/

# Build collector container first (contains Vector)
podman build -f Containerfile.collector -t log-collector:latest .

# Build processor container (includes Vector from collector)
podman build -f Containerfile.processor -t log-processor:local .
```

#### Run with AWS Profile
```bash
# Source environment variables
source .env

podman run --rm \
  -e AWS_PROFILE="$AWS_PROFILE" \
  -e AWS_REGION="$AWS_REGION" \
  -e SQS_QUEUE_URL="$SQS_QUEUE_URL" \
  -e TENANT_CONFIG_TABLE="$TENANT_CONFIG_TABLE" \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN="$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  -e EXECUTION_MODE="sqs" \
  -v ~/.aws:/home/logprocessor/.aws:ro \
  log-processor:local
```

#### Run with Explicit Credentials
```bash
# Source environment variables
source .env

# Extract credentials (do not save these in files!)
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile "$AWS_PROFILE")
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile "$AWS_PROFILE")

# Run container with explicit credentials
podman run --rm \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_REGION="$AWS_REGION" \
  -e SQS_QUEUE_URL="$SQS_QUEUE_URL" \
  -e TENANT_CONFIG_TABLE="$TENANT_CONFIG_TABLE" \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN="$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  -e EXECUTION_MODE="manual" \
  log-processor:local
```

#### Manual Testing with Container
```bash
echo '{"Message": "{\"Records\": [{\"s3\": {\"bucket\": {\"name\": \"test-bucket\"}, \"object\": {\"key\": \"test-customer/test-cluster/test-app/test-pod/20240101-test.json.gz\"}}}]}"}' | podman run --rm -i \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e AWS_REGION="$AWS_REGION" \
  -e TENANT_CONFIG_TABLE="$TENANT_CONFIG_TABLE" \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN="$CENTRAL_LOG_DISTRIBUTION_ROLE_ARN" \
  -e EXECUTION_MODE=manual \
  log-processor:local
```

### Container Registry Management

#### Build and Push to ECR
```bash
cd container/

# Build containers with multi-stage build
podman build -f Containerfile.collector -t log-collector:latest .
podman build -f Containerfile.processor -t log-processor:local .

# Tag and push to ECR (for Lambda deployment)
aws ecr get-login-password --region "$AWS_REGION" | \
  podman login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

podman tag log-processor:local "$ECR_IMAGE_URI"
podman push "$ECR_IMAGE_URI"
```

## Testing and Validation

### Vector Pipeline Testing

#### Test Environment Setup
```bash
cd tests/integration/

# Set up environment for Vector role assumption
chmod +x test-vector.sh
source ./test-vector.sh

# Install fake log generator dependencies
cd ../../test_container/
pip3 install -r requirements.txt
```

#### Basic Vector Testing
```bash
# Basic Vector test with realistic fake logs
python3 fake_log_generator.py --total-batches 10 | \
  vector --config ../tests/vector-local-test.yaml

# High-volume Vector performance test
python3 fake_log_generator.py \
  --min-batch-size 50 --max-batch-size 100 \
  --min-sleep 0.1 --max-sleep 0.5 \
  --total-batches 100 | \
  vector --config ../tests/vector-local-test.yaml

# Multi-tenant Vector test
python3 fake_log_generator.py \
  --customer-id acme-corp \
  --cluster-id prod-cluster-1 \
  --application payment-service \
  --total-batches 20 | \
  vector --config ../tests/vector-local-test.yaml
```

#### Container-Based Vector Testing
```bash
# Build and test fake log generator container
cd test_container/
podman build -f Containerfile -t fake-log-generator .
podman run --rm fake-log-generator --total-batches 10 | \
  vector --config ../tests/vector-local-test.yaml
```

#### Manual Vector Role Assumption
```bash
# Alternative to test-vector.sh script
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile "$AWS_PROFILE")
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile "$AWS_PROFILE")
export S3_WRITER_ROLE_ARN=arn:aws:iam::641875867446:role/multi-tenant-logging-development-central-s3-writer-role
export S3_BUCKET_NAME=multi-tenant-logging-development-central-12345678
export AWS_REGION=us-east-2
```

### Unit Testing

The project includes comprehensive unit tests (126 total tests):

#### Install Test Dependencies
```bash
# From project root
pip3 install -r tests/requirements.txt
```

#### Run All Tests
```bash
# Run all unit tests
pytest tests/unit/ -v

# With coverage report
pytest tests/unit/ --cov=container --cov=api/src --cov-report=html --cov-report=term-missing
```

#### Run Specific Tests
```bash
# Test log processor only
pytest tests/unit/test_log_processor.py -v

# Test API components only
pytest tests/unit/test_api_*.py -v

# Run with specific markers
pytest tests/unit/ -m "unit" -v
```

#### Test Structure Overview
- **`test_log_processor.py`**: Container processing logic, S3 parsing, DynamoDB access, Vector integration
- **`test_api_*.py`**: FastAPI endpoints, authentication, tenant management
- **`conftest.py`**: Shared fixtures with AWS service mocking

### Infrastructure Testing

#### Validate CloudFormation Templates
```bash
cd cloudformation/

# Validate templates without deployment
./deploy.sh --validate-only -b "$TEMPLATE_BUCKET"
./deploy.sh --validate-only -b "$TEMPLATE_BUCKET" --include-sqs --include-lambda
```

#### Test Modular Deployments
```bash
# Test different deployment patterns
./deploy.sh --validate-only -b "$TEMPLATE_BUCKET" --include-sqs
./deploy.sh --validate-only -b "$TEMPLATE_BUCKET" --include-api
```

## Health Checks and Debugging

### Vector Status
```bash
# Check Vector pod status
kubectl get pods -n logging
kubectl describe daemonset vector-logs -n logging
kubectl logs -n logging daemonset/vector-logs --tail=50

# Check Vector metrics endpoint
kubectl port-forward -n logging daemonset/vector-logs 8686:8686
curl http://localhost:8686/metrics
```

### SQS Queue Status
```bash
# Check queue metrics
aws sqs get-queue-attributes \
  --queue-url "$SQS_QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages,ApproximateNumberOfMessagesNotVisible
```

### Lambda Function Status
```bash
# Check function configuration
aws lambda get-function \
  --function-name multi-tenant-logging-${ENVIRONMENT}-log-distributor

# Check recent logs
aws logs describe-log-streams \
  --log-group-name "/aws/lambda/multi-tenant-logging-${ENVIRONMENT}-log-distributor" \
  --order-by LastEventTime --descending

# Filter for errors
aws logs filter-log-events \
  --log-group-name "/aws/lambda/multi-tenant-logging-${ENVIRONMENT}-log-distributor" \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000
```

### Tenant Configuration Management
```bash
# Check tenant configuration
aws dynamodb get-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"},"type":{"S":"cloudwatch"}}'

# List all tenants
aws dynamodb scan \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --projection-expression "tenant_id, #t, enabled" \
  --expression-attribute-names '{"#t": "type"}'

# Enable/disable a tenant
aws dynamodb update-item \
  --table-name multi-tenant-logging-${ENVIRONMENT}-tenant-configs \
  --key '{"tenant_id":{"S":"TENANT_ID"},"type":{"S":"cloudwatch"}}' \
  --update-expression "SET enabled = :val" \
  --expression-attribute-values '{":val":{"BOOL":true}}'
```

## Development Workflow

### Code Development
1. **Make changes** to container code or infrastructure
2. **Run unit tests** to verify functionality
3. **Test locally** with manual or SQS polling mode
4. **Build containers** and test with Podman
5. **Validate infrastructure** changes with CloudFormation
6. **Deploy to development environment** for integration testing

### Container Development
1. **Build locally** with Podman
2. **Test multi-mode execution** (Lambda, SQS, manual)
3. **Push to ECR** for Lambda deployment testing
4. **Deploy and validate** in development environment

### Infrastructure Development
1. **Validate templates** locally
2. **Test modular deployment** patterns
3. **Deploy to development** environment
4. **Verify resource creation** and configuration

## Performance Optimization

### Vector Configuration Tuning
```yaml
# In Vector configuration, optimize for your workload
batch:
  max_bytes: 67108864  # 64MB - adjust based on log volume
  timeout_secs: 300    # 5 minutes - balance latency vs efficiency

buffer:
  max_size: 10737418240  # 10GB - adjust based on available disk
  when_full: "block"     # Ensure no log loss
```

### Lambda Memory Optimization
```bash
# Monitor Lambda performance
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=multi-tenant-logging-${ENVIRONMENT}-log-distributor \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Average,Maximum
```

### Cost Monitoring
```bash
# Check S3 storage costs
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name BucketSizeBytes \
  --dimensions Name=BucketName,Value="$S3_BUCKET_NAME" Name=StorageType,Value=StandardStorage \
  --start-time $(date -d '24 hours ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 86400 \
  --statistics Average
```

## Common Development Issues

### Vector Not Collecting Logs
- **Check namespace labels**: Ensure namespaces have `hypershift.openshift.io/hosted-control-plane=true`
- **Verify IRSA configuration**: Check service account annotations and trust policies
- **Test S3 access**: Manually verify S3WriterRole permissions

### Container Build Failures
```bash
# Force rebuild without cache
podman build --no-cache -f Containerfile.processor -t log-processor:local .

# Check base image availability
podman pull public.ecr.aws/lambda/python:3.13
```

### Lambda Deployment Issues
- **Check ECR image**: Verify image exists and is accessible
- **Validate permissions**: Ensure Lambda execution role has required permissions
- **Test locally first**: Always test with manual mode before deploying

### Cross-Account Access Issues
```bash
# Test role assumption manually
aws sts assume-role \
  --role-arn "arn:aws:iam::CUSTOMER-ACCOUNT:role/CustomerLogDistribution-us-east-1" \
  --role-session-name "test-assumption" \
  --external-id "$AWS_ACCOUNT_ID"
```

## Security Best Practices

### Credential Management
- **Never commit credentials** to version control
- **Use environment variables** for temporary credential passthrough
- **Volume mount ~/.aws** for local development only
- **Prefer IAM roles** over access keys in production

### Testing Security
- **Use mocked AWS services** for unit tests (via `moto`)
- **Test with minimal permissions** to verify least privilege
- **Validate ExternalId** requirements in cross-account scenarios

## Documentation and Resources

### Architecture References
- **[System Design](DESIGN.md)**: Comprehensive architecture documentation
- **[Deployment Guide](docs/deployment-guide.md)**: Infrastructure deployment instructions
- **[Troubleshooting Guide](docs/troubleshooting.md)**: Common issues and solutions

### Component-Specific Guides
- **[CloudFormation Infrastructure](cloudformation/README.md)**
- **[Kubernetes Deployment](k8s/README.md)**
- **[API Management](api/README.md)**

### External Documentation
- **[Vector Documentation](https://vector.dev/docs/)**
- **[AWS Lambda Container Images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)**
- **[OpenShift SecurityContextConstraints](https://docs.openshift.com/container-platform/latest/authentication/managing-security-context-constraints.html)**

## Contributing

### Code Standards
- **Follow existing patterns** in container and infrastructure code
- **Add unit tests** for new functionality
- **Update documentation** for any changes
- **Test in development environment** before production deployment

### Testing Requirements
- **Unit tests must pass**: `pytest tests/unit/ -v`
- **Container builds must succeed**: Test with Podman locally
- **Infrastructure validation**: Validate CloudFormation templates
- **Integration testing**: Test end-to-end functionality in development

### Pull Request Process
1. **Create feature branch** from main
2. **Implement changes** with tests
3. **Validate locally** with full test suite
4. **Update documentation** as needed
5. **Submit PR** with detailed description of changes