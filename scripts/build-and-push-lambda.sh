#!/bin/bash
# Push Lambda container image to LocalStack ECR
# Usage: ./scripts/build-and-push-lambda.sh [tag]
# Note: Image must already be built locally as log-processor:TAG

set -e

# Configuration
LOCALSTACK_ENDPOINT="http://localhost:4566"
CENTRAL_ACCOUNT_ID="111111111111"
REGION="us-east-1"
REPO_NAME="multi-tenant-logging-int-log-processor"
TAG="${1:-latest}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Detect if docker is really Docker or Podman
# Podman changes its --version output based on how it's called, so check docker info instead
IS_PODMAN=false
if docker info 2>&1 | grep -qi podman; then
  IS_PODMAN=true
  echo -e "${BLUE}Detected Podman (via docker alias/symlink)${NC}"
else
  echo -e "${BLUE}Detected Docker${NC}"
fi

# Verify local image exists
echo -e "${BLUE}Checking for local image log-processor:${TAG}...${NC}"
if ! docker image inspect log-processor:${TAG} &> /dev/null; then
  echo "Error: Image log-processor:${TAG} not found locally."
  echo "Build it first with: make build-lambda-image"
  exit 1
fi
echo -e "${GREEN}✓ Local image found${NC}"

# Get ECR repository URL from LocalStack
echo -e "${BLUE}Getting ECR repository URL...${NC}"
REPO_URI=$(AWS_ACCESS_KEY_ID=${CENTRAL_ACCOUNT_ID} \
  AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url=${LOCALSTACK_ENDPOINT} \
  ecr describe-repositories \
  --repository-names ${REPO_NAME} \
  --region ${REGION} \
  --query 'repositories[0].repositoryUri' \
  --output text 2>&1)

# Check if we got an error
if [ $? -ne 0 ] || [ -z "$REPO_URI" ] || [[ "$REPO_URI" == *"Error"* ]]; then
  echo "Error getting repository URI. Response: $REPO_URI"
  echo "Trying to list all repositories..."
  AWS_ACCESS_KEY_ID=${CENTRAL_ACCOUNT_ID} \
    AWS_SECRET_ACCESS_KEY=test \
    aws --endpoint-url=${LOCALSTACK_ENDPOINT} \
    ecr describe-repositories \
    --region ${REGION}
  exit 1
fi

echo -e "${GREEN}✓ Repository URL: ${REPO_URI}${NC}"

# Tag the image for ECR
echo -e "${BLUE}Tagging image for ECR...${NC}"
docker tag log-processor:${TAG} ${REPO_URI}:${TAG}

# LocalStack doesn't require authentication for ECR in local mode
echo -e "${BLUE}Pushing image to LocalStack ECR...${NC}"
if [ "$IS_PODMAN" = true ]; then
  # Podman-specific flags for LocalStack compatibility
  docker push ${REPO_URI}:${TAG} \
    --format docker \
    --tls-verify=false \
    --remove-signatures
else
  # Standard Docker push
  docker push ${REPO_URI}:${TAG}
fi

echo -e "${GREEN}✓ Image pushed successfully${NC}"
echo ""
echo "Image URI: ${REPO_URI}:${TAG}"
echo ""
echo "To deploy Lambda with this image:"
echo "  cd terraform/local"
echo "  terraform apply -var=\"use_container_image=true\" -var=\"lambda_image_tag=${TAG}\""
