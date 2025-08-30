"""
API Integration Tests with DynamoDB Local

These tests validate the API endpoints against a real DynamoDB Local instance
running in Minikube, providing end-to-end validation of the tenant management API.
"""

import pytest
import json
from typing import Dict, Any

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestTenantServiceIntegration:
    """Integration tests for TenantService with real DynamoDB Local"""
    
    def test_tenant_crud_operations(self, tenant_service, sample_integration_tenant):
        """Test complete CRUD operations with real DynamoDB"""
        tenant_data = sample_integration_tenant
        tenant_id = tenant_data["tenant_id"]
        
        # CREATE: Create tenant
        created = tenant_service.create_tenant(tenant_data)
        assert created["tenant_id"] == tenant_id
        assert created["enabled"] is True
        assert created["log_distribution_role_arn"] == tenant_data["log_distribution_role_arn"]
        
        # READ: Get tenant
        retrieved = tenant_service.get_tenant(tenant_id)
        assert retrieved["tenant_id"] == tenant_id
        assert retrieved["log_group_name"] == tenant_data["log_group_name"]
        assert retrieved["target_region"] == tenant_data["target_region"]
        assert retrieved["desired_logs"] == tenant_data["desired_logs"]
        
        # UPDATE: Modify tenant
        update_data = {
            "log_group_name": "/aws/logs/updated-integration-tenant",
            "enabled": False,
            "desired_logs": ["updated-app"]
        }
        updated = tenant_service.update_tenant(tenant_id, update_data)
        assert updated["log_group_name"] == "/aws/logs/updated-integration-tenant"
        assert updated["enabled"] is False
        assert updated["desired_logs"] == ["updated-app"]
        # Unchanged fields should persist
        assert updated["log_distribution_role_arn"] == tenant_data["log_distribution_role_arn"]
        assert updated["target_region"] == tenant_data["target_region"]
        
        # DELETE: Remove tenant
        deleted = tenant_service.delete_tenant(tenant_id)
        assert deleted is True
        
        # Verify deletion
        from src.services.dynamo import TenantNotFoundError
        with pytest.raises(TenantNotFoundError):
            tenant_service.get_tenant(tenant_id)
    
    def test_tenant_list_operations(self, populated_integration_table):
        """Test tenant listing operations with real DynamoDB"""
        tenant_service = populated_integration_table
        
        # List all tenants
        result = tenant_service.list_tenants()
        assert result["count"] == 3
        assert len(result["tenants"]) == 3
        assert result["limit"] == 50
        
        # Verify all test tenants are present
        tenant_ids = [t["tenant_id"] for t in result["tenants"]]
        assert "integration-tenant-1" in tenant_ids
        assert "integration-tenant-2" in tenant_ids
        assert "integration-tenant-3" in tenant_ids
        
        # Test limited listing
        limited_result = tenant_service.list_tenants(limit=2)
        assert limited_result["count"] == 2
        assert len(limited_result["tenants"]) == 2
        assert limited_result["limit"] == 2
        assert "last_key" in limited_result
    
    def test_tenant_validation_integration(self, tenant_service):
        """Test tenant configuration validation with real DynamoDB"""
        # Create tenant with invalid configuration
        invalid_tenant = {
            "tenant_id": "invalid-integration-tenant",
            "log_distribution_role_arn": "invalid-arn-format",
            "log_group_name": "",  # Empty required field
            "target_region": "invalid-region!"
        }
        tenant_service.create_tenant(invalid_tenant)
        
        # Validate configuration
        validation_result = tenant_service.validate_tenant_config("invalid-integration-tenant")
        
        assert validation_result["tenant_id"] == "invalid-integration-tenant"
        assert validation_result["valid"] is False
        assert len(validation_result["checks"]) > 0
        
        # Check for specific validation failures
        check_results = {check["field"]: check for check in validation_result["checks"]}
        
        # Role ARN should be invalid
        assert "log_distribution_role_arn" in check_results
        arn_check = check_results["log_distribution_role_arn"]
        assert arn_check["status"] == "invalid"
        assert "invalid" in arn_check["message"].lower()
        
        # Log group name should be missing/empty
        assert "log_group_name" in check_results
        group_check = check_results["log_group_name"]
        assert group_check["status"] == "missing"
        
        # Target region should be invalid
        assert "target_region" in check_results
        region_check = check_results["target_region"]
        assert region_check["status"] == "invalid"
    
    def test_concurrent_operations(self, tenant_service, sample_integration_tenant):
        """Test concurrent operations with real DynamoDB"""
        import threading
        import time
        
        base_tenant = sample_integration_tenant.copy()
        results = {}
        errors = {}
        
        def create_tenant_worker(tenant_suffix: str):
            try:
                tenant_data = base_tenant.copy()
                tenant_data["tenant_id"] = f"concurrent-tenant-{tenant_suffix}"
                tenant_data["log_group_name"] = f"/aws/logs/concurrent-tenant-{tenant_suffix}"
                
                result = tenant_service.create_tenant(tenant_data)
                results[tenant_suffix] = result
            except Exception as e:
                errors[tenant_suffix] = str(e)
        
        # Create multiple tenants concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_tenant_worker, args=(str(i),))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify results
        assert len(errors) == 0, f"Concurrent operations failed: {errors}"
        assert len(results) == 5
        
        # Verify all tenants were created successfully
        for i in range(5):
            tenant_id = f"concurrent-tenant-{i}"
            assert str(i) in results
            assert results[str(i)]["tenant_id"] == tenant_id
            
            # Verify tenant exists in DynamoDB
            retrieved = tenant_service.get_tenant(tenant_id)
            assert retrieved["tenant_id"] == tenant_id
    
    def test_error_handling_integration(self, tenant_service, sample_integration_tenant):
        """Test error handling with real DynamoDB responses"""
        from src.services.dynamo import TenantNotFoundError, DynamoDBError
        
        # Test tenant not found
        with pytest.raises(TenantNotFoundError) as exc_info:
            tenant_service.get_tenant("nonexistent-integration-tenant")
        assert "not found" in str(exc_info.value).lower()
        
        # Test duplicate tenant creation
        tenant_service.create_tenant(sample_integration_tenant)
        
        with pytest.raises(DynamoDBError) as exc_info:
            tenant_service.create_tenant(sample_integration_tenant)
        assert "already exists" in str(exc_info.value).lower()
        
        # Test update non-existent tenant
        with pytest.raises(TenantNotFoundError):
            tenant_service.update_tenant("nonexistent-tenant", {"enabled": False})
        
        # Test delete non-existent tenant
        with pytest.raises(TenantNotFoundError):
            tenant_service.delete_tenant("nonexistent-tenant")
    
    def test_large_data_operations(self, tenant_service):
        """Test operations with larger datasets"""
        # Create many tenants
        tenant_count = 25
        created_tenants = []
        
        for i in range(tenant_count):
            tenant_data = {
                "tenant_id": f"bulk-tenant-{i:03d}",
                "log_distribution_role_arn": f"arn:aws:iam::123456789012:role/BulkRole{i}",
                "log_group_name": f"/aws/logs/bulk-tenant-{i:03d}",
                "target_region": "us-east-1",
                "enabled": i % 2 == 0,  # Alternate enabled/disabled
                "desired_logs": [f"app-{i}", f"service-{i}"]
            }
            
            result = tenant_service.create_tenant(tenant_data)
            created_tenants.append(result["tenant_id"])
        
        assert len(created_tenants) == tenant_count
        
        # Test paginated listing
        all_tenants = []
        last_key = None
        page_size = 10
        
        while True:
            if last_key:
                result = tenant_service.list_tenants(limit=page_size, last_key=last_key)
            else:
                result = tenant_service.list_tenants(limit=page_size)
            
            all_tenants.extend(result["tenants"])
            
            if "last_key" not in result:
                break
            last_key = result["last_key"]
        
        # Verify we got all created tenants (plus any from other tests)
        bulk_tenant_ids = [t["tenant_id"] for t in all_tenants if t["tenant_id"].startswith("bulk-tenant-")]
        assert len(bulk_tenant_ids) == tenant_count
        
        # Verify pagination worked correctly
        assert len(all_tenants) >= tenant_count


