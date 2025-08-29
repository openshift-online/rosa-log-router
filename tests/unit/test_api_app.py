"""
Unit tests for API application
"""
import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient

# Import the module under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api/src'))

from app import app


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
    
    @patch('app.tenant_service')
    def test_get_tenant_success(self, mock_tenant_service, client, environment_variables):
        """Test successful tenant retrieval."""
        mock_tenant_service.get_tenant.return_value = {
            'tenant_id': 'test-tenant',
            'log_distribution_role_arn': 'arn:aws:iam::123456789012:role/TestRole',
            'log_group_name': '/aws/logs/test',
            'target_region': 'us-east-1',
            'enabled': True
        }
        
        response = client.get("/api/v1/tenants/test-tenant")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["tenant_id"] == "test-tenant"
    
    @patch('app.tenant_service')
    def test_get_tenant_not_found(self, mock_tenant_service, client, environment_variables):
        """Test tenant not found."""
        from src.services.dynamo import TenantNotFoundError
        mock_tenant_service.get_tenant.side_effect = TenantNotFoundError("Tenant not found")
        
        response = client.get("/api/v1/tenants/nonexistent")
        
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["message"].lower()
    
    @patch('app.tenant_service')
    def test_create_tenant_success(self, mock_tenant_service, client, environment_variables):
        """Test successful tenant creation."""
        tenant_data = {
            "tenant_id": "new-tenant",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/NewRole",
            "log_group_name": "/aws/logs/new-tenant",
            "target_region": "us-east-1",
            "enabled": True
        }
        
        mock_tenant_service.create_tenant.return_value = tenant_data
        
        response = client.post("/api/v1/tenants", json=tenant_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["tenant_id"] == "new-tenant"
    
    @patch('app.tenant_service')
    def test_update_tenant_success(self, mock_tenant_service, client, environment_variables):
        """Test successful tenant update."""
        update_data = {
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/UpdatedRole",
            "log_group_name": "/aws/logs/updated",
            "target_region": "us-west-2",
            "enabled": False
        }
        
        updated_tenant = {
            "tenant_id": "test-tenant",
            **update_data
        }
        
        mock_tenant_service.update_tenant.return_value = updated_tenant
        
        response = client.put("/api/v1/tenants/test-tenant", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["enabled"] is False
    
    @patch('app.tenant_service')
    def test_delete_tenant_success(self, mock_tenant_service, client, environment_variables):
        """Test successful tenant deletion."""
        mock_tenant_service.delete_tenant.return_value = None
        
        response = client.delete("/api/v1/tenants/test-tenant")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted" in data["message"].lower()
    
    def test_validation_error(self, client, environment_variables):
        """Test validation error handling."""
        invalid_data = {
            "tenant_id": "",  # Invalid empty tenant_id
            "log_distribution_role_arn": "invalid-arn"
        }
        
        response = client.post("/api/v1/tenants", json=invalid_data)
        
        assert response.status_code == 422
        data = response.json()
        assert data["success"] is False
        assert "validation" in data["message"].lower()


class TestAPIModels:
    """Test API model validation."""
    
    def test_tenant_create_request_validation(self):
        """Test tenant creation request validation."""
        from models.tenant import TenantCreateRequest
        
        # Valid request
        valid_data = {
            "tenant_id": "test-tenant",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
            "log_group_name": "/aws/logs/test",
            "target_region": "us-east-1"
        }
        
        request = TenantCreateRequest(**valid_data)
        assert request.tenant_id == "test-tenant"
        assert request.enabled is True  # Default value
    
    def test_tenant_create_request_invalid_arn(self):
        """Test tenant creation with invalid ARN."""
        from models.tenant import TenantCreateRequest
        from pydantic import ValidationError
        
        invalid_data = {
            "tenant_id": "test-tenant",
            "log_distribution_role_arn": "invalid-arn",
            "log_group_name": "/aws/logs/test",
            "target_region": "us-east-1"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TenantCreateRequest(**invalid_data)
        
        assert "arn format" in str(exc_info.value).lower()
    
    def test_tenant_update_request_partial(self):
        """Test partial tenant update request."""
        from models.tenant import TenantUpdateRequest
        
        partial_data = {
            "enabled": False,
            "desired_logs": ["service1", "service2"]
        }
        
        request = TenantUpdateRequest(**partial_data)
        assert request.enabled is False
        assert request.desired_logs == ["service1", "service2"]
        assert request.log_distribution_role_arn is None  # Optional field