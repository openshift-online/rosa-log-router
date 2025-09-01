"""
Test configuration and fixtures for unit tests
"""
import pytest
import os
import sys
import boto3
from moto import mock_aws

# Add API source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../api/src'))


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


# API-specific fixtures below

@pytest.fixture(scope="function")
def dynamodb_table(aws_credentials):
    """Create a mocked DynamoDB table for testing with composite key schema"""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        
        # Create the table with composite key (tenant_id + type)
        table = dynamodb.create_table(
            TableName="test-tenant-configs",
            KeySchema=[
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "type", "KeyType": "RANGE"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "tenant_id", "AttributeType": "S"},
                {"AttributeName": "type", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST"
        )
        
        yield table


@pytest.fixture(scope="function")
def delivery_config_service(dynamodb_table):
    """Create a TenantDeliveryConfigService instance with mocked DynamoDB"""
    try:
        from src.services.dynamo import TenantDeliveryConfigService
        return TenantDeliveryConfigService(table_name="test-tenant-configs", region="us-east-1")
    except ImportError:
        # If API modules aren't available, skip
        pytest.skip("API modules not available")


@pytest.fixture
def sample_cloudwatch_config():
    """Sample CloudWatch delivery config for testing"""
    return {
        "tenant_id": "test-tenant",
        "type": "cloudwatch",
        "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
        "log_group_name": "/aws/logs/test-tenant",
        "target_region": "us-east-1",
        "enabled": True,
        "desired_logs": ["app1", "app2"]
    }


@pytest.fixture
def sample_s3_config():
    """Sample S3 delivery config for testing"""
    return {
        "tenant_id": "test-tenant",
        "type": "s3",
        "bucket_name": "test-bucket",
        "bucket_prefix": "ROSA/cluster-logs/",
        "target_region": "us-east-1",
        "enabled": True
    }


@pytest.fixture
def multiple_delivery_configs():
    """Multiple delivery configurations for testing"""
    return [
        {
            "tenant_id": "tenant-1",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/Role1",
            "log_group_name": "/aws/logs/tenant-1",
            "target_region": "us-east-1",
            "enabled": True
        },
        {
            "tenant_id": "tenant-1",
            "type": "s3",
            "bucket_name": "tenant-1-logs",
            "bucket_prefix": "logs/",
            "target_region": "us-east-1",
            "enabled": True
        },
        {
            "tenant_id": "tenant-2",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/Role2",
            "log_group_name": "/aws/logs/tenant-2",
            "target_region": "us-west-2",
            "enabled": False,
            "desired_logs": ["payment-service"]
        },
        {
            "tenant_id": "tenant-3",
            "type": "s3",
            "bucket_name": "tenant-3-archive",
            "target_region": "eu-west-1",
            "enabled": True,
            "desired_logs": ["user-service", "auth-service"]
        }
    ]


@pytest.fixture
def populated_delivery_configs(delivery_config_service, multiple_delivery_configs):
    """A delivery config service with pre-populated test data"""
    for config in multiple_delivery_configs:
        delivery_config_service.create_tenant_config(config)
    return delivery_config_service