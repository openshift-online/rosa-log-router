#!/bin/bash
# Warm up Lambda container by pushing test files and verifying execution
# This addresses the LocalStack+Podman cold start race condition

set -e

# Configuration
LOCALSTACK_ENDPOINT="http://localhost:4566"
CENTRAL_ACCOUNT_ID="111111111111"
REGION="us-east-1"
WARMUP_ATTEMPTS=5

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Lambda Container Warmup Script${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Get infrastructure details from Terraform
echo -e "${BLUE}Getting infrastructure details from Terraform...${NC}"
cd "$(dirname "$0")/../terraform/local"

CENTRAL_BUCKET=$(terraform output -raw central_source_bucket 2>/dev/null)
LAMBDA_FUNCTION_NAME=$(terraform output -raw central_lambda_function 2>/dev/null)
LAMBDA_LOG_GROUP="/aws/lambda/${LAMBDA_FUNCTION_NAME}"

if [ -z "$CENTRAL_BUCKET" ] || [ -z "$LAMBDA_FUNCTION_NAME" ]; then
  echo -e "${RED}Error: Could not get infrastructure details from Terraform${NC}"
  echo "Make sure infrastructure is deployed with 'make deploy'"
  exit 1
fi

echo -e "${GREEN}✓ Central Bucket: ${CENTRAL_BUCKET}${NC}"
echo -e "${GREEN}✓ Lambda Function: ${LAMBDA_FUNCTION_NAME}${NC}"
echo ""

# Function to upload a test file
upload_test_file() {
  local attempt=$1
  local uuid=$(uuidgen | tr '[:upper:]' '[:lower:]')
  local timestamp=$(date +%s)
  local temp_log="/tmp/warmup-log-${attempt}.json"
  local temp_gz="${temp_log}.gz"

  # Create test log
  cat > "$temp_log" << LOGEOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "level": "INFO",
  "message": "Lambda warmup test ${attempt}/${WARMUP_ATTEMPTS}",
  "warmup_uuid": "$uuid",
  "attempt": $attempt,
  "pod": "warmup-test-pod"
}
LOGEOF

  # Compress it
  gzip -f "$temp_log"

  # Upload to central bucket
  echo -e "${BLUE}Attempt ${attempt}/${WARMUP_ATTEMPTS}: Uploading test file (UUID: $uuid)${NC}"

  AWS_ACCESS_KEY_ID=${CENTRAL_ACCOUNT_ID} \
    AWS_SECRET_ACCESS_KEY=test \
    aws --endpoint-url=${LOCALSTACK_ENDPOINT} \
    s3 cp "$temp_gz" \
    "s3://${CENTRAL_BUCKET}/test-cluster/acme-corp/payment-service/warmup-test-pod/warmup-${attempt}-${timestamp}.json.gz" \
    --region ${REGION} >/dev/null 2>&1

  echo "$uuid"
}

# Function to check Lambda execution status
check_lambda_execution() {
  local uuid=$1
  local attempt=$2
  local max_wait=30
  local waited=0

  echo -e "${YELLOW}  Waiting for Lambda execution (max ${max_wait}s)...${NC}"

  while [ $waited -lt $max_wait ]; do
    # Check if customer bucket has the file with our UUID
    if AWS_ACCESS_KEY_ID=222222222222 \
       AWS_SECRET_ACCESS_KEY=test \
       aws --endpoint-url=${LOCALSTACK_ENDPOINT} \
       s3 ls s3://acme-corp-logs/logs/acme-corp/payment-service/warmup-test-pod/ \
       --region ${REGION} 2>/dev/null | grep -q "warmup-${attempt}"; then

      echo -e "${GREEN}✓ File delivered to customer bucket${NC}"

      # Verify UUID is in the file
      sleep 2  # Give S3 a moment to ensure file is fully written

      # Get the actual filename (most recent one matching this attempt)
      local filename=$(AWS_ACCESS_KEY_ID=222222222222 \
         AWS_SECRET_ACCESS_KEY=test \
         aws --endpoint-url=${LOCALSTACK_ENDPOINT} \
         s3 ls s3://acme-corp-logs/logs/acme-corp/payment-service/warmup-test-pod/ \
         --region ${REGION} 2>/dev/null | \
         grep "warmup-${attempt}-" | tail -1 | awk '{print $4}')

      if [ -z "$filename" ]; then
        echo -e "${YELLOW}⚠ File list succeeded but no filename found${NC}"
        return 1
      fi

      # Download and verify UUID
      if AWS_ACCESS_KEY_ID=222222222222 \
         AWS_SECRET_ACCESS_KEY=test \
         aws --endpoint-url=${LOCALSTACK_ENDPOINT} \
         s3 cp "s3://acme-corp-logs/logs/acme-corp/payment-service/warmup-test-pod/${filename}" - \
         --region ${REGION} 2>/dev/null | gunzip 2>/dev/null | grep -qF "$uuid"; then
        echo -e "${GREEN}✓ UUID verified in delivered file${NC}"
        return 0
      else
        echo -e "${YELLOW}⚠ File delivered but UUID not found${NC}"
        return 1
      fi
    fi

    sleep 2
    waited=$((waited + 2))
    echo -e "${YELLOW}  Still waiting... (${waited}s)${NC}"
  done

  echo -e "${RED}✗ Timeout waiting for Lambda execution${NC}"
  return 1
}

