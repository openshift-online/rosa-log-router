#!/usr/bin/env python3
"""
Mock test for SQS message handling that doesn't require AWS credentials
"""

import sys
import os
import json
from unittest.mock import patch, MagicMock
import tempfile

# Add the container directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'container'))

# Import our processor with mocked AWS dependencies
with patch('boto3.client'), patch('boto3.resource'):
    from log_processor import (
        process_sqs_record, 
        TenantNotFoundError, 
        InvalidS3NotificationError,
        NonRecoverableError
    )

def test_tenant_not_found():
    """Test that TenantNotFoundError is handled as non-recoverable"""
    print("Testing TenantNotFoundError handling...")
    
    # Mock DynamoDB to raise TenantNotFoundError
    with patch('log_processor.get_tenant_configuration') as mock_get_tenant:
        mock_get_tenant.side_effect = TenantNotFoundError("No configuration found for tenant: test-tenant")
        
        # Create a valid SQS record
        sqs_record = {
            'body': json.dumps({
                "Message": json.dumps({
                    "Records": [{
                        "s3": {
                            "bucket": {"name": "test-bucket"},
                            "object": {"key": "cluster/tenant/app/pod/file.json.gz"}
                        }
                    }]
                })
            }),
            'messageId': 'test-message-id'
        }
        
        # Process should not raise an exception
        try:
            process_sqs_record(sqs_record)
            print("✅ TenantNotFoundError handled gracefully (no exception raised)")
            return True
        except Exception as e:
            print(f"❌ TenantNotFoundError not handled properly: {e}")
            return False

def test_invalid_message_format():
    """Test that invalid JSON format is handled as non-recoverable"""
    print("\nTesting invalid message format handling...")
    
    sqs_record = {
        'body': 'invalid json content',
        'messageId': 'test-message-id'
    }
    
    try:
        process_sqs_record(sqs_record)
        print("✅ Invalid message format handled gracefully (no exception raised)")
        return True
    except Exception as e:
        print(f"❌ Invalid message format not handled properly: {e}")
        return False

def test_invalid_object_key():
    """Test that invalid object key format is handled as non-recoverable"""
    print("\nTesting invalid object key handling...")
    
    sqs_record = {
        'body': json.dumps({
            "Message": json.dumps({
                "Records": [{
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "invalid-key.json.gz"}  # Not enough path segments
                    }
                }]
            })
        }),
        'messageId': 'test-message-id'
    }
    
    try:
        process_sqs_record(sqs_record)
        print("✅ Invalid object key handled gracefully (no exception raised)")
        return True
    except Exception as e:
        print(f"❌ Invalid object key not handled properly: {e}")
        return False

def test_recoverable_error():
    """Test that recoverable errors are still raised"""
    print("\nTesting recoverable error handling...")
    
    # Mock to raise a generic exception (should be treated as recoverable)
    with patch('log_processor.get_tenant_configuration') as mock_get_tenant:
        mock_get_tenant.side_effect = Exception("Network error")
        
        sqs_record = {
            'body': json.dumps({
                "Message": json.dumps({
                    "Records": [{
                        "s3": {
                            "bucket": {"name": "test-bucket"},
                            "object": {"key": "cluster/tenant/app/pod/file.json.gz"}
                        }
                    }]
                })
            }),
            'messageId': 'test-message-id'
        }
        
        try:
            process_sqs_record(sqs_record)
            print("❌ Recoverable error should have been raised")
            return False
        except Exception as e:
            if "Network error" in str(e):
                print("✅ Recoverable error properly raised for retry")
                return True
            else:
                print(f"❌ Wrong exception raised: {e}")
                return False

def main():
    """Run all mock tests"""
    print("Mock SQS Message Handling Tests")
    print("===============================")
    
    tests = [
        test_tenant_not_found,
        test_invalid_message_format,
        test_invalid_object_key,
        test_recoverable_error
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n\nTest Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())