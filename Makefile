# Makefile for local development with LocalStack

.PHONY: help start stop logs build deploy test clean validate-vector-flow

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
	@sleep 10
	@docker compose logs localstack | tail -20
	@echo "✅ LocalStack is running at http://localhost:4566"

stop: ## Stop LocalStack
	@echo "Stopping LocalStack..."
	docker compose down

logs: ## Show LocalStack logs
	docker compose logs -f localstack

build: ## Build Python container image
	@echo "Building Python log processor container..."
	cd container && docker build -f Containerfile.processor -t log-processor:local .
	@echo "✅ Container image built: log-processor:local"

build-go: ## Build Go container image
	@echo "Building Go log processor container..."
	cd container && docker build -f Containerfile.processor_go -t log-processor-go:local .
	@echo "✅ Go container image built: log-processor-go:local"

build-zip: ## Build Python Lambda zip file for local testing
	@echo "Building Lambda deployment package..."
	@bash terraform/modules/regional/modules/lambda-stack/build_zip.sh terraform/local/log-processor.zip
	@echo "✅ Lambda zip built: terraform/local/log-processor.zip"

init: ## Initialize Terraform
	@echo "Initializing Terraform..."
	cd terraform/local && terraform init

plan: init ## Plan Terraform deployment
	@echo "Planning Terraform deployment..."
	cd terraform/local && terraform plan

deploy: build-zip init ## Deploy full infrastructure with Lambda (Python)
	@echo "Deploying to LocalStack with Lambda..."
	cd terraform/local && terraform apply -auto-approve
	@echo ""
	@echo "✅ Infrastructure deployed with Lambda!"
	@echo ""
	@cd terraform/local && terraform output test_commands

deploy-go: build-go init ## Deploy infrastructure without Lambda (for Go scan mode)
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

test-upload-customer-1: ## Upload a test log file for Customer 1 (ACME Corp)
	@echo "Creating test log file for Customer 1 (ACME Corp)..."
	@TIMESTAMP=$$(date +%s); \
	echo '{"timestamp":"'$$(date -Iseconds)'","message":"Test from Makefile","level":"INFO","service":"payment-service","customer":"acme-corp"}' | gzip > /tmp/test-acme-$$TIMESTAMP.json.gz; \
	echo "Uploading to central bucket..."; \
	SOURCE_BUCKET=$$(cd terraform/local && terraform output -raw central_source_bucket 2>/dev/null); \
	aws --endpoint-url=http://localhost:4566 s3 cp /tmp/test-acme-$$TIMESTAMP.json.gz \
		s3://$$SOURCE_BUCKET/test-cluster/acme-corp/payment-service/pod-123/test-$$TIMESTAMP.json.gz; \
	rm -f /tmp/test-acme-$$TIMESTAMP.json.gz
	@echo "✅ Log uploaded for Customer 1 (should trigger S3 → SNS → SQS → Lambda)"

test-upload-customer-2: ## Upload a test log file for Customer 2 (Globex Industries)
	@echo "Creating test log file for Customer 2 (Globex Industries)..."
	@TIMESTAMP=$$(date +%s); \
	echo '{"timestamp":"'$$(date -Iseconds)'","message":"Test from Makefile","level":"INFO","service":"platform-api","customer":"globex-industries"}' | gzip > /tmp/test-globex-$$TIMESTAMP.json.gz; \
	echo "Uploading to central bucket..."; \
	SOURCE_BUCKET=$$(cd terraform/local && terraform output -raw central_source_bucket 2>/dev/null); \
	aws --endpoint-url=http://localhost:4566 s3 cp /tmp/test-globex-$$TIMESTAMP.json.gz \
		s3://$$SOURCE_BUCKET/test-cluster/globex-industries/platform-api/pod-456/test-$$TIMESTAMP.json.gz; \
	rm -f /tmp/test-globex-$$TIMESTAMP.json.gz
	@echo "✅ Log uploaded for Customer 2 (should trigger S3 → SNS → SQS → Lambda)"

test-upload: test-upload-customer-1 test-upload-customer-2 ## Upload test logs for both customers

test-logs: ## Show Lambda logs
	@echo "Lambda logs (last 5 minutes):"
	@LAMBDA=$$(cd terraform/local && terraform output -raw central_lambda_function 2>/dev/null); \
	aws --endpoint-url=http://localhost:4566 logs tail \
		/aws/lambda/$$LAMBDA --since 5m || echo "No logs yet"

test-check-central: ## Check resources in central account
	@echo "Central Account (111111111111) Resources:"
	@echo ""
	@echo "S3 Buckets:"
	@AWS_ACCESS_KEY_ID=111111111111 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 s3 ls
	@echo ""
	@echo "DynamoDB Tables:"
	@AWS_ACCESS_KEY_ID=111111111111 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 dynamodb list-tables
	@echo ""
	@echo "Tenant Configs:"
	@TABLE=$$(cd terraform/local && terraform output -raw central_dynamodb_table 2>/dev/null); \
	AWS_ACCESS_KEY_ID=111111111111 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 \
		dynamodb scan --table-name $$TABLE --output table

