"""
Unit tests for API application
"""
import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient

# Import the module under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api/src'))

from src.app import app


class TestAPIEndpoints:
    """Test API endpoint functionality."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def environment_variables(self):
        """Set up test environment variables."""
        test_env = {
            'TENANT_CONFIG_TABLE': 'test-tenant-configs',
            'AWS_REGION': 'us-east-1'
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
    
    def test_health_check_endpoint(self, client, environment_variables):
        """Test health check endpoint."""
        with patch('src.handlers.health.get_health_status') as mock_health:
            mock_health.return_value = {
                "status": "healthy",
                "timestamp": "2024-01-01T10:00:00Z",
                "version": "1.0.0"
            }
            
            response = client.get("/api/v1/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            mock_health.assert_called_once()
    
    @patch('src.app.delivery_config_service')
    def test_get_delivery_config_success(self, mock_delivery_config_service, client, environment_variables):
        """Test successful delivery config retrieval."""
        mock_delivery_config_service.get_tenant_config.return_value = {
            'tenant_id': 'test-tenant',
            'type': 'cloudwatch',
            'log_distribution_role_arn': 'arn:aws:iam::123456789012:role/TestRole',
            'log_group_name': '/aws/logs/test',
            'target_region': 'us-east-1',
            'enabled': True
        }
        
        response = client.get("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["tenant_id"] == "test-tenant"
        assert data["data"]["type"] == "cloudwatch"
    
    @patch('src.app.delivery_config_service')
    def test_get_delivery_config_not_found(self, mock_delivery_config_service, client, environment_variables):
        """Test delivery config not found."""
        from src.services.dynamo import TenantNotFoundError
        mock_delivery_config_service.get_tenant_config.side_effect = TenantNotFoundError("Delivery configuration not found")
        
        response = client.get("/api/v1/tenants/nonexistent/delivery-configs/cloudwatch")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    @patch('src.app.delivery_config_service')
    def test_create_delivery_config_success(self, mock_delivery_config_service, client, environment_variables):
        """Test successful delivery config creation."""
        config_data = {
            "tenant_id": "new-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/NewRole",
            "log_group_name": "/aws/logs/new-tenant",
            "target_region": "us-east-1",
            "enabled": True
        }
        
        mock_delivery_config_service.create_tenant_config.return_value = config_data
        
        response = client.post("/api/v1/tenants/new-tenant/delivery-configs", json=config_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["tenant_id"] == "new-tenant"
        assert data["data"]["type"] == "cloudwatch"
    
    @patch('src.app.delivery_config_service')
    def test_update_delivery_config_success(self, mock_delivery_config_service, client, environment_variables):
        """Test successful delivery config update."""
        update_data = {
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/UpdatedRole",
            "log_group_name": "/aws/logs/updated",
            "target_region": "us-west-2",
            "enabled": False
        }
        
        updated_config = {
            "tenant_id": "test-tenant",
            "type": "cloudwatch",
            **update_data
        }
        
        mock_delivery_config_service.update_tenant_config.return_value = updated_config
        
        response = client.put("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["enabled"] is False
        assert data["data"]["type"] == "cloudwatch"
    
    @patch('src.app.delivery_config_service')
    def test_delete_delivery_config_success(self, mock_delivery_config_service, client, environment_variables):
        """Test successful delivery config deletion."""
        mock_delivery_config_service.delete_tenant_config.return_value = None
        
        response = client.delete("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "deleted" in data["message"].lower()
    
    def test_validation_error(self, client, environment_variables):
        """Test validation error handling."""
        invalid_data = {
            "tenant_id": "",  # Invalid empty tenant_id
            "type": "cloudwatch",
            "log_distribution_role_arn": "invalid-arn"
        }
        
        response = client.post("/api/v1/tenants/test-tenant/delivery-configs", json=invalid_data)
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestAPIModels:
    """Test API model validation."""
    
    def test_delivery_config_create_request_validation(self):
        """Test delivery config creation request validation."""
        from src.models.tenant import TenantDeliveryConfigCreateRequest
        
        # Valid CloudWatch request
        valid_data = {
            "tenant_id": "test-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
            "log_group_name": "/aws/logs/test",
            "target_region": "us-east-1"
        }
        
        request = TenantDeliveryConfigCreateRequest(**valid_data)
        assert request.tenant_id == "test-tenant"
        assert request.type == "cloudwatch"
        assert request.enabled is None  # No default in base model
    
    def test_delivery_config_create_request_invalid_arn(self):
        """Test delivery config creation with invalid ARN."""
        from src.models.tenant import TenantDeliveryConfigCreateRequest
        from pydantic import ValidationError
        
        invalid_data = {
            "tenant_id": "test-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "invalid-arn",
            "log_group_name": "/aws/logs/test",
            "target_region": "us-east-1"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TenantDeliveryConfigCreateRequest(**invalid_data)
        
        assert "arn" in str(exc_info.value).lower()
    
    def test_delivery_config_update_request_partial(self):
        """Test partial delivery config update request."""
        from src.models.tenant import TenantDeliveryConfigUpdateRequest
        
        partial_data = {
            "enabled": False,
            "desired_logs": ["service1", "service2"]
        }
        
        request = TenantDeliveryConfigUpdateRequest(**partial_data)
        assert request.enabled is False
        assert request.desired_logs == ["service1", "service2"]
        assert request.log_distribution_role_arn is None  # Optional field
    
    def test_s3_delivery_config_create_request_validation(self):
        """Test S3 delivery config creation request validation."""
        from src.models.tenant import TenantDeliveryConfigCreateRequest
        
        # Valid S3 request
        valid_data = {
            "tenant_id": "test-tenant",
            "type": "s3",
            "bucket_name": "my-log-bucket",
            "bucket_prefix": "logs/",
            "target_region": "us-east-1"
        }
        
        request = TenantDeliveryConfigCreateRequest(**valid_data)
        assert request.tenant_id == "test-tenant"
        assert request.type == "s3"
        assert request.bucket_name == "my-log-bucket"
        assert request.bucket_prefix == "logs/"