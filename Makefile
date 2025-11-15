# Makefile for local development with LocalStack

# Configuration
# Set to 'true' to use container image instead of zip (requires LocalStack Pro)
USE_CONTAINER ?= false
# Tag for Lambda container image
LAMBDA_IMAGE_TAG ?= latest

.PHONY: help start stop logs build build-py build-go build-zip build-lambda-image push-lambda-image init plan deploy deploy-pyzip deploy-py deploy-go deploy-go-wo-lambda deploy-container outputs destroy test-e2e-go test-e2e-go-quick warmup-lambda test-e2e-go-with-warmup validate-vector-flow clean reset run-go-scan run-go-scan-background

help: ## Show this help message
	@echo "Rosa Log Router - Local Multi-Account Testing"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

start: ## Start LocalStack
	@echo "Ensuring Podman socket is available..."
	@systemctl --user enable --now podman.socket 2>/dev/null || true
	@echo "Starting LocalStack..."
	docker compose up -d
	@echo "Waiting for LocalStack to be ready..."
	@timeout 120 bash -c 'until curl -sf http://localhost:4566/_localstack/health > /dev/null 2>&1; do echo "  Waiting for LocalStack health check..."; sleep 5; done' || { echo "❌ LocalStack failed to become healthy"; docker compose logs localstack | tail -50; exit 1; }
	@echo "✅ LocalStack is healthy and ready"
	@docker compose logs localstack | tail -20

stop: ## Stop LocalStack
	@echo "Stopping LocalStack..."
	docker compose down

logs: ## Show LocalStack logs
	docker compose logs -f localstack

build: build-py ## Build Python container image (default)

build-py: ## Build Python container image
	@echo "Building Python log processor container..."
	cd container && docker build -f Containerfile.processor -t log-processor:local-py .
	@echo "✅ Container image built: log-processor:local-py"

build-go: ## Build Go container image
	@echo "Building Go log processor container..."
	cd container && docker build -f Containerfile.processor_go -t log-processor:local-go .
	@echo "✅ Go container image built: log-processor:local-go"

build-zip: ## Build Python Lambda zip file for local testing
	@echo "Building Lambda deployment package..."
	@bash terraform/modules/regional/modules/lambda-stack/build_zip.sh terraform/local/log-processor.zip
	@echo "✅ Lambda zip built: terraform/local/log-processor.zip"

build-lambda-image: ## Build Lambda container image locally (doesn't push)
	@echo "Building Lambda container image..."
	cd container && docker build -f Containerfile.processor -t log-processor:$(LAMBDA_IMAGE_TAG) .
	@echo "✅ Container image built: log-processor:$(LAMBDA_IMAGE_TAG)"

push-lambda-image: ## Push Lambda container to LocalStack ECR (run after terraform apply)
	@echo "Pushing Lambda container to LocalStack ECR..."
	@bash scripts/build-and-push-lambda.sh $(LAMBDA_IMAGE_TAG)

init: ## Initialize Terraform
	@echo "Initializing Terraform..."
	cd terraform/local && terraform init

plan: init ## Plan Terraform deployment
	@echo "Planning Terraform deployment..."
	cd terraform/local && terraform plan

deploy: init ## Deploy full infrastructure with Lambda (Python zip or container)
ifeq ($(USE_CONTAINER),true)
	@echo "Deploying to LocalStack with Lambda (container image)..."
	@echo "Step 1: Building container image..."
	@$(MAKE) build-lambda-image
	@echo "Step 2: Creating ECR repository..."
	cd terraform/local && terraform apply -auto-approve -target=aws_ecr_repository.lambda_processor
	@echo "Step 3: Pushing container image to ECR..."
	@$(MAKE) push-lambda-image
	@echo "Step 4: Deploying full infrastructure..."
	cd terraform/local && terraform apply -auto-approve -var="use_container_image=true" -var="lambda_image_tag=$(LAMBDA_IMAGE_TAG)"
else
	@echo "Deploying to LocalStack with Lambda (zip)..."
	@$(MAKE) build-zip
	cd terraform/local && terraform apply -auto-approve
endif
	@echo ""
	@echo "✅ Infrastructure deployed!"
	@echo ""
	@cd terraform/local && terraform output test_commands

deploy-container: ## Deploy with container image (shortcut for USE_CONTAINER=true)
	@$(MAKE) deploy USE_CONTAINER=true

deploy-pyzip: build-zip init ## Deploy full infrastructure with Python Lambda zip file
	@echo "Deploying to LocalStack with Python Lambda zip file..."
	cd terraform/local && terraform apply -auto-approve
	@echo ""
	@echo "✅ Infrastructure deployed with Python Lambda zip!"
	@echo ""
	@cd terraform/local && terraform output test_commands

deploy-py: build-py init ## Deploy full infrastructure with Python Lambda container
	@echo "Deploying to LocalStack with Python Lambda container..."
	@echo "⚠️  Note: LocalStack Pro required for Lambda container support"
	@echo "Step 1: Creating ECR repository..."
	cd terraform/local && terraform apply -auto-approve -target=aws_ecr_repository.lambda_processor
	@echo "Step 2: Tagging and pushing Python container to ECR..."
	@ECR_URL=$$(cd terraform/local && terraform output -raw ecr_repository_url 2>/dev/null); \
	docker tag log-processor:local-py $$ECR_URL:py && \
	docker push $$ECR_URL:py
	@echo "Step 3: Deploying infrastructure..."
	cd terraform/local && terraform apply -auto-approve -var="use_container_image=true" -var="lambda_image_tag=py"
	@echo ""
	@echo "✅ Infrastructure deployed with Python Lambda container!"
	@echo ""
	@cd terraform/local && terraform output test_commands

