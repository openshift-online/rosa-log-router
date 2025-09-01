"""
Unit tests for DynamoDB tenant service
"""

import pytest
from botocore.exceptions import ClientError

# Setup path for importing API modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api/src'))

from src.services.dynamo import TenantDeliveryConfigService, TenantNotFoundError, DynamoDBError


class TestTenantDeliveryConfigService:
    """Test cases for TenantDeliveryConfigService class"""
    
    def test_get_tenant_config_success(self, delivery_config_service, sample_cloudwatch_config):
        """Test successful delivery config retrieval"""
        # Create a delivery config first
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        # Retrieve the config
        result = delivery_config_service.get_tenant_config("test-tenant", "cloudwatch")
        
        assert result["tenant_id"] == "test-tenant"
        assert result["type"] == "cloudwatch"
        assert result["log_distribution_role_arn"] == "arn:aws:iam::123456789012:role/TestRole"
        assert result["log_group_name"] == "/aws/logs/test-tenant"
        assert result["target_region"] == "us-east-1"
        assert result["enabled"] is True
        assert result["desired_logs"] == ["app1", "app2"]
    
    def test_get_tenant_config_not_found(self, delivery_config_service):
        """Test delivery config retrieval when config doesn't exist"""
        with pytest.raises(TenantNotFoundError, match="Tenant 'nonexistent' delivery configuration 'cloudwatch' not found"):
            delivery_config_service.get_tenant_config("nonexistent", "cloudwatch")
    
    def test_create_tenant_config_success(self, delivery_config_service, sample_cloudwatch_config):
        """Test successful delivery config creation"""
        result = delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        assert result["tenant_id"] == "test-tenant"
        assert result["type"] == "cloudwatch"
        assert result["enabled"] is True  # Default value should be set
        
        # Verify config was actually created
        retrieved = delivery_config_service.get_tenant_config("test-tenant", "cloudwatch")
        assert retrieved["tenant_id"] == "test-tenant"
        assert retrieved["type"] == "cloudwatch"
    
    def test_create_s3_config_success(self, delivery_config_service, sample_s3_config):
        """Test successful S3 delivery config creation"""
        result = delivery_config_service.create_tenant_config(sample_s3_config)
        
        assert result["tenant_id"] == "test-tenant"
        assert result["type"] == "s3"
        assert result["bucket_name"] == "test-bucket"
        assert result["bucket_prefix"] == "ROSA/cluster-logs/"
        assert result["enabled"] is True  # Should default to True
        assert "desired_logs" not in result or result["desired_logs"] is None
    
    def test_create_tenant_config_duplicate(self, delivery_config_service, sample_cloudwatch_config):
        """Test delivery config creation with duplicate tenant_id/type"""
        # Create config first time
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        # Try to create again - should fail
        with pytest.raises(DynamoDBError, match="already exists"):
            delivery_config_service.create_tenant_config(sample_cloudwatch_config)
    
    def test_update_tenant_config_success(self, delivery_config_service, sample_cloudwatch_config):
        """Test successful delivery config update"""
        # Create config first
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        # Update config
        update_data = {
            "log_group_name": "/aws/logs/updated-tenant",
            "enabled": False,
            "desired_logs": ["new-app"]
        }
        
        result = delivery_config_service.update_tenant_config("test-tenant", "cloudwatch", update_data)
        
        assert result["tenant_id"] == "test-tenant"
        assert result["type"] == "cloudwatch"
        assert result["log_group_name"] == "/aws/logs/updated-tenant"
        assert result["enabled"] is False
        assert result["desired_logs"] == ["new-app"]
        # Other fields should remain unchanged
        assert result["log_distribution_role_arn"] == "arn:aws:iam::123456789012:role/TestRole"
    
    def test_update_tenant_config_not_found(self, delivery_config_service):
        """Test delivery config update when config doesn't exist"""
        update_data = {"enabled": False}
        
        with pytest.raises(TenantNotFoundError, match="Tenant 'nonexistent' delivery configuration 'cloudwatch' not found"):
            delivery_config_service.update_tenant_config("nonexistent", "cloudwatch", update_data)
    
    def test_update_tenant_config_no_fields(self, delivery_config_service, sample_cloudwatch_config):
        """Test delivery config update with no fields to update (should still update timestamp)"""
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        # Even with empty update data, should succeed because updated_at is always added
        result = delivery_config_service.update_tenant_config("test-tenant", "cloudwatch", {})
        
        assert result["tenant_id"] == "test-tenant"
        assert result["type"] == "cloudwatch"
        assert "updated_at" in result
    
    def test_patch_tenant_config_success(self, delivery_config_service, sample_cloudwatch_config):
        """Test successful delivery config patch (partial update)"""
        # Create config first
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        # Patch config
        patch_data = {"enabled": False}
        
        result = delivery_config_service.patch_tenant_config("test-tenant", "cloudwatch", patch_data)
        
        assert result["tenant_id"] == "test-tenant"
        assert result["type"] == "cloudwatch"
        assert result["enabled"] is False
        # Other fields should remain unchanged
        assert result["log_group_name"] == "/aws/logs/test-tenant"
        assert result["desired_logs"] == ["app1", "app2"]
    
    def test_delete_tenant_config_success(self, delivery_config_service, sample_cloudwatch_config):
        """Test successful delivery config deletion"""
        # Create config first
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        # Delete config
        result = delivery_config_service.delete_tenant_config("test-tenant", "cloudwatch")
        assert result is True
        
        # Verify config is gone
        with pytest.raises(TenantNotFoundError):
            delivery_config_service.get_tenant_config("test-tenant", "cloudwatch")
    
    def test_delete_tenant_config_not_found(self, delivery_config_service):
        """Test delivery config deletion when config doesn't exist"""
        with pytest.raises(TenantNotFoundError, match="Tenant 'nonexistent' delivery configuration 'cloudwatch' not found"):
            delivery_config_service.delete_tenant_config("nonexistent", "cloudwatch")
    
    def test_get_tenant_configs_success(self, delivery_config_service, sample_cloudwatch_config, sample_s3_config):
        """Test getting all delivery configs for a tenant"""
        # Create both CloudWatch and S3 configs for the same tenant
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        delivery_config_service.create_tenant_config(sample_s3_config)
        
        # Get all configs for the tenant
        result = delivery_config_service.get_tenant_configs("test-tenant")
        
        assert len(result) == 2
        config_types = [config["type"] for config in result]
        assert "cloudwatch" in config_types
        assert "s3" in config_types
    
    def test_get_enabled_tenant_configs(self, delivery_config_service, sample_cloudwatch_config, sample_s3_config):
        """Test getting only enabled delivery configs for a tenant"""
        # Create enabled CloudWatch config
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        # Create disabled S3 config
        sample_s3_config["enabled"] = False
        delivery_config_service.create_tenant_config(sample_s3_config)
        
        # Get enabled configs for the tenant
        result = delivery_config_service.get_enabled_tenant_configs("test-tenant")
        
        assert len(result) == 1
        assert result[0]["type"] == "cloudwatch"
        assert result[0]["enabled"] is True
    
    def test_list_tenant_configs_empty(self, delivery_config_service):
        """Test listing delivery configs when table is empty"""
        result = delivery_config_service.list_tenant_configs()
        
        assert result["configurations"] == []
        assert result["count"] == 0
        assert result["limit"] == 50
        assert "last_key" not in result
    
    def test_validate_tenant_config_valid_cloudwatch(self, delivery_config_service, sample_cloudwatch_config):
        """Test delivery configuration validation for valid CloudWatch config"""
        delivery_config_service.create_tenant_config(sample_cloudwatch_config)
        
        result = delivery_config_service.validate_tenant_config("test-tenant", "cloudwatch")
        
        assert result["tenant_id"] == "test-tenant"
        assert result["type"] == "cloudwatch"
        assert result["valid"] is True
        assert len(result["checks"]) > 0
        
        # Check that required fields are validated
        check_fields = [check["field"] for check in result["checks"]]
        assert "log_distribution_role_arn" in check_fields
        assert "log_group_name" in check_fields
    
    def test_validate_tenant_config_valid_s3(self, delivery_config_service, sample_s3_config):
        """Test delivery configuration validation for valid S3 config"""
        delivery_config_service.create_tenant_config(sample_s3_config)
        
        result = delivery_config_service.validate_tenant_config("test-tenant", "s3")
        
        assert result["tenant_id"] == "test-tenant"
        assert result["type"] == "s3"
        assert result["valid"] is True
        assert len(result["checks"]) > 0
        
        # Check that required fields are validated
        check_fields = [check["field"] for check in result["checks"]]
        assert "bucket_name" in check_fields
    
    def test_validate_tenant_config_invalid_role_arn(self, delivery_config_service):
        """Test delivery configuration validation with invalid role ARN"""
        invalid_config = {
            "tenant_id": "invalid-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "invalid-arn",
            "log_group_name": "/aws/logs/invalid-tenant"
        }
        delivery_config_service.create_tenant_config(invalid_config)
        
        result = delivery_config_service.validate_tenant_config("invalid-tenant", "cloudwatch")
        
        assert result["tenant_id"] == "invalid-tenant"
        assert result["type"] == "cloudwatch"
        assert result["valid"] is False
        
        # Find the role ARN validation check
        role_check = next(
            (check for check in result["checks"] 
             if check["field"] == "log_distribution_role_arn" and check["status"] == "invalid"),
            None
        )
        assert role_check is not None
        assert "invalid" in role_check["message"]
    
    def test_validate_tenant_config_not_found(self, delivery_config_service):
        """Test delivery configuration validation when config doesn't exist"""
        with pytest.raises(TenantNotFoundError, match="Tenant 'nonexistent' delivery configuration 'cloudwatch' not found"):
            delivery_config_service.validate_tenant_config("nonexistent", "cloudwatch")


class TestTenantDeliveryConfigServiceEdgeCases:
    """Test edge cases and error scenarios"""
    
    def test_initialization(self):
        """Test service initialization"""
        service = TenantDeliveryConfigService("test-table", "us-west-2")
        assert service.table_name == "test-table"
        assert service.region == "us-west-2"
    
    def test_initialization_defaults(self):
        """Test service initialization with defaults"""
        service = TenantDeliveryConfigService("test-table")
        assert service.table_name == "test-table"
        assert service.region == "us-east-1"
    
    def test_lazy_initialization(self, delivery_config_service):
        """Test that DynamoDB resources are initialized lazily"""
        # Before accessing properties, should be None
        assert delivery_config_service._dynamodb is None
        assert delivery_config_service._table is None
        
        # After accessing, should be initialized
        _ = delivery_config_service.dynamodb
        assert delivery_config_service._dynamodb is not None
        
        _ = delivery_config_service.table
        assert delivery_config_service._table is not None