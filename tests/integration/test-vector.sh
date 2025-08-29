#!/bin/bash

# test-vector.sh - Setup environment for local Vector integration testing
#
# This script sets up the necessary environment variables for testing Vector's
# integration with AWS S3. It sources the project's .env file and extracts
# AWS credentials from the configured profile.
#
# Usage:
#   cd tests/integration
#   chmod +x test-vector.sh
#   source ./test-vector.sh
#   vector --config ../../vector-local-test.yaml
#
# Requirements:
#   - .env file configured with AWS_PROFILE, S3_WRITER_ROLE_ARN, S3_BUCKET_NAME
#   - AWS CLI configured with the specified profile
#   - vector binary in PATH

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Setting up environment for Vector integration testing...${NC}"

# Source the project .env file
ENV_FILE="../../.env"
if [[ -f "$ENV_FILE" ]]; then
    echo -e "${GREEN}✓${NC} Found .env file at $ENV_FILE"
    source "$ENV_FILE"
else
    echo -e "${RED}✗${NC} .env file not found at $ENV_FILE"
    echo "Please create .env file from .env.sample and configure your AWS settings"
    return 1
fi

# Validate required environment variables
if [[ -z "$AWS_PROFILE" ]]; then
    echo -e "${RED}✗${NC} AWS_PROFILE not set in .env file"
    return 1
fi

if [[ -z "$S3_WRITER_ROLE_ARN" ]]; then
    echo -e "${RED}✗${NC} S3_WRITER_ROLE_ARN not set in .env file"
    return 1
fi

if [[ -z "$S3_BUCKET_NAME" ]]; then
    echo -e "${RED}✗${NC} S3_BUCKET_NAME not set in .env file"
    return 1
fi

if [[ -z "$AWS_REGION" ]]; then
    echo -e "${RED}✗${NC} AWS_REGION not set in .env file"
    return 1
fi

echo -e "${GREEN}✓${NC} Required variables found in .env:"
echo "  AWS_PROFILE: $AWS_PROFILE"
echo "  AWS_REGION: $AWS_REGION"
echo "  S3_WRITER_ROLE_ARN: $S3_WRITER_ROLE_ARN"
echo "  S3_BUCKET_NAME: $S3_BUCKET_NAME"

# Extract AWS credentials from the configured profile
echo -e "${YELLOW}Extracting AWS credentials from profile '$AWS_PROFILE'...${NC}"

if ! aws configure list --profile "$AWS_PROFILE" >/dev/null 2>&1; then
    echo -e "${RED}✗${NC} AWS profile '$AWS_PROFILE' not found"
    echo "Please configure the profile with: aws configure --profile $AWS_PROFILE"
    return 1
fi

# Export base AWS credentials for Vector
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile "$AWS_PROFILE")
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile "$AWS_PROFILE")

if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" ]]; then
    echo -e "${RED}✗${NC} Failed to extract credentials from profile '$AWS_PROFILE'"
    echo "Please ensure the profile has valid aws_access_key_id and aws_secret_access_key"
    return 1
fi

# Export Vector-specific environment variables
export S3_WRITER_ROLE_ARN="$S3_WRITER_ROLE_ARN"
export S3_BUCKET_NAME="$S3_BUCKET_NAME"
export AWS_REGION="$AWS_REGION"

echo -e "${GREEN}✓${NC} AWS credentials extracted successfully"
echo -e "${GREEN}✓${NC} Environment configured for Vector testing"
echo
echo -e "${YELLOW}Environment variables set:${NC}"
echo "  AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:0:8}..."
echo "  AWS_SECRET_ACCESS_KEY: [hidden]"
echo "  AWS_REGION: $AWS_REGION"
echo "  S3_WRITER_ROLE_ARN: $S3_WRITER_ROLE_ARN"
echo "  S3_BUCKET_NAME: $S3_BUCKET_NAME"
echo
echo -e "${GREEN}Ready to run Vector integration tests!${NC}"
echo
echo "Example usage:"
echo "  # Run with fake log generator"
echo "  python3 ../../test_container/fake_log_generator.py --total-batches 10 | vector --config ../vector-local-test.yaml"
echo
echo "  # High-volume test"
echo "  python3 ../../test_container/fake_log_generator.py --min-batch-size 50 --max-batch-size 100 --total-batches 100 | vector --config ../vector-local-test.yaml"