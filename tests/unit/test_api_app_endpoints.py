"""
Unit tests for API endpoints
"""

import hashlib
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
    return TestClient(app)


def _body_hash(data) -> str:
    """Compute X-Body-SHA256 for a request body (dict → JSON bytes, str → utf-8 bytes)."""
    if isinstance(data, dict):
        raw = json.dumps(data, separators=(",", ":")).encode()
    elif isinstance(data, str):
        raw = data.encode()
    else:
        raw = data or b""
    return hashlib.sha256(raw).hexdigest()


def post_json(client, url, data):
    """POST with auto X-Body-SHA256 header."""
    raw = json.dumps(data).encode()
    return client.post(url, content=raw,
                       headers={"Content-Type": "application/json",
                                "X-Body-SHA256": hashlib.sha256(raw).hexdigest()})


def put_json(client, url, data):
    """PUT with auto X-Body-SHA256 header."""
    raw = json.dumps(data).encode()
    return client.put(url, content=raw,
                      headers={"Content-Type": "application/json",
                               "X-Body-SHA256": hashlib.sha256(raw).hexdigest()})


def patch_json(client, url, data):
    """PATCH with auto X-Body-SHA256 header."""
    raw = json.dumps(data).encode()
    return client.patch(url, content=raw,
                        headers={"Content-Type": "application/json",
                                 "X-Body-SHA256": hashlib.sha256(raw).hexdigest()})


class TestHealthEndpoint:
    @patch('src.services.dynamo.TenantDeliveryConfigService')
    def test_health_check_success(self, mock_service_class, client):
        mock_service = Mock()
        mock_service.dynamodb.describe_table.return_value = {"Table": {"TableName": "test-table"}}
        mock_service_class.return_value = mock_service
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["checks"]["dynamodb"]["status"] == "healthy"

    @patch('src.services.dynamo.TenantDeliveryConfigService')
    def test_health_check_dynamodb_table_not_found(self, mock_service_class, client):
        mock_service = Mock()
        mock_service.dynamodb.meta.client.describe_table.side_effect = Exception("ResourceNotFoundException")
        mock_service_class.return_value = mock_service
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["checks"]["dynamodb"]["status"] == "healthy"
        assert data["checks"]["dynamodb"]["note"] == "table_not_exists_but_connection_ok"

    @patch('src.services.dynamo.TenantDeliveryConfigService')
    def test_health_check_dynamodb_connection_error(self, mock_service_class, client):
        mock_service = Mock()
        mock_service.dynamodb.meta.client.describe_table.side_effect = Exception("Connection timeout")
        mock_service_class.return_value = mock_service
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["dynamodb"]["status"] == "unhealthy"

    @patch('src.services.dynamo.TenantDeliveryConfigService')
    def test_health_check_service_initialization_error(self, mock_service_class, client):
        mock_service_class.side_effect = Exception("Failed to initialize service")
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["dynamodb"]["status"] == "unhealthy"