class TestDynamoDBLocalConnection:
    """Test DynamoDB Local connection and basic operations"""
    
    def test_connection_and_table_operations(self, dynamodb_local_client, dynamodb_local_resource):
        """Test basic DynamoDB Local connectivity and operations"""
        # Test client connectivity
        response = dynamodb_local_client.list_tables()
        assert "TableNames" in response
        
        # Test table creation via resource
        test_table_name = "integration-test-table"
        table = dynamodb_local_resource.create_table(
            TableName=test_table_name,
            KeySchema=[
                {"AttributeName": "id", "KeyType": "HASH"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST"
        )
        
        # Wait for table to be active
        table.wait_until_exists()
        
        # Test item operations
        table.put_item(Item={"id": "test-item", "data": "test-value"})
        
        response = table.get_item(Key={"id": "test-item"})
        assert "Item" in response
        assert response["Item"]["data"] == "test-value"
        
        # Test table listing
        tables = dynamodb_local_client.list_tables()
        assert test_table_name in tables["TableNames"]
        
        # Cleanup
        table.delete()
    
    def test_dynamodb_local_persistence(self, dynamodb_local_resource):
        """Test data persistence within test session"""
        # Create table and add data
        table_name = "persistence-test-table"
        table = dynamodb_local_resource.create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST"
        )
        table.wait_until_exists()
        
        # Add test items
        test_items = [
            {"pk": "item1", "value": "value1"},
            {"pk": "item2", "value": "value2"},
            {"pk": "item3", "value": "value3"}
        ]
        
        for item in test_items:
            table.put_item(Item=item)
        
        # Verify all items exist
        for item in test_items:
            response = table.get_item(Key={"pk": item["pk"]})
            assert "Item" in response
            assert response["Item"]["value"] == item["value"]
        
        # Test scan operation
        scan_response = table.scan()
        assert scan_response["Count"] == 3
        
        # Cleanup
        table.delete()