#!/bin/bash
set -e

# Validates Vector log flow by checking customer S3 buckets in LocalStack
# This script verifies that Vector successfully collected logs from pods
# and routed them through the Lambda processor to customer accounts

echo "🔍 Validating Vector log flow through LocalStack..."
echo ""

# Get terraform outputs
echo "Fetching terraform outputs..."
CUSTOMER1_BUCKET=$(cd terraform/local && terraform output -raw customer1_bucket 2>/dev/null)
CUSTOMER2_BUCKET=$(cd terraform/local && terraform output -raw customer2_bucket 2>/dev/null)

if [ -z "$CUSTOMER1_BUCKET" ] || [ -z "$CUSTOMER2_BUCKET" ]; then
  echo "❌ Failed to get terraform outputs. Is infrastructure deployed?"
  echo "Run: make deploy"
  exit 1
fi

echo "Customer 1 bucket: $CUSTOMER1_BUCKET"
echo "Customer 2 bucket: $CUSTOMER2_BUCKET"
echo ""

# Check Customer 1 (acme-corp) logs
echo "Checking Customer 1 (acme-corp) bucket for payment-service logs..."
ACME_LOGS=$(AWS_ACCESS_KEY_ID=222222222222 AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url=http://localhost:4566 \
  s3 ls s3://$CUSTOMER1_BUCKET/logs/acme-corp/payment-service/ --recursive 2>/dev/null | grep -c "\.json\.gz" || echo "0")

if [ "$ACME_LOGS" -gt 0 ]; then
  echo "✅ Found $ACME_LOGS log file(s) for acme-corp/payment-service"

  # Show sample file path
  SAMPLE_FILE=$(AWS_ACCESS_KEY_ID=222222222222 AWS_SECRET_ACCESS_KEY=test \
    aws --endpoint-url=http://localhost:4566 \
    s3 ls s3://$CUSTOMER1_BUCKET/logs/acme-corp/payment-service/ --recursive 2>/dev/null | grep "\.json\.gz" | head -1 | awk '{print $4}')
  if [ -n "$SAMPLE_FILE" ]; then
    echo "   Sample: s3://$CUSTOMER1_BUCKET/$SAMPLE_FILE"
  fi
else
  echo "❌ No logs found for acme-corp/payment-service"
  echo ""
  echo "Debug: Checking what's in the customer bucket..."
  AWS_ACCESS_KEY_ID=222222222222 AWS_SECRET_ACCESS_KEY=test \
    aws --endpoint-url=http://localhost:4566 \
    s3 ls s3://$CUSTOMER1_BUCKET/ --recursive 2>/dev/null | head -10 || echo "Bucket is empty or inaccessible"
  exit 1
fi

echo ""

# Check Customer 2 (globex-industries) logs
echo "Checking Customer 2 (globex-industries) bucket for platform-api logs..."
GLOBEX_LOGS=$(AWS_ACCESS_KEY_ID=333333333333 AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url=http://localhost:4566 \
  s3 ls s3://$CUSTOMER2_BUCKET/platform-logs/globex-industries/platform-api/ --recursive 2>/dev/null | grep -c "\.json\.gz" || echo "0")

if [ "$GLOBEX_LOGS" -gt 0 ]; then
  echo "✅ Found $GLOBEX_LOGS log file(s) for globex-industries/platform-api"

  # Show sample file path
  SAMPLE_FILE=$(AWS_ACCESS_KEY_ID=333333333333 AWS_SECRET_ACCESS_KEY=test \
    aws --endpoint-url=http://localhost:4566 \
    s3 ls s3://$CUSTOMER2_BUCKET/platform-logs/globex-industries/platform-api/ --recursive 2>/dev/null | grep "\.json\.gz" | head -1 | awk '{print $4}')
  if [ -n "$SAMPLE_FILE" ]; then
    echo "   Sample: s3://$CUSTOMER2_BUCKET/$SAMPLE_FILE"
  fi
else
  echo "❌ No logs found for globex-industries/platform-api"
  echo ""
  echo "Debug: Checking what's in the customer bucket..."
  AWS_ACCESS_KEY_ID=333333333333 AWS_SECRET_ACCESS_KEY=test \
    aws --endpoint-url=http://localhost:4566 \
    s3 ls s3://$CUSTOMER2_BUCKET/ --recursive 2>/dev/null | head -10 || echo "Bucket is empty or inaccessible"
  exit 1
fi

echo ""
echo "============================================================"
echo "✅ Vector flow validation PASSED!"
echo "============================================================"
echo ""
echo "Summary:"
echo "  • Vector collected logs from pods in customer namespaces"
echo "  • Logs were written to LocalStack S3 central bucket"
echo "  • S3 triggered SNS → SQS → Lambda pipeline"
echo "  • Lambda processed and delivered logs to customer buckets"
echo "  • Customer 1: $ACME_LOGS file(s) delivered"
echo "  • Customer 2: $GLOBEX_LOGS file(s) delivered"
echo ""