class TestDeliveryConfigEndpoints:
    @patch('src.app.delivery_config_service')
    def test_list_all_delivery_configs_success(self, mock_service, client):
        mock_service.list_tenant_configs.return_value = {
            "configurations": [{"tenant_id": "test-tenant", "type": "cloudwatch",
                                 "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
                                 "log_group_name": "/aws/logs/test-tenant",
                                 "target_region": "us-east-1", "enabled": True}],
            "count": 1, "limit": 50
        }
        response = client.get("/api/v1/delivery-configs")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["configurations"]) == 1
        mock_service.list_tenant_configs.assert_called_once_with(limit=50, last_key=None)

    @patch('src.app.delivery_config_service')
    def test_list_tenant_delivery_configs_success(self, mock_service, client):
        mock_service.get_tenant_configs.return_value = [
            {"tenant_id": "test-tenant", "type": "cloudwatch",
             "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
             "log_group_name": "/aws/logs/test-tenant", "enabled": True}
        ]
        response = client.get("/api/v1/tenants/test-tenant/delivery-configs")
        assert response.status_code == 200
        assert len(response.json()["data"]["configurations"]) == 1

    @patch('src.app.delivery_config_service')
    def test_list_all_delivery_configs_service_error(self, mock_service, client):
        mock_service.list_tenant_configs.side_effect = DynamoDBError("Connection failed")
        response = client.get("/api/v1/delivery-configs")
        assert response.status_code == 500

    @patch('src.app.delivery_config_service')
    def test_get_delivery_config_success(self, mock_service, client):
        mock_service.get_tenant_config.return_value = {
            "tenant_id": "test-tenant", "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
            "log_group_name": "/aws/logs/test-tenant", "target_region": "us-east-1", "enabled": True
        }
        response = client.get("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch")
        assert response.status_code == 200
        assert response.json()["data"]["tenant_id"] == "test-tenant"

    @patch('src.app.delivery_config_service')
    def test_get_delivery_config_not_found(self, mock_service, client):
        mock_service.get_tenant_config.side_effect = TenantNotFoundError("not found")
        response = client.get("/api/v1/tenants/nonexistent/delivery-configs/cloudwatch")
        assert response.status_code == 404

    @patch('src.app.delivery_config_service')
    def test_create_delivery_config_success(self, mock_service, client):
        config_data = {"tenant_id": "new-tenant", "type": "cloudwatch",
                       "log_distribution_role_arn": "arn:aws:iam::123456789012:role/NewRole",
                       "log_group_name": "/aws/logs/new-tenant", "target_region": "us-east-1"}
        mock_service.create_tenant_config.return_value = config_data
        response = post_json(client, "/api/v1/tenants/new-tenant/delivery-configs", config_data)
        assert response.status_code == 201
        assert response.json()["data"]["tenant_id"] == "new-tenant"
        mock_service.create_tenant_config.assert_called_once()

    def test_create_delivery_config_invalid_data(self, client):
        invalid_data = {"tenant_id": "new-tenant", "type": "cloudwatch",
                        "log_distribution_role_arn": "invalid-arn",
                        "log_group_name": "/aws/logs/new-tenant", "target_region": "us-east-1"}
        response = post_json(client, "/api/v1/tenants/new-tenant/delivery-configs", invalid_data)
        assert response.status_code == 422
        assert "log_distribution_role_arn" in str(response.json()["detail"])

    @patch('src.app.delivery_config_service')
    def test_create_delivery_config_duplicate(self, mock_service, client):
        mock_service.create_tenant_config.side_effect = DynamoDBError("Configuration already exists")
        config_data = {"tenant_id": "existing-tenant", "type": "cloudwatch",
                       "log_distribution_role_arn": "arn:aws:iam::123456789012:role/ExistingRole",
                       "log_group_name": "/aws/logs/existing-tenant", "target_region": "us-east-1"}
        response = post_json(client, "/api/v1/tenants/existing-tenant/delivery-configs", config_data)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    @patch('src.app.delivery_config_service')
    def test_update_delivery_config_success(self, mock_service, client):
        updated_data = {"tenant_id": "test-tenant", "type": "cloudwatch",
                        "log_distribution_role_arn": "arn:aws:iam::123456789012:role/UpdatedRole",
                        "log_group_name": "/aws/logs/updated-tenant",
                        "target_region": "us-west-2", "enabled": False}
        mock_service.update_tenant_config.return_value = updated_data
        update_request = {"log_distribution_role_arn": "arn:aws:iam::123456789012:role/UpdatedRole",
                          "log_group_name": "/aws/logs/updated-tenant",
                          "target_region": "us-west-2", "enabled": False}
        response = put_json(client, "/api/v1/tenants/test-tenant/delivery-configs/cloudwatch", update_request)
        assert response.status_code == 200
        assert response.json()["data"]["enabled"] is False

    @patch('src.app.delivery_config_service')
    def test_update_delivery_config_not_found(self, mock_service, client):
        mock_service.update_tenant_config.side_effect = TenantNotFoundError("not found")
        response = put_json(client, "/api/v1/tenants/nonexistent/delivery-configs/cloudwatch", {"enabled": False})
        assert response.status_code == 404

    @patch('src.app.delivery_config_service')
    def test_patch_delivery_config_success(self, mock_service, client):
        patched_data = {"tenant_id": "test-tenant", "type": "cloudwatch",
                        "log_distribution_role_arn": "arn:aws:iam::123456789012:role/TestRole",
                        "log_group_name": "/aws/logs/test-tenant",
                        "target_region": "us-east-1", "enabled": False}
        mock_service.patch_tenant_config.return_value = patched_data
        response = patch_json(client, "/api/v1/tenants/test-tenant/delivery-configs/cloudwatch", {"enabled": False})
        assert response.status_code == 200
        assert response.json()["data"]["enabled"] is False
        mock_service.patch_tenant_config.assert_called_once_with("test-tenant", "cloudwatch", {"enabled": False})

    @patch('src.app.delivery_config_service')
    def test_delete_delivery_config_success(self, mock_service, client):
        mock_service.delete_tenant_config.return_value = None
        response = client.delete("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch")
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()

    @patch('src.app.delivery_config_service')
    def test_delete_delivery_config_not_found(self, mock_service, client):
        mock_service.delete_tenant_config.side_effect = TenantNotFoundError("not found")
        response = client.delete("/api/v1/tenants/nonexistent/delivery-configs/cloudwatch")
        assert response.status_code == 404

    @patch('src.app.delivery_config_service')
    def test_validate_delivery_config_success(self, mock_service, client):
        mock_service.validate_tenant_config.return_value = {
            "tenant_id": "test-tenant", "type": "cloudwatch", "valid": True,
            "checks": [{"field": "log_distribution_role_arn", "status": "ok", "message": "ok"},
                       {"field": "log_group_name", "status": "ok", "message": "ok"},
                       {"field": "target_region", "status": "ok", "message": "ok"}]
        }
        response = client.get("/api/v1/tenants/test-tenant/delivery-configs/cloudwatch/validate")
        assert response.status_code == 200
        assert response.json()["data"]["valid"] is True

    @patch('src.app.delivery_config_service')
    def test_validate_delivery_config_invalid(self, mock_service, client):
        mock_service.validate_tenant_config.return_value = {
            "tenant_id": "invalid-tenant", "type": "cloudwatch", "valid": False,
            "checks": [{"field": "log_distribution_role_arn", "status": "invalid", "message": "invalid"},
                       {"field": "log_group_name", "status": "missing", "message": "missing"}]
        }
        response = client.get("/api/v1/tenants/invalid-tenant/delivery-configs/cloudwatch/validate")
        assert response.status_code == 200
        assert response.json()["data"]["valid"] is False

    @patch('src.app.delivery_config_service')
    def test_validate_delivery_config_not_found(self, mock_service, client):
        mock_service.validate_tenant_config.side_effect = TenantNotFoundError("not found")
        response = client.get("/api/v1/tenants/nonexistent/delivery-configs/cloudwatch/validate")
        assert response.status_code == 404


class TestErrorHandling:
    def test_invalid_json_body(self, client):
        """POST with invalid JSON — middleware passes (hash matches bytes sent), FastAPI rejects with 422."""
        raw = b"invalid json"
        response = client.post(
            "/api/v1/tenants/test-tenant/delivery-configs",
            content=raw,
            headers={"Content-Type": "application/json",
                     "X-Body-SHA256": hashlib.sha256(raw).hexdigest()}
        )
        assert response.status_code == 422

    def test_missing_required_fields(self, client):
        incomplete_data = {"tenant_id": "incomplete-tenant", "type": "cloudwatch"}
        response = post_json(client, "/api/v1/tenants/incomplete-tenant/delivery-configs", incomplete_data)
        assert response.status_code == 422
        error_details = str(response.json()["detail"])
        assert any(f in error_details for f in ["log_distribution_role_arn", "log_group_name"])

    def test_post_missing_body_hash_header_returns_400(self, client):
        """POST without X-Body-SHA256 header must be rejected by middleware."""
        response = client.post(
            "/api/v1/tenants/test-tenant/delivery-configs",
            json={"tenant_id": "test-tenant", "type": "cloudwatch"}
        )
        assert response.status_code == 400
        assert "X-Body-SHA256" in response.json()["error"]