test-check-customer1: ## Check Customer 1 (ACME Corp) resources
	@echo "Customer 1 - ACME Corp (222222222222) Resources:"
	@echo ""
	@echo "S3 Buckets:"
	@AWS_ACCESS_KEY_ID=222222222222 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 s3 ls
	@echo ""
	@BUCKET=$$(cd terraform/local && terraform output -raw customer1_bucket 2>/dev/null); \
	echo "Logs in bucket:"; \
	AWS_ACCESS_KEY_ID=222222222222 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 \
		s3 ls s3://$$BUCKET/logs/ --recursive || echo "(empty)"

test-check-customer2: ## Check Customer 2 (Globex) resources
	@echo "Customer 2 - Globex Industries (333333333333) Resources:"
	@echo ""
	@echo "S3 Buckets:"
	@AWS_ACCESS_KEY_ID=333333333333 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 s3 ls
	@echo ""
	@BUCKET=$$(cd terraform/local && terraform output -raw customer2_bucket 2>/dev/null); \
	echo "Logs in bucket:"; \
	AWS_ACCESS_KEY_ID=333333333333 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 \
		s3 ls s3://$$BUCKET/platform-logs/ --recursive || echo "(empty)"

test-assume-role: ## Test cross-account AssumeRole
	@echo "Testing AssumeRole from central account to customer account..."
	@ROLE_ARN=$$(cd terraform/local && terraform output -raw customer1_role_arn 2>/dev/null); \
	CENTRAL_ID=$$(cd terraform/local && terraform output -raw central_account_id 2>/dev/null); \
	echo "Assuming role: $$ROLE_ARN"; \
	AWS_ACCESS_KEY_ID=$$CENTRAL_ID AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 \
		sts assume-role \
		--role-arn $$ROLE_ARN \
		--role-session-name test-session \
		--external-id $$CENTRAL_ID

test-customer-1: test-upload-customer-1 ## Upload and check Customer 1 (ACME Corp)
	@echo ""
	@echo "Waiting 5 seconds for processing..."
	@sleep 5
	@echo ""
	@make test-check-customer1

test-customer-2: test-upload-customer-2 ## Upload and check Customer 2 (Globex)
	@echo ""
	@echo "Waiting 5 seconds for processing..."
	@sleep 5
	@echo ""
	@make test-check-customer2

test-all: test-upload ## Run full test workflow for both customers
	@echo ""
	@echo "Waiting 10 seconds for processing..."
	@sleep 10
	@echo ""
	@make test-logs
	@echo ""
	@make test-check-customer1
	@echo ""
	@make test-check-customer2

