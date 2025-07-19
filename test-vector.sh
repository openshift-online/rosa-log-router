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
echo "To test Vector:"
echo "1. echo 'Test log message' | vector --config $CONFIG_FILE"
echo "2. Or run: vector --config $CONFIG_FILE < test-logs.json"

# Create test data
cat > test-logs.json << 'EOF'
{"message": "INFO Test application started successfully", "level": "INFO"}
{"message": "DEBUG Processing user request id=12345", "level": "DEBUG"}  
{"message": "WARN Database connection slow, retrying...", "level": "WARN"}
{"message": "ERROR Failed to process payment for order #67890", "level": "ERROR"}
{"message": "INFO Application shutdown complete", "level": "INFO"}
EOF

echo ""
echo "Test log data created in test-logs.json"
echo "Run: vector --config $CONFIG_FILE < test-logs.json"