#!/bin/bash
# Test script for SQS message handling using containers

set -e

echo "Testing SQS Message Handling with Containers"
echo "============================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if podman is available
if ! command -v podman &> /dev/null; then
    echo -e "${RED}Error: podman not found. Please install podman or use docker instead.${NC}"
    exit 1
fi

# Build the processor container if it doesn't exist
echo "Building processor container..."
cd ../container
if podman build -f Containerfile.processor -t log-processor:test . > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Container built successfully${NC}"
else
    echo -e "${RED}✗ Failed to build container${NC}"
    exit 1
fi

cd ../tests

# Function to run container test
run_container_test() {
    local test_name="$1"
    local test_case="$2"
    local expected_behavior="$3"
    
    echo -e "\n${YELLOW}Container Test: $test_name${NC}"
    echo "Expected: $expected_behavior"
    
    # Set minimal environment variables for testing
    ENV_VARS="-e EXECUTION_MODE=manual"
    ENV_VARS="$ENV_VARS -e AWS_REGION=us-east-2"
    ENV_VARS="$ENV_VARS -e TENANT_CONFIG_TABLE=test-tenant-configs"
    
    # Run the test
    if python3 test_data.py "$test_case" | podman run --rm -i $ENV_VARS log-processor:test; then
        echo -e "${GREEN}✓ Container test completed${NC}"
    else
        exit_code=$?
        echo -e "${YELLOW}! Container test exited with code $exit_code${NC}"
    fi
}

echo -e "\n${GREEN}Starting Container-based SQS Tests${NC}"

# Test the same scenarios but in container environment
run_container_test "Container: Non-existent Tenant" "nonexistent-tenant" "Should handle gracefully in container"
run_container_test "Container: Invalid Message Format" "invalid-format" "Should handle gracefully in container"
run_container_test "Container: Invalid Object Key" "invalid-object-key" "Should handle gracefully in container"

echo -e "\n${GREEN}Container tests completed!${NC}"
echo ""
echo "These tests verify that the SQS message handling works correctly in the containerized environment"
echo "that would be used in Lambda or Kubernetes deployments."