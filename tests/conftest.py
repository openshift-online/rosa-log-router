"""
Test configuration and fixtures for unit tests
"""
import pytest
import os
from moto import mock_aws


@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'


@pytest.fixture
def mock_aws_services(aws_credentials):
    """Mock all AWS services."""
    with mock_aws():
        yield


@pytest.fixture
def environment_variables():
    """Set up test environment variables."""
    test_env = {
        'TENANT_CONFIG_TABLE': 'test-tenant-configs',
        'CENTRAL_LOG_DISTRIBUTION_ROLE_ARN': 'arn:aws:iam::123456789012:role/CentralRole',
        'AWS_REGION': 'us-east-1',
        'MAX_BATCH_SIZE': '1000',
        'RETRY_ATTEMPTS': '3',
        'SQS_QUEUE_URL': 'https://sqs.us-east-1.amazonaws.com/123456789012/test-queue'
    }
    
    # Store original values
    original_env = {}
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    yield test_env
    
    # Restore original values
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value