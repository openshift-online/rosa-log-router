#!/usr/bin/env python3
"""
Test data generator for SQS message handling scenarios
"""

import json
import sys

# Test case 1: Valid SQS message with existing tenant
VALID_MESSAGE_EXISTING_TENANT = {
    "Message": json.dumps({
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "multi-tenant-logging-development-central-12345678"},
                    "object": {"key": "test-cluster/test-customer/payment-service/payment-pod-123/20240101-test.json.gz"}
                }
            }
        ]
    })
}

# Test case 2: Valid SQS message with non-existent tenant (should be removed from queue)
VALID_MESSAGE_NONEXISTENT_TENANT = {
    "Message": json.dumps({
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "multi-tenant-logging-development-central-12345678"},
                    "object": {"key": "test-cluster/nonexistent-tenant/payment-service/payment-pod-123/20240101-test.json.gz"}
                }
            }
        ]
    })
}

# Test case 3: Invalid SQS message format (should be removed from queue)
INVALID_MESSAGE_FORMAT = {
    "Message": "invalid json content here"
}

# Test case 4: Valid JSON but missing required S3 fields (should be removed from queue)
INVALID_S3_EVENT = {
    "Message": json.dumps({
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-bucket"}
                    # Missing object key
                }
            }
        ]
    })
}

# Test case 5: Invalid object key format (should be removed from queue)
INVALID_OBJECT_KEY = {
    "Message": json.dumps({
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "multi-tenant-logging-development-central-12345678"},
                    "object": {"key": "invalid-key-format.json.gz"}  # Not enough path segments
                }
            }
        ]
    })
}

# Test case 6: Network/AWS error simulation (should be retried)
# This would be a valid message but we'd simulate AWS SDK errors

def print_test_case(name, data):
    """Print a test case in the format expected by the processor"""
    print(f"# Test case: {name}")
    print(json.dumps(data))
    print()

def main():
    if len(sys.argv) > 1:
        test_case = sys.argv[1]
        if test_case == "existing-tenant":
            print(json.dumps(VALID_MESSAGE_EXISTING_TENANT))
        elif test_case == "nonexistent-tenant":
            print(json.dumps(VALID_MESSAGE_NONEXISTENT_TENANT))
        elif test_case == "invalid-format":
            print(json.dumps(INVALID_MESSAGE_FORMAT))
        elif test_case == "invalid-s3-event":
            print(json.dumps(INVALID_S3_EVENT))
        elif test_case == "invalid-object-key":
            print(json.dumps(INVALID_OBJECT_KEY))
        else:
            print(f"Unknown test case: {test_case}")
            sys.exit(1)
    else:
        print("Available test cases:")
        print("  existing-tenant      - Valid message for existing tenant")
        print("  nonexistent-tenant  - Valid message for non-existent tenant (should be removed)")
        print("  invalid-format       - Invalid JSON format (should be removed)")
        print("  invalid-s3-event     - Missing S3 fields (should be removed)")
        print("  invalid-object-key   - Invalid object key format (should be removed)")
        print()
        print("Usage: python3 test_data.py <test_case>")
        print("Example: python3 test_data.py nonexistent-tenant | python3 ../container/log_processor.py --mode manual")

if __name__ == "__main__":
    main()