test-e2e-s3: ## End-to-end test for S3 delivery (ACME Corp)
	@echo "🧪 Running end-to-end test for S3 delivery (ACME Corp)..."
	@echo ""
	@# Generate unique test ID
	@TEST_ID=$$(uuidgen); \
	TIMESTAMP=$$(date +%s); \
	echo "Test ID: $$TEST_ID"; \
	echo ""; \
	echo "📝 Creating structured log with unique trace ID..."; \
	python3 test_container/generate_e2e_s3_log.py "$$TEST_ID" | gzip > /tmp/test-e2e-$$TIMESTAMP.json.gz; \
	echo ""; \
	echo "⬆️  Uploading to central bucket..."; \
	SOURCE_BUCKET=$$(cd terraform/local && terraform output -raw central_source_bucket 2>/dev/null); \
	aws --endpoint-url=http://localhost:4566 s3 cp /tmp/test-e2e-$$TIMESTAMP.json.gz \
		s3://$$SOURCE_BUCKET/test-cluster/acme-corp/payment-service/pod-e2e/test-e2e-$$TIMESTAMP.json.gz; \
	rm -f /tmp/test-e2e-$$TIMESTAMP.json.gz; \
	echo ""; \
	echo "⏳ Waiting 15 seconds for processing (scan interval is 10s)..."; \
	sleep 15; \
	echo ""; \
	echo "🔍 Verifying S3 delivery..."; \
	CUSTOMER_BUCKET=$$(cd terraform/local && terraform output -raw customer1_bucket 2>/dev/null); \
	DELIVERED_FILE=$$(AWS_ACCESS_KEY_ID=222222222222 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 \
		s3 ls s3://$$CUSTOMER_BUCKET/logs/acme-corp/payment-service/pod-e2e/ --recursive | grep test-e2e | tail -1 | awk '{print $$4}'); \
	if [ -z "$$DELIVERED_FILE" ]; then \
		echo "❌ FAILED: No file delivered to S3"; \
		exit 1; \
	fi; \
	echo "Found delivered file: $$DELIVERED_FILE"; \
	echo "Downloading and checking content..."; \
	AWS_ACCESS_KEY_ID=222222222222 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 \
		s3 cp s3://$$CUSTOMER_BUCKET/$$DELIVERED_FILE /tmp/delivered-$$TIMESTAMP.json.gz; \
	zcat /tmp/delivered-$$TIMESTAMP.json.gz | grep -q "$$TEST_ID"; \
	if [ $$? -eq 0 ]; then \
		echo "✅ S3 delivery verified - UUID found in delivered file"; \
	else \
		echo "❌ FAILED: UUID not found in S3 file"; \
		rm -f /tmp/delivered-$$TIMESTAMP.json.gz; \
		exit 1; \
	fi; \
	rm -f /tmp/delivered-$$TIMESTAMP.json.gz; \
	echo ""; \
	echo "✅ End-to-end test completed successfully!"

test-e2e-cw: ## End-to-end test for CloudWatch delivery (Globex Industries)
	@echo "🧪 Running end-to-end test for CloudWatch delivery (Globex Industries)..."
	@echo ""
	@# Generate unique test ID
	@TEST_ID=$$(uuidgen); \
	TIMESTAMP=$$(date +%s); \
	echo "Test ID: $$TEST_ID"; \
	echo ""; \
	echo "📝 Creating structured log with unique trace ID..."; \
	python3 test_container/generate_e2e_log.py "$$TEST_ID" | gzip > /tmp/test-e2e-cw-$$TIMESTAMP.json.gz; \
	echo ""; \
	echo "⬆️  Uploading to central bucket..."; \
	SOURCE_BUCKET=$$(cd terraform/local && terraform output -raw central_source_bucket 2>/dev/null); \
	aws --endpoint-url=http://localhost:4566 s3 cp /tmp/test-e2e-cw-$$TIMESTAMP.json.gz \
		s3://$$SOURCE_BUCKET/test-cluster/globex-industries/platform-api/pod-e2e-cw/test-e2e-cw-$$TIMESTAMP.json.gz; \
	rm -f /tmp/test-e2e-cw-$$TIMESTAMP.json.gz; \
	echo ""; \
	echo "⏳ Waiting 15 seconds for processing (scan interval is 10s)..."; \
	sleep 15; \
	echo ""; \
	echo "🔍 Verifying CloudWatch Logs delivery..."; \
	LOG_GROUP=$$(cd terraform/local && terraform output -raw customer2_log_group 2>/dev/null); \
	echo "Querying log group: $$LOG_GROUP"; \
	echo "Looking for log stream: pod-e2e-cw"; \
	CW_EVENTS=$$(AWS_ACCESS_KEY_ID=333333333333 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 \
		logs get-log-events \
		--log-group-name "$$LOG_GROUP" \
		--log-stream-name "pod-e2e-cw" \
		--limit 10 \
		--output json 2>/dev/null || echo '{"events":[]}'); \
	echo "CloudWatch events:"; \
	echo "$$CW_EVENTS" | jq -r '.events[].message' 2>/dev/null || echo "No events or jq not available"; \
	if echo "$$CW_EVENTS" | grep -q "$$TEST_ID"; then \
		echo ""; \
		echo "✅ CloudWatch delivery verified - UUID found in logs"; \
		echo "✅ End-to-end CloudWatch test completed successfully!"; \
	else \
		echo ""; \
		echo "❌ FAILED: UUID not found in CloudWatch logs"; \
		echo ""; \
		echo "Available log streams:"; \
		AWS_ACCESS_KEY_ID=333333333333 AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566 \
			logs describe-log-streams --log-group-name "$$LOG_GROUP" --order-by LastEventTime --descending --max-items 5 2>/dev/null || echo "Could not list log streams"; \
		exit 1; \
	fi

test-e2e: test-e2e-s3 test-e2e-cw ## Run end-to-end tests for both delivery types
	@echo ""
	@echo "🎉 All end-to-end tests passed!"

test-e2e-go: ## Run Go integration tests (requires Go container running)
	@echo "🧪 Running Go integration tests..."
	@echo ""
	@echo "Prerequisites:"
	@echo "  1. LocalStack running (make start)"
	@echo "  2. Infrastructure deployed (make deploy-go)"
	@echo "  3. Go container running in scan mode (make run-go-scan)"
	@echo ""
	@read -p "Press Enter to continue if prerequisites are met (Ctrl+C to cancel)..."
	@echo ""
	cd container && go test -count=1 -tags=integration ./integration -v -timeout 5m

test-e2e-go-quick: ## Run Go integration tests without prerequisite check
	@echo "🧪 Running Go integration tests..."
	cd container && go test -count=1 -tags=integration ./integration -v -timeout 5m

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

run-go-scan: ## Run Go container in scan mode (requires deploy-go first)
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
		log-processor-go:local \
		--mode scan

.DEFAULT_GOAL := help