# Function to check Lambda logs for errors
check_lambda_logs() {
  echo -e "${BLUE}Checking Lambda logs for errors...${NC}"

  # Get recent log events (last 5 minutes)
  local start_time=$(($(date +%s) - 300))000

  local errors=$(AWS_ACCESS_KEY_ID=${CENTRAL_ACCOUNT_ID} \
    AWS_SECRET_ACCESS_KEY=test \
    aws --endpoint-url=${LOCALSTACK_ENDPOINT} \
    logs filter-log-events \
    --log-group-name "${LAMBDA_LOG_GROUP}" \
    --start-time ${start_time} \
    --filter-pattern "ERROR" \
    --region ${REGION} \
    --query 'events[*].message' \
    --output text 2>/dev/null || echo "")

  if [ -n "$errors" ]; then
    echo -e "${YELLOW}⚠ Found errors in Lambda logs:${NC}"
    echo "$errors" | head -10
    echo ""
  fi

  # Check for ContainerException specifically
  local container_errors=$(AWS_ACCESS_KEY_ID=${CENTRAL_ACCOUNT_ID} \
    AWS_SECRET_ACCESS_KEY=test \
    aws --endpoint-url=${LOCALSTACK_ENDPOINT} \
    logs filter-log-events \
    --log-group-name "${LAMBDA_LOG_GROUP}" \
    --start-time ${start_time} \
    --filter-pattern "ContainerException" \
    --region ${REGION} \
    --query 'events[*].message' \
    --output text 2>/dev/null || echo "")

  if [ -n "$container_errors" ]; then
    echo -e "${YELLOW}⚠ Found ContainerException (expected on first attempt with Podman):${NC}"
    echo "$container_errors" | head -5
    echo ""
  fi
}

# Main warmup loop
echo -e "${BLUE}Starting Lambda container warmup...${NC}"
echo ""

success_count=0
fail_count=0

for i in $(seq 1 $WARMUP_ATTEMPTS); do
  uuid=$(upload_test_file $i)

  if check_lambda_execution "$uuid" $i; then
    success_count=$((success_count + 1))
    echo -e "${GREEN}✓ Attempt ${i}/${WARMUP_ATTEMPTS} succeeded${NC}"
    echo ""
    echo -e "${GREEN}✅ Lambda container warmed up successfully!${NC}"
    echo -e "${GREEN}Container is ready for e2e tests${NC}"
    exit 0
  else
    fail_count=$((fail_count + 1))
    echo -e "${RED}✗ Attempt ${i}/${WARMUP_ATTEMPTS} failed${NC}"
  fi

  echo ""

  # Small delay between attempts
  if [ $i -lt $WARMUP_ATTEMPTS ]; then
    sleep 3
  fi
done

echo -e "${BLUE}Warmup Summary${NC}"
echo -e "${BLUE}==============${NC}"
echo -e "Successful: ${GREEN}${success_count}/${WARMUP_ATTEMPTS}${NC}"
echo -e "Failed: ${RED}${fail_count}/${WARMUP_ATTEMPTS}${NC}"
echo ""

# Check logs for any errors
check_lambda_logs

# Determine success
if [ $success_count -eq $WARMUP_ATTEMPTS ]; then
  echo -e "${GREEN}✅ Lambda container fully warmed up and ready!${NC}"
  exit 0
elif [ $success_count -gt 0 ]; then
  echo -e "${YELLOW}⚠ Lambda container warmed up but some attempts failed${NC}"
  echo -e "${YELLOW}This is expected with LocalStack+Podman on first cold start${NC}"
  echo -e "${GREEN}Container should be ready for e2e tests now${NC}"
  exit 0
else
  echo -e "${RED}❌ Lambda warmup failed completely${NC}"
  echo -e "${RED}Check Lambda configuration and logs${NC}"
  exit 1
fi
