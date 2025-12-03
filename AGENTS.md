# Development Guide

This guide provides comprehensive instructions for local development and testing of the multi-tenant logging pipeline.

## Prerequisites

- **Go 1.21+** for log processor development
- **Python 3.13+** for API development only (optional)
- **Podman** for containerized testing
- **AWS CLI** configured with LocalStack testing
- **kubectl** configured for your Kubernetes clusters (for cluster deployments)

## Environment Setup

### Environment Configuration

The project uses a `.env` file for centralized environment variable management:

```bash
# For local development with LocalStack, most configuration is handled by the Makefile
# See Makefile targets for common development tasks

# For production deployments, configure AWS credentials
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
```

**Key Environment Variables for Production:**
- `AWS_PROFILE`: Your AWS CLI profile name
- `AWS_REGION`: Target AWS region
- `AWS_ACCOUNT_ID`: Your AWS account ID

**LocalStack Development:**
- Use `make start` to start LocalStack
- Use `make deploy` to deploy infrastructure locally
- See Makefile for all available targets

**Security Note**: Never commit credentials to version control.

## Local Development

### Quick Start with Make

The easiest way to get started is using the Makefile:

```bash
# Start LocalStack
make start

# Build the log processor container
make build

# Deploy infrastructure to LocalStack
make deploy

# Run integration tests
make test-e2e

# View all available targets
make help
```

### Container-Based Development

#### Build Containers
```bash
cd container/

# Build collector container (contains Vector for log collection)
podman build -f Containerfile.collector -t log-collector:latest .

# Build Go-based processor container
podman build -f Containerfile.processor_go -t log-processor:local .

# Or use Make from project root
cd ..
make build
```

#### Run in LocalStack Environment
```bash
# Using Make (recommended)
make run-scan

# Or manually with Podman (after make deploy)
# Get configuration from terraform outputs
S3_BUCKET=$(cd terraform/local && terraform output -raw central_source_bucket)
DYNAMODB_TABLE=$(cd terraform/local && terraform output -raw central_dynamodb_table)
ROLE_ARN=$(cd terraform/local && terraform output -raw central_log_distribution_role_arn)

podman run --rm -it --network rosa-log-router_rosa-network \
  -e AWS_ACCESS_KEY_ID=111111111111 \
  -e AWS_SECRET_ACCESS_KEY=test \
  -e AWS_REGION=us-east-1 \
  -e AWS_ENDPOINT_URL=http://localstack:4566 \
  -e AWS_S3_USE_PATH_STYLE=true \
  -e SOURCE_BUCKET=$S3_BUCKET \
  -e TENANT_CONFIG_TABLE=$DYNAMODB_TABLE \
  -e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=$ROLE_ARN \
  -e SCAN_INTERVAL=10 \
  -e LOG_LEVEL=DEBUG \
  log-processor:local \
  --mode scan
```

#### Production Deployment
For production AWS deployments, see the deployment documentation. Local development uses LocalStack for testing.

## Testing and Validation

### Integration Testing with LocalStack

The project uses Go-based integration tests that run against LocalStack:

#### Run Integration Tests
```bash
# Using Make (recommended)
make test-e2e

# Or manually with Go
cd container
go test -count=1 -tags=integration ./integration -v -timeout 5m
```

#### Validate Vector Flow
```bash
# Test Vector log routing to customer buckets
make validate-vector-flow
```

### Vector Pipeline Testing

For Vector testing in production environments, ensure:
- Namespace labels are correctly configured
- IRSA roles are properly set up
- S3 bucket permissions are validated

```bash
# Check Vector pod status
kubectl get pods -n logging
kubectl describe daemonset vector-logs -n logging
kubectl logs -n logging daemonset/vector-logs --tail=50

# Check Vector metrics endpoint
kubectl port-forward -n logging daemonset/vector-logs 8686:8686
curl http://localhost:8686/metrics
```

### Infrastructure Testing

#### Validate Terraform Configuration
```bash
cd terraform/local

# Initialize Terraform
terraform init

# Validate configuration
terraform validate

# Plan deployment
terraform plan
```

## Health Checks and Debugging

### LocalStack Health
```bash
# Check LocalStack status
curl http://localhost:4566/_localstack/health

# View LocalStack logs
make logs
```

### Vector Status (Production Deployments)
```bash
# Check Vector pod status
kubectl get pods -n logging
kubectl describe daemonset vector-logs -n logging
kubectl logs -n logging daemonset/vector-logs --tail=50

# Check Vector metrics endpoint
kubectl port-forward -n logging daemonset/vector-logs 8686:8686
curl http://localhost:8686/metrics
```