deploy-go: build-go init ## Deploy infrastructure with Go Lambda container
	@echo "Deploying to LocalStack with Go Lambda container..."
	@echo "⚠️  Note: LocalStack Pro required for Lambda container support"
	@echo "Step 1: Creating ECR repository..."
	cd terraform/local && terraform apply -auto-approve -target=aws_ecr_repository.lambda_processor
	@echo "Step 2: Tagging and pushing Go container to ECR..."
	@ECR_URL=$$(cd terraform/local && terraform output -raw ecr_repository_url 2>/dev/null); \
	docker tag log-processor:local-go $$ECR_URL:go && \
	docker push $$ECR_URL:go
	@echo "Step 3: Deploying infrastructure..."
	cd terraform/local && terraform apply -auto-approve -var="use_container_image=true" -var="lambda_image_tag=go"
	@echo ""
	@echo "✅ Infrastructure deployed with Go Lambda container!"
	@echo ""
	@cd terraform/local && terraform output test_commands

deploy-go-wo-lambda: build-go init ## Deploy infrastructure without Lambda (for Go scan mode)
	@echo "Deploying to LocalStack without Lambda (for Go scan mode)..."
	cd terraform/local && terraform apply -auto-approve -var="deploy_lambda=false"
	@echo ""
	@echo "✅ Infrastructure deployed! Ready for Go container scan mode."
	@echo ""
	@echo "Run 'make run-go-scan' to start the Go processor in scan mode"

outputs: ## Show Terraform outputs
	@cd terraform/local && terraform output

destroy: ## Destroy Terraform infrastructure
	@echo "Destroying infrastructure..."
	cd terraform/local && terraform destroy -auto-approve

test-e2e-go: ## Run Go integration tests (with prerequisite check)
	@echo "🧪 Running Go integration tests..."
	@echo ""
	@echo "Prerequisites:"
	@echo "  1. LocalStack running (make start)"
	@echo "  2. Infrastructure deployed:"
	@echo "     - For Python Lambda: make deploy"
	@echo "     - For Go rewrite (scan mode): make deploy-go + make run-go-scan"
	@echo "        Note: Go container mode requires LocalStack Pro (Lambda containers)"
	@echo ""
	@read -p "Press Enter to continue if prerequisites are met (Ctrl+C to cancel)..."
	@echo ""
	cd container && go test -count=1 -tags=integration ./integration -v -timeout 5m

test-e2e-go-quick: ## Run Go integration tests without prerequisite check
	@echo "🧪 Running Go integration tests..."
	cd container && go test -count=1 -tags=integration ./integration -v -timeout 5m

warmup-lambda: ## Warm up Lambda container (addresses LocalStack+Podman cold start issue)
	@echo "🔥 Warming up Lambda container..."
	@bash scripts/warmup-lambda.sh

test-e2e-go-with-warmup: ## Run Go integration tests with Lambda warmup
	@echo "🧪 Running Go integration tests with Lambda warmup..."
	@echo ""
	@$(MAKE) warmup-lambda
	@echo ""
	@echo "✅ Lambda warmed up, running full test suite..."
	@echo ""
	@$(MAKE) test-e2e-go-quick

validate-vector-flow: ## Validate Vector is routing logs to customer buckets correctly
	@bash scripts/validate-vector-flow.sh

clean: stop ## Stop LocalStack and clean up all local state
	docker compose down -v
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

run-go-scan: ## Run Go container in scan mode (requires deploy-go-wo-lambda first)
	@echo "Starting Go log processor in scan mode..."
	@S3_BUCKET=$$(cd terraform/local && terraform output -raw central_source_bucket 2>/dev/null); \
	DYNAMODB_TABLE=$$(cd terraform/local && terraform output -raw central_dynamodb_table 2>/dev/null); \
	ROLE_ARN=$$(cd terraform/local && terraform output -raw central_log_distribution_role_arn 2>/dev/null); \
	echo "Configuration:"; \
	echo "  S3 Bucket: $$S3_BUCKET"; \
	echo "  DynamoDB Table: $$DYNAMODB_TABLE"; \
	echo "  Role ARN: $$ROLE_ARN"; \
	echo "  S3 Path Style: true (LocalStack)"; \
	echo ""; \
	docker run --rm -it --network rosa-log-router_rosa-network \
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
		log-processor:local-go \
		--mode scan

run-go-scan-background: ## Run Go container in scan mode in background
	@echo "Starting Go log processor in scan mode (background)..."
	@S3_BUCKET=$$(cd terraform/local && terraform output -raw central_source_bucket 2>/dev/null); \
	DYNAMODB_TABLE=$$(cd terraform/local && terraform output -raw central_dynamodb_table 2>/dev/null); \
	ROLE_ARN=$$(cd terraform/local && terraform output -raw central_log_distribution_role_arn 2>/dev/null); \
	echo "Configuration:"; \
	echo "  S3 Bucket: $$S3_BUCKET"; \
	echo "  DynamoDB Table: $$DYNAMODB_TABLE"; \
	echo "  Role ARN: $$ROLE_ARN"; \
	echo ""; \
	docker run --rm -d --name rosa-go-processor --network rosa-log-router_rosa-network \
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
		log-processor:local-go \
		--mode scan
	@echo "✅ Go processor running in background (container: rosa-go-processor)"

.DEFAULT_GOAL := help
