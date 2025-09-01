"""
Unit tests for API endpoints
"""

import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api/src'))

from src.app import app
from src.services.dynamo import TenantNotFoundError, DynamoDBError


@pytest.fixture
def client():
    """Create a test client for the FastAPI app"""
    return TestClient(app)


@pytest.fixture
def mock_delivery_config_service():
    """Create a mock delivery config service"""
    return Mock()


class TestHealthEndpoint:
    """Test cases for health check endpoint"""
    
    def test_health_check_success(self, client):
        """Test successful health check"""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "tenant-management-api"
        assert "timestamp" in data
        assert "version" in data


class TestDeliveryConfigEndpoints:
    """Test cases for delivery configuration management endpoints"""
    
    @patch('src.app.delivery_config_service')
    def test_list_all_delivery_configs_success(self, mock_delivery_config_service, client):
        """Test successful delivery config listing"""
        # Setup mock
        mock_delivery_config_service.list_tenant_configs.return_value = {
            "configurations": [
                {
                    "tenant_id": "test-tenant",
                    "type": "cloudwatch",
                    "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
                    "log_group_name": "/aws/logs/test-tenant",
                    "target_region": "us-east-1",
                    "enabled": True
                }
            ],
            "count": 1,
            "limit": 50
        }
        
        response = client.get("/api/v1/delivery-configs")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "configurations" in data["data"]
        assert "count" in data["data"]
        assert len(data["data"]["configurations"]) == 1
        mock_delivery_config_service.list_tenant_configs.assert_called_once_with(limit=50, last_key=None)
    
    @patch('src.app.delivery_config_service')
    def test_list_tenant_delivery_configs_success(self, mock_delivery_config_service, client):
        """Test listing delivery configs for a specific tenant"""
        # Setup mock
        mock_delivery_config_service.get_tenant_configs.return_value = [
            {
                "tenant_id": "test-tenant",
                "type": "cloudwatch",
                "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
                "log_group_name": "/aws/logs/test-tenant",
                "enabled": True
            }
        ]
        
        response = client.get("/api/v1/tenants/test-tenant/delivery-configs")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "configurations" in data["data"]
        assert "count" in data["data"]
        assert len(data["data"]["configurations"]) == 1
        mock_delivery_config_service.get_tenant_configs.assert_called_once_with("test-tenant")
    
    @patch('src.app.delivery_config_service')
    def test_list_all_delivery_configs_service_error(self, mock_delivery_config_service, client):
        """Test delivery config listing when service throws error"""
        # Setup mock to raise error
        mock_delivery_config_service.list_tenant_configs.side_effect = DynamoDBError("Connection failed")
        
        response = client.get("/api/v1/delivery-configs")
        
        assert response.status_code == 500
        data = response.json()
        assert "Failed to list delivery configurations" in data["detail"]
    
    @patch('src.app.delivery_config_service')
    def test_get_delivery_config_success(self, mock_delivery_config_service, client):
        """Test successful delivery config retrieval"""
        # Setup mock
        mock_delivery_config_service.get_tenant_config.return_value = {
            "tenant_id": "test-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
            "log_group_name": "/aws/logs/test-tenant",
            "target_region": "us-east-1",
            "enabled": True
        }
        
        response = client.get("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["tenant_id"] == "test-tenant"
        assert data["data"]["type"] == "cloudwatch"
        mock_delivery_config_service.get_tenant_config.assert_called_once_with("test-tenant", "cloudwatch")
    
    @patch('src.app.delivery_config_service')
    def test_get_delivery_config_not_found(self, mock_delivery_config_service, client):
        """Test delivery config retrieval when config doesn't exist"""
        # Setup mock to raise TenantNotFoundError
        mock_delivery_config_service.get_tenant_config.side_effect = TenantNotFoundError("Delivery configuration not found")
        
        response = client.get("/api/v1/tenants/nonexistent/delivery-configs/cloudwatch")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    @patch('src.app.delivery_config_service')
    def test_create_delivery_config_success(self, mock_delivery_config_service, client):
        """Test successful delivery config creation"""
        # Setup mock
        config_data = {
            "tenant_id": "new-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/NewRole",
            "log_group_name": "/aws/logs/new-tenant",
            "target_region": "us-east-1"
        }
        mock_delivery_config_service.create_tenant_config.return_value = config_data
        
        response = client.post("/api/v1/tenants/new-tenant/delivery-configs", json=config_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["tenant_id"] == "new-tenant"
        assert data["data"]["type"] == "cloudwatch"
        mock_delivery_config_service.create_tenant_config.assert_called_once()
    
    def test_create_delivery_config_invalid_data(self, client):
        """Test delivery config creation with invalid data"""
        invalid_data = {
            "tenant_id": "new-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "invalid-arn",  # Invalid ARN format
            "log_group_name": "/aws/logs/new-tenant",
            "target_region": "us-east-1"
        }
        
        response = client.post("/api/v1/tenants/new-tenant/delivery-configs", json=invalid_data)
        
        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert "detail" in data
        # Verify validation error mentions the role ARN
        error_details = str(data["detail"])
        assert "log_distribution_role_arn" in error_details
    
    @patch('src.app.delivery_config_service')
    def test_create_delivery_config_duplicate(self, mock_delivery_config_service, client):
        """Test delivery config creation with duplicate configuration"""
        # Setup mock to raise DynamoDBError for duplicate
        mock_delivery_config_service.create_tenant_config.side_effect = DynamoDBError("Configuration already exists")
        
        config_data = {
            "tenant_id": "existing-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/ExistingRole",
            "log_group_name": "/aws/logs/existing-tenant",
            "target_region": "us-east-1"
        }
        
        response = client.post("/api/v1/tenants/existing-tenant/delivery-configs", json=config_data)
        
        assert response.status_code == 400
        data = response.json()
        assert "already exists" in data["detail"].lower()
    
    @patch('src.app.delivery_config_service')
    def test_update_delivery_config_success(self, mock_delivery_config_service, client):
        """Test successful delivery config update"""
        # Setup mock
        updated_data = {
            "tenant_id": "test-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/UpdatedRole",
            "log_group_name": "/aws/logs/updated-tenant",
            "target_region": "us-west-2",
            "enabled": False
        }
        mock_delivery_config_service.update_tenant_config.return_value = updated_data
        
        update_request = {
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/UpdatedRole",
            "log_group_name": "/aws/logs/updated-tenant",
            "target_region": "us-west-2",
            "enabled": False
        }
        
        response = client.put("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch", json=update_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["tenant_id"] == "test-tenant"
        assert data["data"]["type"] == "cloudwatch"
        assert data["data"]["enabled"] is False
        mock_delivery_config_service.update_tenant_config.assert_called_once_with("test-tenant", "cloudwatch", update_request)
    
    @patch('src.app.delivery_config_service')
    def test_update_delivery_config_not_found(self, mock_delivery_config_service, client):
        """Test delivery config update when config doesn't exist"""
        # Setup mock to raise TenantNotFoundError
        mock_delivery_config_service.update_tenant_config.side_effect = TenantNotFoundError("Delivery configuration not found")
        
        update_request = {"enabled": False}
        
        response = client.put("/api/v1/tenants/nonexistent/delivery-configs/cloudwatch", json=update_request)
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    @patch('src.app.delivery_config_service')
    def test_patch_delivery_config_success(self, mock_delivery_config_service, client):
        """Test successful delivery config patch (partial update)"""
        # Setup mock
        patched_data = {
            "tenant_id": "test-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
            "log_group_name": "/aws/logs/test-tenant",
            "target_region": "us-east-1",
            "enabled": False  # Only this field was patched
        }
        mock_delivery_config_service.patch_tenant_config.return_value = patched_data
        
        patch_request = {"enabled": False}
        
        response = client.patch("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch", json=patch_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["tenant_id"] == "test-tenant"
        assert data["data"]["type"] == "cloudwatch"
        assert data["data"]["enabled"] is False
        mock_delivery_config_service.patch_tenant_config.assert_called_once_with("test-tenant", "cloudwatch", patch_request)
    
    @patch('src.app.delivery_config_service')
    def test_delete_delivery_config_success(self, mock_delivery_config_service, client):
        """Test successful delivery config deletion"""
        # Setup mock
        mock_delivery_config_service.delete_tenant_config.return_value = None
        
        response = client.delete("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch")
        
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower()
        mock_delivery_config_service.delete_tenant_config.assert_called_once_with("test-tenant", "cloudwatch")
    
    @patch('src.app.delivery_config_service')
    def test_delete_delivery_config_not_found(self, mock_delivery_config_service, client):
        """Test delivery config deletion when config doesn't exist"""
        # Setup mock to raise TenantNotFoundError
        mock_delivery_config_service.delete_tenant_config.side_effect = TenantNotFoundError("Delivery configuration not found")
        
        response = client.delete("/api/v1/tenants/nonexistent/delivery-configs/cloudwatch")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    @patch('src.app.delivery_config_service')
    def test_validate_delivery_config_success(self, mock_delivery_config_service, client):
        """Test successful delivery config validation"""
        # Setup mock
        validation_result = {
            "tenant_id": "test-tenant",
            "type": "cloudwatch",
            "valid": True,
            "checks": [
                {"field": "log_distribution_role_arn", "status": "ok", "message": "Field is present"},
                {"field": "log_group_name", "status": "ok", "message": "Field is present"},
                {"field": "target_region", "status": "ok", "message": "Field is present"}
            ]
        }
        mock_delivery_config_service.validate_tenant_config.return_value = validation_result
        
        response = client.get("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch/validate")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["tenant_id"] == "test-tenant"
        assert data["data"]["type"] == "cloudwatch"
        assert data["data"]["valid"] is True
        assert len(data["data"]["checks"]) == 3
        mock_delivery_config_service.validate_tenant_config.assert_called_once_with("test-tenant", "cloudwatch")
    
    @patch('src.app.delivery_config_service')
    def test_validate_delivery_config_invalid(self, mock_delivery_config_service, client):
        """Test delivery config validation with invalid configuration"""
        # Setup mock
        validation_result = {
            "tenant_id": "invalid-tenant",
            "type": "cloudwatch",
            "valid": False,
            "checks": [
                {"field": "log_distribution_role_arn", "status": "invalid", "message": "Role ARN format is invalid"},
                {"field": "log_group_name", "status": "missing", "message": "Required field is missing"}
            ]
        }
        mock_delivery_config_service.validate_tenant_config.return_value = validation_result
        
        response = client.get("/api/v1/tenants/invalid-tenant/delivery-configs/cloudwatch/validate")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["tenant_id"] == "invalid-tenant"
        assert data["data"]["type"] == "cloudwatch"
        assert data["data"]["valid"] is False
        assert len(data["data"]["checks"]) == 2
    
    @patch('src.app.delivery_config_service')
    def test_validate_delivery_config_not_found(self, mock_delivery_config_service, client):
        """Test delivery config validation when config doesn't exist"""
        # Setup mock to raise TenantNotFoundError
        mock_delivery_config_service.validate_tenant_config.side_effect = TenantNotFoundError("Delivery configuration not found")
        
        response = client.get("/api/v1/tenants/nonexistent/delivery-configs/cloudwatch/validate")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestErrorHandling:
    """Test cases for error handling scenarios"""
    
    def test_invalid_json_body(self, client):
        """Test handling of invalid JSON in request body"""
        response = client.post(
            "/api/v1/tenants/test-tenant/delivery-configs",
            content="invalid json",
            headers={"content-type": "application/json"}
        )
        
        assert response.status_code == 422
    
    def test_missing_required_fields(self, client):
        """Test validation of missing required fields"""
        incomplete_data = {
            "tenant_id": "incomplete-tenant",
            "type": "cloudwatch"
            # Missing required fields for cloudwatch type
        }
        
        response = client.post("/api/v1/tenants/incomplete-tenant/delivery-configs", json=incomplete_data)
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        # Should mention missing required fields
        error_details = str(data["detail"])
        assert any(field in error_details for field in ["log_distribution_role_arn", "log_group_name"])
    
    def test_invalid_desired_logs_format(self, client):
        """Test validation of invalid desired_logs format"""
        invalid_data = {
            "tenant_id": "test-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
            "log_group_name": "/aws/logs/test-tenant",
            "target_region": "us-east-1",
            "desired_logs": []  # Empty list is invalid
        }
        
        response = client.post("/api/v1/tenants/test-tenant/delivery-configs", json=invalid_data)
        
        assert response.status_code == 422
        data = response.json()
        error_details = str(data["detail"])
        assert "desired_logs" in error_details