### Tenant Configuration Management (LocalStack)
```bash
# Get table name from terraform
TABLE_NAME=$(cd terraform/local && terraform output -raw central_dynamodb_table)

# List all tenants in LocalStack
aws --endpoint-url=http://localhost:4566 dynamodb scan \
  --table-name $TABLE_NAME

# Check specific tenant configuration
aws --endpoint-url=http://localhost:4566 dynamodb get-item \
  --table-name $TABLE_NAME \
  --key '{"tenant_id":{"S":"customer1"},"type":{"S":"cloudwatch"}}'
```

## Development Workflow

### Code Development
1. **Make changes** to Go code in `container/`
2. **Run unit tests** to verify functionality (if applicable)
3. **Build container** with `make build`
4. **Deploy to LocalStack** with `make deploy`
5. **Run integration tests** with `make test-e2e`
6. **Iterate** on changes as needed

### Container Development
1. **Build locally** with `make build`
2. **Test with LocalStack** using `make deploy` and `make run-scan`
3. **Validate integration** with `make test-e2e`
4. **Review logs** and debug as needed

### Infrastructure Development
1. **Edit Terraform** in `terraform/local/`
2. **Validate changes** with `terraform validate`
3. **Plan deployment** with `make plan`
4. **Deploy changes** with `make deploy`
5. **Verify resources** in LocalStack

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

### Go Processor Tuning
For production deployments, consider:
- Adjusting scan intervals based on log volume
- Tuning batch sizes for S3 operations
- Monitoring memory usage and adjusting container limits
- Optimizing concurrent processing of log files

## Common Development Issues

### LocalStack Not Starting
```bash
# Check Podman socket
systemctl --user status podman.socket
systemctl --user enable --now podman.socket

# Clean and restart
make clean
make start
```

### Container Build Failures
```bash
# Force rebuild without cache
podman build --no-cache -f Containerfile.processor_go -t log-processor:local .

# Check base image availability
podman pull registry.access.redhat.com/ubi9/go-toolset:9.7-1763633888
```

### Integration Tests Failing
- **Verify LocalStack is running**: `make start`
- **Check infrastructure is deployed**: `make deploy`
- **Review LocalStack logs**: `make logs`
- **Warm up Lambda** (if using Lambda mode): `make warmup-lambda`

### Vector Not Collecting Logs (Production)
- **Check namespace labels**: Ensure namespaces have `hypershift.openshift.io/hosted-control-plane=true`
- **Verify IRSA configuration**: Check service account annotations and trust policies
- **Test S3 access**: Manually verify S3WriterRole permissions

## Security Best Practices

### Credential Management
- **Never commit credentials** to version control
- **Use LocalStack** for local testing (no real AWS credentials needed)
- **Use IAM roles** for production deployments
- **Implement least privilege** access for all components

### Testing Security
- **Use LocalStack** for local testing (isolated environment)
- **Test with minimal permissions** to verify least privilege
- **Validate role assumptions** in cross-account scenarios

## Documentation and Resources

### Architecture References
- **[System Design](DESIGN.md)**: Comprehensive architecture documentation
- **[Deployment Guide](docs/deployment-guide.md)**: Infrastructure deployment instructions
- **[Troubleshooting Guide](docs/troubleshooting.md)**: Common issues and solutions

### Component-Specific Guides
- **[Terraform Infrastructure](terraform/local/README.md)**: LocalStack development environment
- **[Kubernetes Deployment](k8s/README.md)**: Vector and processor deployment
- **[API Management](api/README.md)**: Tenant configuration API
- **[Makefile](Makefile)**: Development workflow automation

### External Documentation
- **[Vector Documentation](https://vector.dev/docs/)**: Log collection and routing
- **[LocalStack Documentation](https://docs.localstack.cloud/)**: Local AWS testing
- **[OpenShift SecurityContextConstraints](https://docs.openshift.com/container-platform/latest/authentication/managing-security-context-constraints.html)**: Production deployments

## Contributing

### Code Standards
- **Follow existing patterns** in Go code and infrastructure
- **Write integration tests** for new functionality
- **Update documentation** for any changes
- **Test with LocalStack** before submitting changes

### Testing Requirements
- **Integration tests must pass**: `make test-e2e`
- **Container builds must succeed**: `make build`
- **Infrastructure validation**: `terraform validate` in terraform/local/
- **LocalStack deployment**: Test end-to-end with `make deploy`

### Pull Request Process
1. **Create feature branch** from main
2. **Implement changes** with tests
3. **Validate locally** with `make test-e2e`
4. **Update documentation** as needed
5. **Submit PR** with detailed description of changes