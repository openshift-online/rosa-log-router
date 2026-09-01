# Makefile for local development with LocalStack
#
# Container engine auto-detection: checks which daemon is running (docker first, then podman).
# Override with: make CONTAINER_ENGINE=podman build
# The DOCKER_SOCK variable controls which socket is mounted for LocalStack.
# Override with: make DOCKER_SOCK=/var/run/docker.sock start
CONTAINER_ENGINE ?= $(shell \
	if docker info >/dev/null 2>&1; then \
		echo docker; \
	elif podman info >/dev/null 2>&1; then \
		echo podman; \
	else \
		echo docker; \
	fi)

# On macOS, use docker-compose.macos.yml override to fix SELinux and socket issues.
ifeq ($(shell uname),Darwin)
  COMPOSE := $(CONTAINER_ENGINE) compose -f docker-compose.yml -f docker-compose.macos.yml
else
  COMPOSE := $(CONTAINER_ENGINE) compose
endif

# Platform flag for container builds — LocalStack Lambda requires linux/amd64.
# On arm64 hosts (Apple Silicon), cross-compile. On amd64, no flag needed.
BUILD_PLATFORM := $(shell uname -m | grep -q arm64 && echo "--platform linux/amd64" || echo "")

# Docker socket auto-detection for LocalStack container mounts.
# macOS + Podman: /var/run/docker.sock (symlink inside Podman VM)
# Linux + Podman: /run/user/$UID/podman/podman.sock
# Docker Desktop: /var/run/docker.sock
DOCKER_SOCK ?= $(shell \
	if [ "$$(uname)" = "Darwin" ]; then \
		echo "/var/run/docker.sock"; \
	elif [ -S "/run/user/$$(id -u)/podman/podman.sock" ]; then \
		echo "/run/user/$$(id -u)/podman/podman.sock"; \
	else \
		echo "/var/run/docker.sock"; \
	fi)

.PHONY: help start stop logs build build-api build-all deploy deploy-wo-lambda deploy-api init plan outputs test-api destroy test-e2e test-e2e-quick warmup-lambda test-e2e-with-warmup validate-vector-flow clean reset run-scan run-scan-background

help: ## Show this help message
	@echo "Rosa Log Router - Local Multi-Account Testing"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Detected: CONTAINER_ENGINE=$(CONTAINER_ENGINE), DOCKER_SOCK=$(DOCKER_SOCK)"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

start: ## Start LocalStack
	@echo "Ensuring container socket is available..."
	@systemctl --user enable --now podman.socket 2>/dev/null || true
	@echo "Starting LocalStack (engine: $(CONTAINER_ENGINE), socket: $(DOCKER_SOCK))..."
	DOCKER_SOCK=$(DOCKER_SOCK) $(COMPOSE) up -d
	@echo "Waiting for LocalStack to be ready..."
	@timeout 120 bash -c 'until curl -sf http://localhost:4566/_localstack/health > /dev/null 2>&1; do echo "  Waiting for LocalStack health check..."; sleep 5; done' || { echo "❌ LocalStack failed to become healthy"; $(COMPOSE) logs localstack | tail -50; exit 1; }
	@echo "✅ LocalStack is healthy and ready"
	@$(COMPOSE) logs localstack | tail -20

stop: ## Stop LocalStack
	@echo "Stopping LocalStack..."
	$(COMPOSE) down

logs: ## Show LocalStack logs
	$(COMPOSE) logs -f localstack

build: ## Build log processor container
	@echo "Building log processor container ($(CONTAINER_ENGINE) $(BUILD_PLATFORM))..."
	cd container && $(CONTAINER_ENGINE) build $(BUILD_PLATFORM) -f Containerfile.processor_go -t log-processor:local .
	@echo "✅ Container image built: log-processor:local"

build-api: ## Build API service and authorizer containers
	@echo "Building API containers..."
	cd api && $(CONTAINER_ENGINE) build $(BUILD_PLATFORM) -f Containerfile.api -t api-service:local .
	cd api && $(CONTAINER_ENGINE) build $(BUILD_PLATFORM) -f Containerfile.authorizer -t api-authorizer:local .
	@echo "✅ API container images built: api-service:local, api-authorizer:local"

build-all: build build-api ## Build all containers (processor + API)

init: ## Initialize Terraform
	@echo "Initializing Terraform..."
	cd terraform/local && terraform init

plan: init ## Plan Terraform deployment
	@echo "Planning Terraform deployment..."
	cd terraform/local && terraform plan

