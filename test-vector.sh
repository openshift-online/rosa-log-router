#!/bin/bash

# Test script for Vector with local S3 bucket configuration
# This script gets stack outputs and configures Vector for testing

set -e

# Configuration
STACK_NAME="multi-tenant-logging-development"
CONFIG_FILE="vector-local-test.yaml"
export AWS_PROFILE=scuppett-dev
export AWS_DEFAULT_REGION=us-east-2

echo "Getting stack outputs for Vector testing..."

# Get stack outputs
S3_BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CentralLoggingBucketName`].OutputValue' \
    --output text)

S3_WRITER_ROLE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "multi-tenant-logging-development-CoreInfrastructureStack-1R0TR6CYSW2CT" \
    --query 'Stacks[0].Outputs[?OutputKey==`CentralS3WriterRoleArn`].OutputValue' \
    --output text)

AWS_REGION=us-east-2

echo "Stack Configuration:"
echo "  S3 Bucket: $S3_BUCKET_NAME"
echo "  S3 Writer Role: $S3_WRITER_ROLE_ARN"
echo "  AWS Region: $AWS_REGION"

# Set environment variables for Vector
export S3_BUCKET_NAME
export S3_WRITER_ROLE_ARN
export AWS_REGION

echo ""
echo "Environment variables set:"
echo "  S3_BUCKET_NAME=$S3_BUCKET_NAME"
echo "  S3_WRITER_ROLE_ARN=$S3_WRITER_ROLE_ARN"  
echo "  AWS_REGION=$AWS_REGION"

echo ""
echo "To test Vector with fake log generator:"
echo "1. Basic test with fake logs:"
echo "   cd test_container && python3 fake_log_generator.py --total-batches 10 | vector --config ../$CONFIG_FILE"
echo ""
echo "2. High-volume performance test:"
echo "   cd test_container && python3 fake_log_generator.py --min-batch-size 20 --max-batch-size 50 --min-sleep 0.1 --max-sleep 1.0 --total-batches 50 | vector --config ../$CONFIG_FILE"
echo ""
echo "3. Multi-tenant test (different customer):"
echo "   cd test_container && python3 fake_log_generator.py --customer-id acme-corp --cluster-id prod-cluster-1 --application payment-service --total-batches 20 | vector --config ../$CONFIG_FILE"
echo ""
echo "4. Container-based test:"
echo "   cd test_container && podman build -f Containerfile -t fake-log-generator ."
echo "   podman run --rm fake-log-generator --total-batches 10 | vector --config $CONFIG_FILE"
echo ""
echo "5. Simple single message test:"
echo "   echo '{\"message\": \"Test log message\", \"level\": \"INFO\"}' | vector --config $CONFIG_FILE"