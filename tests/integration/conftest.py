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
import requests
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
    # Start port forwarding with explicit namespace
    process = subprocess.Popen([
        'kubectl', 'port-forward', 
        'service/dynamodb-local', 
        f'{dynamodb_local_port}:8000',
        '--namespace=logging'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for port forward to be ready with increased time for GitHub Actions
    time.sleep(10)
    
    # Verify port forward is working with improved retry logic
    max_retries = 60  # Increased from 30 to 60 for GitHub Actions
    retry_delay = 1
    for attempt in range(max_retries):
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.settimeout(2)  # Increased socket timeout
                if s.connect_ex(('localhost', dynamodb_local_port)) == 0:
                    print(f"✅ DynamoDB Local port forward established on port {dynamodb_local_port}")
                    break
            # Exponential backoff for GitHub Actions compatibility
            time.sleep(min(retry_delay, 5))
            if attempt % 10 == 9:  # Every 10 attempts, increase delay
                retry_delay = min(retry_delay * 1.5, 3)
        except Exception as e:
            print(f"⚠️ Port forward attempt {attempt + 1}/{max_retries} failed: {e}")
            time.sleep(retry_delay)
    else:
        # Enhanced error reporting
        stdout, stderr = process.communicate(timeout=5) if process.poll() is None else (b'', b'')
        process.terminate()
        error_msg = f"""Failed to establish port forward to DynamoDB Local on port {dynamodb_local_port}
        Kubectl stdout: {stdout.decode() if stdout else 'None'}
        Kubectl stderr: {stderr.decode() if stderr else 'None'}
        Process return code: {process.returncode}
        
        Troubleshooting:
        1. Verify DynamoDB Local service is running: kubectl get svc -n logging
        2. Check DynamoDB Local pod status: kubectl get pods -n logging -l app=dynamodb-local
        3. Verify namespace exists: kubectl get ns logging
        """
        raise RuntimeError(error_msg)
    
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
    """Create and manage the tenant delivery configuration table for testing"""
    table_name = 'integration-test-tenant-configs'
    
    # Create table with composite key (tenant_id + type)
    table = dynamodb_local_resource.create_table(
        TableName=table_name,
        KeySchema=[
            {'AttributeName': 'tenant_id', 'KeyType': 'HASH'},
            {'AttributeName': 'type', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'tenant_id', 'AttributeType': 'S'},
            {'AttributeName': 'type', 'AttributeType': 'S'}
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
def api_client():
    """Create an HTTP client for making requests to the tenant configuration API"""
    class APIClient:
        def __init__(self, base_url: str = None):
            if base_url is None:
                base_url = os.getenv("API_BASE_URL", "http://tenant-config-api:8080")
            self.base_url = base_url.rstrip('/')
            self.session = requests.Session()
            # Set default timeout for all requests
            self.session.timeout = 30
        
        def create_delivery_config(self, tenant_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
            """Create a delivery configuration via API"""
            url = f"{self.base_url}/api/v1/tenants/{tenant_id}/delivery-configs"
            response = self.session.post(url, json=config_data)
            response.raise_for_status()
            return response.json()
        
        def get_delivery_config(self, tenant_id: str, delivery_type: str) -> Dict[str, Any]:
            """Get a delivery configuration via API"""
            url = f"{self.base_url}/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        def update_delivery_config(self, tenant_id: str, delivery_type: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
            """Update a delivery configuration via API"""
            url = f"{self.base_url}/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}"
            response = self.session.put(url, json=update_data)
            response.raise_for_status()
            return response.json()
        
        def patch_delivery_config(self, tenant_id: str, delivery_type: str, patch_data: Dict[str, Any]) -> Dict[str, Any]:
            """Patch a delivery configuration via API"""
            url = f"{self.base_url}/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}"
            response = self.session.patch(url, json=patch_data)
            response.raise_for_status()
            return response.json()
        
        def delete_delivery_config(self, tenant_id: str, delivery_type: str) -> Dict[str, Any]:
            """Delete a delivery configuration via API"""
            url = f"{self.base_url}/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}"
            response = self.session.delete(url)
            response.raise_for_status()
            return response.json()
        
        def list_tenant_delivery_configs(self, tenant_id: str) -> Dict[str, Any]:
            """List all delivery configurations for a tenant via API"""
            url = f"{self.base_url}/api/v1/tenants/{tenant_id}/delivery-configs"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        def list_all_delivery_configs(self, limit: int = 50, last_key: str = None) -> Dict[str, Any]:
            """List all delivery configurations via API"""
            url = f"{self.base_url}/api/v1/delivery-configs"
            params = {"limit": limit}
            if last_key:
                params["last_key"] = last_key
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        
        def validate_delivery_config(self, tenant_id: str, delivery_type: str) -> Dict[str, Any]:
            """Validate a delivery configuration via API"""
            url = f"{self.base_url}/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}/validate"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        def health_check(self) -> Dict[str, Any]:
            """Check API health"""
            url = f"{self.base_url}/api/v1/health"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
    
    return APIClient()


@pytest.fixture
def delivery_config_service(tenant_config_table, kubectl_port_forward: int):
    """Create a TenantDeliveryConfigService instance configured for DynamoDB Local
    
    Note: This fixture is kept for table setup/teardown only.
    Tests should use api_client for data operations.
    """
    try:
        from src.services.dynamo import TenantDeliveryConfigService
        
        # Create service with custom DynamoDB resource
        service = TenantDeliveryConfigService(
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
def sample_integration_cloudwatch_config() -> Dict[str, Any]:
    """Sample CloudWatch delivery configuration for integration testing"""
    return {
        "tenant_id": "integration-test-tenant",
        "type": "cloudwatch",
        "log_distribution_role_arn": "arn:aws:iam::123456789012:role/IntegrationTestRole",
        "log_group_name": "/aws/logs/integration-test-tenant",
        "target_region": "us-east-1",
        "enabled": True,
        "desired_logs": ["test-app", "integration-service"],
        "groups": ["test-group", "integration-group"]
    }


@pytest.fixture
def sample_integration_s3_config() -> Dict[str, Any]:
    """Sample S3 delivery configuration for integration testing"""
    return {
        "tenant_id": "integration-test-tenant",
        "type": "s3",
        "bucket_name": "integration-test-logs",
        "bucket_prefix": "cluster-logs/",
        "target_region": "us-east-1",
        "enabled": True,
        "desired_logs": ["test-app", "integration-service"],
        "groups": ["test-group", "integration-group"]
    }


@pytest.fixture
def multiple_integration_delivery_configs() -> list[Dict[str, Any]]:
    """Multiple delivery configurations for integration testing"""
    return [
        # Tenant 1 - CloudWatch configuration
        {
            "tenant_id": "integration-tenant-1",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/Role1",
            "log_group_name": "/aws/logs/integration-tenant-1",
            "target_region": "us-east-1",
            "enabled": True,
            "groups": ["frontend-group", "api-group"]
        },
        # Tenant 1 - S3 configuration
        {
            "tenant_id": "integration-tenant-1",
            "type": "s3",
            "bucket_name": "integration-tenant-1-logs",
            "bucket_prefix": "logs/",
            "target_region": "us-east-1",
            "enabled": True,
            "groups": ["frontend-group", "api-group"]
        },
        # Tenant 2 - CloudWatch configuration
        {
            "tenant_id": "integration-tenant-2", 
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::987654321098:role/Role2",
            "log_group_name": "/aws/logs/integration-tenant-2",
            "target_region": "us-west-2",
            "enabled": False,
            "desired_logs": ["payment-service"],
            "groups": ["payment-group"]
        },
        # Tenant 2 - S3 configuration
        {
            "tenant_id": "integration-tenant-2",
            "type": "s3",
            "bucket_name": "integration-tenant-2-logs",
            "bucket_prefix": "logs/",
            "target_region": "us-west-2",
            "enabled": True,
            "desired_logs": ["payment-service"],
            "groups": ["payment-group"]
        }
    ]


@pytest.fixture
def populated_integration_table(api_client, tenant_config_table, multiple_integration_delivery_configs):
    """A delivery config table with pre-populated integration test data via API calls"""
    for config in multiple_integration_delivery_configs:
        # Use API to create delivery configurations instead of direct service calls
        api_client.create_delivery_config(config["tenant_id"], config)
    return api_client