deploy: build init ## Deploy infrastructure with Lambda container
	@echo "Deploying to LocalStack with Lambda container..."
	@echo "⚠️  Note: LocalStack Pro required for Lambda container support"
	@echo "Step 1: Creating ECR repository..."
	cd terraform/local && terraform apply -auto-approve -target=aws_ecr_repository.lambda_processor
	@echo "Step 2: Tagging and pushing container to ECR..."
	@ECR_URL=$$(cd terraform/local && terraform output -raw ecr_repository_url 2>/dev/null); \
	$(CONTAINER_ENGINE) tag log-processor:local "$$ECR_URL:local" && \
	if $(CONTAINER_ENGINE) info 2>&1 | grep -qi podman; then \
		echo "Detected Podman - using Podman-specific flags for LocalStack ECR"; \
		$(CONTAINER_ENGINE) push "$$ECR_URL:local" --format docker --tls-verify=false --remove-signatures; \
	else \
		$(CONTAINER_ENGINE) push "$$ECR_URL:local"; \
	fi
	@echo "Step 3: Deploying infrastructure..."
	cd terraform/local && terraform apply -auto-approve
	@echo ""
	@echo "✅ Infrastructure deployed with Lambda container!"
	@echo ""
	@cd terraform/local && terraform output test_commands

deploy-wo-lambda: build init ## Deploy infrastructure without Lambda (for scan mode)
	@echo "Deploying to LocalStack without Lambda (for scan mode)..."
	cd terraform/local && terraform apply -auto-approve -var="deploy_lambda=false"
	@echo ""
	@echo "✅ Infrastructure deployed! Ready for container scan mode."
	@echo ""
	@echo "Run 'make run-scan' to start the processor in scan mode"

deploy-api: build build-api init ## Deploy infrastructure with API containers
	@echo "Deploying API to LocalStack..."
	@echo "⚠️  Note: LocalStack Pro required for Lambda container support"
	@echo "Step 1: Creating ECR repositories..."
	cd terraform/local && terraform apply -auto-approve \
		-target=aws_ecr_repository.lambda_processor \
		-target=aws_ecr_repository.api_service \
		-target=aws_ecr_repository.api_authorizer
	@echo "Step 2: Tagging and pushing processor container to ECR..."
	@ECR_PROCESSOR=$$(cd terraform/local && terraform output -raw ecr_repository_url 2>/dev/null); \
	$(CONTAINER_ENGINE) tag log-processor:local "$$ECR_PROCESSOR:local" && \
	if $(CONTAINER_ENGINE) info 2>&1 | grep -qi podman; then \
		$(CONTAINER_ENGINE) push "$$ECR_PROCESSOR:local" --format docker --tls-verify=false --remove-signatures; \
	else \
		$(CONTAINER_ENGINE) push "$$ECR_PROCESSOR:local"; \
	fi
	@echo "Step 3: Tagging and pushing API containers to ECR..."
	@ECR_API_SERVICE=$$(cd terraform/local && terraform output -raw ecr_api_service_url 2>/dev/null); \
	ECR_API_AUTHORIZER=$$(cd terraform/local && terraform output -raw ecr_api_authorizer_url 2>/dev/null); \
	$(CONTAINER_ENGINE) tag api-service:local "$$ECR_API_SERVICE:local" && \
	$(CONTAINER_ENGINE) tag api-authorizer:local "$$ECR_API_AUTHORIZER:local" && \
	if $(CONTAINER_ENGINE) info 2>&1 | grep -qi podman; then \
		$(CONTAINER_ENGINE) push "$$ECR_API_SERVICE:local" --format docker --tls-verify=false --remove-signatures && \
		$(CONTAINER_ENGINE) push "$$ECR_API_AUTHORIZER:local" --format docker --tls-verify=false --remove-signatures; \
	else \
		$(CONTAINER_ENGINE) push "$$ECR_API_SERVICE:local" && \
		$(CONTAINER_ENGINE) push "$$ECR_API_AUTHORIZER:local"; \
	fi
	@echo "Step 4: Deploying full infrastructure..."
	cd terraform/local && terraform apply -auto-approve
	@echo ""
	@echo "✅ Infrastructure deployed with API!"
	@echo ""
	@cd terraform/local && terraform output test_commands

outputs: ## Show Terraform outputs
	@cd terraform/local && terraform output

test-api: ## Test API health endpoint
	@echo "Testing API health endpoint..."
	@API_ENDPOINT=$$(cd terraform/local && terraform output -raw api_gateway_endpoint 2>/dev/null); \
	curl -v "$$API_ENDPOINT/api/v1/health"

destroy: ## Destroy Terraform infrastructure
	@echo "Destroying infrastructure..."
	cd terraform/local && terraform destroy -auto-approve

test-e2e: ## Run integration tests (with prerequisite check)
	@echo "🧪 Running integration tests..."
	@echo ""
	@echo "Prerequisites:"
	@echo "  1. LocalStack running (make start)"
	@echo "  2. Infrastructure deployed with Lambda container:"
	@echo "     - make deploy"
	@echo "        Note: Requires LocalStack Pro (Lambda containers)"
	@echo ""
	@echo ""
	cd container && go test -count=1 -tags=integration ./integration -v -timeout 5m

