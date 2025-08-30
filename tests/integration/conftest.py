"""
Integration test configuration and fixtures for DynamoDB Local testing
"""

import pytest
import boto3
import os
import sys
import time
import subprocess
import socket
from contextlib import closing
from typing import Generator, Dict, Any

# Add API source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api/src'))


def find_free_port() -> int:
    """Find a free port for DynamoDB Local port forwarding"""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture(scope="session")
def dynamodb_local_port() -> int:
    """Get a free port for DynamoDB Local access"""
    return find_free_port()


@pytest.fixture(scope="session")
def kubectl_port_forward(dynamodb_local_port: int) -> Generator[int, None, None]:
    """Start kubectl port-forward for DynamoDB Local service"""
    # Start port forwarding
    process = subprocess.Popen([
        'kubectl', 'port-forward', 
        'service/dynamodb-local', 
        f'{dynamodb_local_port}:8000'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for port forward to be ready
    time.sleep(5)
    
    # Verify port forward is working
    max_retries = 30
    for _ in range(max_retries):
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.settimeout(1)
                if s.connect_ex(('localhost', dynamodb_local_port)) == 0:
                    break
            time.sleep(1)
        except:
            time.sleep(1)
    else:
        process.terminate()
        raise RuntimeError(f"Failed to establish port forward to DynamoDB Local on port {dynamodb_local_port}")
    
    try:
        yield dynamodb_local_port
    finally:
        # Cleanup: terminate port forward
        process.terminate()
        process.wait()


@pytest.fixture(scope="session")
def integration_aws_credentials():
    """Set up AWS credentials for integration testing with DynamoDB Local"""
    original_env = {}
    test_env = {
        'AWS_ACCESS_KEY_ID': 'test',
        'AWS_SECRET_ACCESS_KEY': 'test', 
        'AWS_DEFAULT_REGION': 'us-east-1',
        'AWS_REGION': 'us-east-1'
    }
    
    # Store and set environment variables
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    yield test_env
    
    # Restore original environment
    for key, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


@pytest.fixture(scope="session")
def dynamodb_local_client(kubectl_port_forward: int, integration_aws_credentials: Dict[str, str]) -> boto3.client:
    """Create a DynamoDB client connected to DynamoDB Local"""
    return boto3.client(
        'dynamodb',
        endpoint_url=f'http://localhost:{kubectl_port_forward}',
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )


@pytest.fixture(scope="session")
def dynamodb_local_resource(kubectl_port_forward: int, integration_aws_credentials: Dict[str, str]) -> boto3.resource:
    """Create a DynamoDB resource connected to DynamoDB Local"""
    return boto3.resource(
        'dynamodb',
        endpoint_url=f'http://localhost:{kubectl_port_forward}',
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )


@pytest.fixture
def tenant_config_table(dynamodb_local_resource: boto3.resource) -> Generator[Any, None, None]:
    """Create and manage the tenant configuration table for testing"""
    table_name = 'integration-test-tenant-configs'
    
    # Create table
    table = dynamodb_local_resource.create_table(
        TableName=table_name,
        KeySchema=[
            {'AttributeName': 'tenant_id', 'KeyType': 'HASH'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'tenant_id', 'AttributeType': 'S'}
        ],
        BillingMode='PAY_PER_REQUEST'
    )
    
    # Wait for table to be active
    table.wait_until_exists()
    
    yield table
    
    # Cleanup: delete table
    try:
        table.delete()
    except Exception:
        pass  # Table might not exist if test failed


@pytest.fixture
def tenant_service(tenant_config_table, kubectl_port_forward: int):
    """Create a TenantService instance configured for DynamoDB Local"""
    try:
        from src.services.dynamo import TenantService
        
        # Create service with custom DynamoDB resource
        service = TenantService(
            table_name=tenant_config_table.table_name,
            region='us-east-1'
        )
        
        # Override the DynamoDB resource to use DynamoDB Local
        service._dynamodb = boto3.resource(
            'dynamodb',
            endpoint_url=f'http://localhost:{kubectl_port_forward}',
            region_name='us-east-1',
            aws_access_key_id='test',
            aws_secret_access_key='test'
        )
        service._table = service._dynamodb.Table(tenant_config_table.table_name)
        
        return service
    except ImportError:
        pytest.skip("API modules not available for integration testing")


@pytest.fixture
def sample_integration_tenant() -> Dict[str, Any]:
    """Sample tenant data for integration testing"""
    return {
        "tenant_id": "integration-test-tenant",
        "log_distribution_role_arn": "arn:aws:iam::123456789012:role/IntegrationTestRole",
        "log_group_name": "/aws/logs/integration-test-tenant",
        "target_region": "us-east-1",
        "enabled": True,
        "desired_logs": ["test-app", "integration-service"]
    }


@pytest.fixture
def multiple_integration_tenants() -> list[Dict[str, Any]]:
    """Multiple tenant configurations for integration testing"""
    return [
        {
            "tenant_id": "integration-tenant-1",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/Role1",
            "log_group_name": "/aws/logs/integration-tenant-1",
            "target_region": "us-east-1",
            "enabled": True
        },
        {
            "tenant_id": "integration-tenant-2", 
            "log_distribution_role_arn": "arn:aws:iam::987654321098:role/Role2",
            "log_group_name": "/aws/logs/integration-tenant-2",
            "target_region": "us-west-2",
            "enabled": False,
            "desired_logs": ["payment-service"]
        },
        {
            "tenant_id": "integration-tenant-3",
            "log_distribution_role_arn": "arn:aws:iam::555666777888:role/Role3", 
            "log_group_name": "/aws/logs/integration-tenant-3",
            "target_region": "eu-west-1",
            "enabled": True,
            "desired_logs": ["user-service", "auth-service"]
        }
    ]


@pytest.fixture
def populated_integration_table(tenant_service, multiple_integration_tenants):
    """A tenant service with pre-populated integration test data"""
    for tenant in multiple_integration_tenants:
        tenant_service.create_tenant(tenant)
    return tenant_service