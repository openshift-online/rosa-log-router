# LocalStack Container-Based Lambda Deployment

This guide explains how to use container images for Lambda deployment in LocalStack (requires LocalStack Pro).

## Quick Start

### Deploy with Container Image (LocalStack Pro)

```bash
# Start LocalStack Pro
make start

# Deploy with container image
make deploy-container

# Or use the environment variable
USE_CONTAINER=true make deploy
```

### Deploy with Zip File (Default)

```bash
# Start LocalStack
make start

# Deploy with zip (default)
make deploy
```

## How It Works

The deployment system supports two modes controlled by the `USE_CONTAINER` environment variable:

### Container Mode (`USE_CONTAINER=true`)
1. **Build**: Builds the Python container using `container/Containerfile.processor`
2. **Push**: Pushes the image to LocalStack's internal ECR repository
3. **Deploy**: Terraform creates Lambda function with `package_type = "Image"`

### Zip Mode (default, `USE_CONTAINER=false`)
1. **Build**: Creates a Python zip file with dependencies
2. **Deploy**: Terraform creates Lambda function with `package_type = "Zip"`

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make deploy` | Deploy with zip (default) or container (if `USE_CONTAINER=true`) |
| `make deploy-container` | Shortcut for container deployment |
| `make build-push-lambda` | Build and push container to LocalStack ECR |
| `make build-zip` | Build Python zip file |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_CONTAINER` | `false` | Use container image instead of zip |
| `LAMBDA_IMAGE_TAG` | `latest` | Tag for Lambda container image |

## Examples

### Deploy with specific image tag

```bash
USE_CONTAINER=true LAMBDA_IMAGE_TAG=v1.2.3 make deploy
```

### Rebuild and redeploy container

```bash
# Build and push new image
make build-push-lambda LAMBDA_IMAGE_TAG=test

# Deploy with new tag
cd terraform/local
terraform apply -var="use_container_image=true" -var="lambda_image_tag=test"
```

### Switch from zip to container

```bash
# Initial deployment with zip
make deploy

# Switch to container
USE_CONTAINER=true make deploy
```

## Architecture

### Container Image Structure

The `Containerfile.processor` creates a multi-mode container that works with:
- **Lambda Runtime**: Uses `awslambdaric` when `EXECUTION_MODE=lambda`
- **SQS Polling**: Direct SQS polling when `EXECUTION_MODE=sqs`
- **Manual Testing**: Stdin/stdout mode when `EXECUTION_MODE=manual`

### LocalStack ECR Integration

When using LocalStack Pro, the system:
1. Creates an ECR repository via Terraform: `multi-tenant-logging-int-log-processor`
2. Pushes container images to `localhost:4566/ecr`
3. Lambda pulls from the LocalStack ECR repository

### Terraform Configuration

The Lambda function resource (`terraform/local/main.tf`) supports both modes:

```hcl
resource "aws_lambda_function" "central_log_distributor" {
  package_type = var.use_container_image ? "Image" : "Zip"

  # For zip deployment
  filename         = var.use_container_image ? null : var.lambda_zip_path
  handler          = var.use_container_image ? null : "log_processor.lambda_handler"
  runtime          = var.use_container_image ? null : "python3.13"

  # For container deployment
  image_uri = var.use_container_image ? "${aws_ecr_repository.lambda_processor.repository_url}:${var.lambda_image_tag}" : null
}
```

## Troubleshooting

### Container push fails

**Error**: `Error: ECR repository not found`

**Solution**: Run terraform first to create the ECR repository:
```bash
cd terraform/local
terraform apply -target=aws_ecr_repository.lambda_processor
```

### Lambda can't pull image

**Error**: Lambda invocation fails with image pull error

**Solution**: Verify the image exists in LocalStack ECR:
```bash
AWS_ACCESS_KEY_ID=111111111111 aws --endpoint-url=http://localhost:4566 \
  ecr describe-images \
  --repository-name multi-tenant-logging-int-log-processor
```

### Container mode requires LocalStack Pro

**Error**: Container images not supported

**Solution**: Ensure LocalStack Pro is running with auth token:
```bash
# Check docker-compose.yml has LOCALSTACK_AUTH_TOKEN set
docker compose logs localstack | grep -i "pro"
```

## Benefits of Container Mode

1. **Production Parity**: Same container image can be deployed to AWS Lambda
2. **Faster Iteration**: No need to rebuild zip on dependency changes
3. **Multi-Mode**: Same image works for Lambda, SQS polling, and manual testing
4. **Better Testing**: Test exact production image locally

## Migration Path

The system supports gradual migration:

1. **Stage 1**: Use zip for LocalStack testing (current default)
2. **Stage 2**: Add container deployment for LocalStack Pro users
3. **Stage 3**: Use containers for both LocalStack and AWS production
4. **Stage 4**: Deprecate zip deployment entirely

## See Also

- [LocalStack Lambda Container Images](https://docs.localstack.cloud/user-guide/aws/lambda/#container-images)
- [AWS Lambda Container Images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
- [Main Development Guide](../CLAUDE.md)