test-e2e-quick: ## Run integration tests without prerequisite check
	@echo "🧪 Running integration tests..."
	cd container && go test -count=1 -tags=integration ./integration -v -timeout 5m

warmup-lambda: ## Warm up Lambda container (addresses LocalStack+Podman cold start issue)
	@echo "🔥 Warming up Lambda container..."
	@bash scripts/warmup-lambda.sh

test-e2e-with-warmup: ## Run integration tests with Lambda warmup
	@echo "🧪 Running integration tests with Lambda warmup..."
	@echo ""
	@$(MAKE) warmup-lambda
	@echo ""
	@echo "✅ Lambda warmed up, running full test suite..."
	@echo ""
	@$(MAKE) test-e2e-quick

validate-vector-flow: ## Validate Vector is routing logs to customer buckets correctly
	@bash scripts/validate-vector-flow.sh

clean: stop ## Stop LocalStack and clean up all local state
	$(COMPOSE) down -v
	@echo "Cleaning up Terraform state..."
	@rm -rf terraform/local/.terraform
	@rm -f terraform/local/.terraform.lock.hcl
	@rm -f terraform/local/terraform.tfstate
	@rm -f terraform/local/terraform.tfstate.backup
	@echo "Cleaning up build artifacts..."
	@rm -f terraform/local/log-processor.zip
	@echo "✅ Cleaned up"

reset: clean start deploy ## Full reset: clean, start, and deploy
	@echo "✅ Environment reset complete"

run-scan: ## Run container in scan mode (requires deploy-wo-lambda first)
	@echo "Starting log processor in scan mode..."
	@S3_BUCKET=$$(cd terraform/local && terraform output -raw central_source_bucket 2>/dev/null); \
	DYNAMODB_TABLE=$$(cd terraform/local && terraform output -raw central_dynamodb_table 2>/dev/null); \
	ROLE_ARN=$$(cd terraform/local && terraform output -raw central_log_distribution_role_arn 2>/dev/null); \
	echo "Configuration:"; \
	echo "  S3 Bucket: $$S3_BUCKET"; \
	echo "  DynamoDB Table: $$DYNAMODB_TABLE"; \
	echo "  Role ARN: $$ROLE_ARN"; \
	echo "  S3 Path Style: true (LocalStack)"; \
	echo ""; \
	$(CONTAINER_ENGINE) run --rm -it --network rosa-log-router_rosa-network \
		-e AWS_ACCESS_KEY_ID=111111111111 \
		-e AWS_SECRET_ACCESS_KEY=test \
		-e AWS_REGION=us-east-1 \
		-e AWS_ENDPOINT_URL=http://localstack:4566 \
		-e AWS_S3_USE_PATH_STYLE=true \
		-e SOURCE_BUCKET=$$S3_BUCKET \
		-e TENANT_CONFIG_TABLE=$$DYNAMODB_TABLE \
		-e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=$$ROLE_ARN \
		-e SCAN_INTERVAL=10 \
		-e LOG_LEVEL=DEBUG \
		log-processor:local \
		--mode scan

run-scan-background: ## Run container in scan mode in background
	@echo "Starting log processor in scan mode (background)..."
	@S3_BUCKET=$$(cd terraform/local && terraform output -raw central_source_bucket 2>/dev/null); \
	DYNAMODB_TABLE=$$(cd terraform/local && terraform output -raw central_dynamodb_table 2>/dev/null); \
	ROLE_ARN=$$(cd terraform/local && terraform output -raw central_log_distribution_role_arn 2>/dev/null); \
	echo "Configuration:"; \
	echo "  S3 Bucket: $$S3_BUCKET"; \
	echo "  DynamoDB Table: $$DYNAMODB_TABLE"; \
	echo "  Role ARN: $$ROLE_ARN"; \
	echo ""; \
	$(CONTAINER_ENGINE) run --rm -d --name rosa-processor --network rosa-log-router_rosa-network \
		-e AWS_ACCESS_KEY_ID=111111111111 \
		-e AWS_SECRET_ACCESS_KEY=test \
		-e AWS_REGION=us-east-1 \
		-e AWS_ENDPOINT_URL=http://localstack:4566 \
		-e AWS_S3_USE_PATH_STYLE=true \
		-e SOURCE_BUCKET=$$S3_BUCKET \
		-e TENANT_CONFIG_TABLE=$$DYNAMODB_TABLE \
		-e CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=$$ROLE_ARN \
		-e SCAN_INTERVAL=10 \
		-e LOG_LEVEL=DEBUG \
		log-processor:local \
		--mode scan
	@echo "✅ Processor running in background (container: rosa-processor)"

.DEFAULT_GOAL := help
