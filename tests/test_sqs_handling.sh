#!/bin/bash
# Test script for SQS message handling scenarios

set -e

echo "Testing SQS Message Handling Scenarios"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Source environment variables if .env exists
if [ -f "../.env" ]; then
    echo "Loading environment variables from .env..."
    source ../.env
fi

# Check if log processor is available
if [ ! -f "../container/log_processor.py" ]; then
    echo -e "${RED}Error: log_processor.py not found${NC}"
    exit 1
fi

# Function to run a test case
run_test() {
    local test_name="$1"
    local test_case="$2"
    local expected_behavior="$3"
    
    echo -e "\n${YELLOW}Test: $test_name${NC}"
    echo "Expected: $expected_behavior"
    echo "Running: python3 test_data.py $test_case | python3 ../container/log_processor.py --mode manual"
    echo "Output:"
    
    # Run the test and capture both stdout and stderr
    if python3 test_data.py "$test_case" | python3 ../container/log_processor.py --mode manual 2>&1; then
        echo -e "${GREEN}✓ Test completed without fatal errors${NC}"
    else
        exit_code=$?
        if [ $exit_code -eq 1 ]; then
            echo -e "${RED}✗ Test failed with exit code $exit_code${NC}"
        else
            echo -e "${YELLOW}! Test exited with code $exit_code${NC}"
        fi
    fi
}

# Test cases
echo -e "\n${GREEN}Starting SQS Message Handling Tests${NC}"

# Test 1: Non-existent tenant (should be handled gracefully)
run_test "Non-existent Tenant" "nonexistent-tenant" "Should log warning and not raise exception"

# Test 2: Invalid message format (should be handled gracefully)
run_test "Invalid Message Format" "invalid-format" "Should log warning and not raise exception"

# Test 3: Invalid S3 event (should be handled gracefully)
run_test "Invalid S3 Event" "invalid-s3-event" "Should log warning and not raise exception"

# Test 4: Invalid object key format (should be handled gracefully)
run_test "Invalid Object Key" "invalid-object-key" "Should log warning and not raise exception"

echo -e "\n${GREEN}All tests completed!${NC}"
echo ""
echo "Key points to verify in the output above:"
echo "1. Non-recoverable errors should show WARNING messages with 'Message will be removed from queue'"
echo "2. No exceptions should be raised for invalid data"
echo "3. The process should exit cleanly (exit code 0) for non-recoverable errors"
echo "4. Only true infrastructure/network errors should cause retries"
echo ""
echo "In production:"
echo "- Lambda: Non-recoverable errors won't be added to batchItemFailures"
echo "- SQS polling: Non-recoverable errors will cause message deletion"