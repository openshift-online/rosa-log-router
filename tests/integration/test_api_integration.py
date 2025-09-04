"""
API Integration Tests with DynamoDB Local

These tests validate the API endpoints against a real DynamoDB Local instance
running in Minikube, providing end-to-end validation of the tenant delivery configuration API.
"""

import pytest
import json
import requests
from typing import Dict, Any

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestTenantDeliveryConfigAPIIntegration:
    """Integration tests for Tenant Delivery Configuration API with real deployed API service"""
    
    def test_delivery_config_crud_operations(self, api_client, tenant_config_table, sample_integration_cloudwatch_config):
        """Test complete CRUD operations via API endpoints"""
        config_data = sample_integration_cloudwatch_config
        tenant_id = config_data["tenant_id"]
        delivery_type = config_data["type"]
        
        # CREATE: Create delivery configuration via API
        response = api_client.create_delivery_config(tenant_id, config_data)
        created = response["data"]
        assert response["status"] == "success"
        assert created["tenant_id"] == tenant_id
        assert created["type"] == delivery_type
        assert created["enabled"] is True
        assert created["log_distribution_role_arn"] == config_data["log_distribution_role_arn"]
        
        # READ: Get delivery configuration via API
        response = api_client.get_delivery_config(tenant_id, delivery_type)
        retrieved = response["data"]
        assert response["status"] == "success"
        assert retrieved["tenant_id"] == tenant_id
        assert retrieved["type"] == delivery_type
        assert retrieved["log_group_name"] == config_data["log_group_name"]
        assert retrieved["target_region"] == config_data["target_region"]
        assert retrieved["desired_logs"] == config_data["desired_logs"]
        
        # UPDATE: Modify delivery configuration via API
        update_data = {
            "log_group_name": "/aws/logs/updated-integration-tenant",
            "enabled": False,
            "desired_logs": ["updated-app"]
        }
        response = api_client.update_delivery_config(tenant_id, delivery_type, update_data)
        updated = response["data"]
        assert response["status"] == "success"
        assert updated["log_group_name"] == "/aws/logs/updated-integration-tenant"
        assert updated["enabled"] is False
        assert updated["desired_logs"] == ["updated-app"]
        # Unchanged fields should persist
        assert updated["log_distribution_role_arn"] == config_data["log_distribution_role_arn"]
        assert updated["target_region"] == config_data["target_region"]
        
        # DELETE: Remove delivery configuration via API
        response = api_client.delete_delivery_config(tenant_id, delivery_type)
        assert response["status"] == "success"
        
        # Verify deletion via API
        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            api_client.get_delivery_config(tenant_id, delivery_type)
        assert exc_info.value.response.status_code == 404
    
    def test_delivery_config_list_operations(self, populated_integration_table):
        """Test delivery configuration listing operations via API"""
        api_client = populated_integration_table
        
        # List all delivery configurations via API
        response = api_client.list_all_delivery_configs()
        result = response["data"]
        assert response["status"] == "success"
        assert result["count"] == 4  # 2 tenants x 2 delivery types each
        assert len(result["configurations"]) == 4
        
        # Verify all test configurations are present
        config_keys = [(c["tenant_id"], c["type"]) for c in result["configurations"]]
        assert ("integration-tenant-1", "cloudwatch") in config_keys
        assert ("integration-tenant-1", "s3") in config_keys
        assert ("integration-tenant-2", "cloudwatch") in config_keys
        assert ("integration-tenant-2", "s3") in config_keys
        
        # Test limited listing
        limited_response = api_client.list_all_delivery_configs(limit=2)
        limited_result = limited_response["data"]
        assert limited_response["status"] == "success"
        assert limited_result["count"] == 2
        assert len(limited_result["configurations"]) == 2
        
        # Test tenant-specific listing
        tenant_response = api_client.list_tenant_delivery_configs("integration-tenant-1")
        tenant_result = tenant_response["data"]
        assert tenant_response["status"] == "success"
        assert len(tenant_result["configurations"]) == 2
        tenant_types = [c["type"] for c in tenant_result["configurations"]]
        assert "cloudwatch" in tenant_types
        assert "s3" in tenant_types
    
    def test_delivery_config_validation_integration(self, api_client, tenant_config_table):
        """Test delivery configuration validation via API"""
        # Create delivery configuration with invalid configuration via API
        invalid_config = {
            "tenant_id": "invalid-integration-tenant",
            "type": "cloudwatch",
            "log_distribution_role_arn": "invalid-arn-format",
            "log_group_name": "",  # Empty required field
            "target_region": "invalid-region!"
        }
        api_client.create_delivery_config("invalid-integration-tenant", invalid_config)
        
        # Validate configuration via API
        response = api_client.validate_delivery_config("invalid-integration-tenant", "cloudwatch")
        validation_result = response["data"]
        
        assert response["status"] == "success"
        assert validation_result["tenant_id"] == "invalid-integration-tenant"
        assert validation_result["type"] == "cloudwatch"
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
    
    def test_concurrent_operations(self, api_client, tenant_config_table, sample_integration_cloudwatch_config):
        """Test concurrent operations via API"""
        import threading
        import time
        
        base_config = sample_integration_cloudwatch_config.copy()
        results = {}
        errors = {}
        
        def create_config_worker(config_suffix: str):
            try:
                config_data = base_config.copy()
                config_data["tenant_id"] = f"concurrent-tenant-{config_suffix}"
                config_data["log_group_name"] = f"/aws/logs/concurrent-tenant-{config_suffix}"
                
                response = api_client.create_delivery_config(f"concurrent-tenant-{config_suffix}", config_data)
                results[config_suffix] = response["data"]
            except Exception as e:
                errors[config_suffix] = str(e)
        
        # Create multiple delivery configurations concurrently via API
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_config_worker, args=(str(i),))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify results
        assert len(errors) == 0, f"Concurrent operations failed: {errors}"
        assert len(results) == 5
        
        # Verify all delivery configurations were created successfully via API
        for i in range(5):
            tenant_id = f"concurrent-tenant-{i}"
            delivery_type = "cloudwatch"
            assert str(i) in results
            assert results[str(i)]["tenant_id"] == tenant_id
            
            # Verify delivery configuration exists via API
            response = api_client.get_delivery_config(tenant_id, delivery_type)
            retrieved = response["data"]
            assert retrieved["tenant_id"] == tenant_id
            assert retrieved["type"] == delivery_type
    
    def test_error_handling_integration(self, api_client, tenant_config_table, sample_integration_cloudwatch_config):
        """Test error handling with real API responses"""
        # Test delivery configuration not found
        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            api_client.get_delivery_config("nonexistent-integration-tenant", "cloudwatch")
        assert exc_info.value.response.status_code == 404
        
        # Test duplicate delivery configuration creation
        api_client.create_delivery_config(sample_integration_cloudwatch_config["tenant_id"], sample_integration_cloudwatch_config)
        
        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            api_client.create_delivery_config(sample_integration_cloudwatch_config["tenant_id"], sample_integration_cloudwatch_config)
        assert exc_info.value.response.status_code == 409  # Conflict
        
        # Test update non-existent delivery configuration
        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            api_client.update_delivery_config("nonexistent-tenant", "cloudwatch", {"enabled": False})
        assert exc_info.value.response.status_code == 404
        
        # Test delete non-existent delivery configuration
        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            api_client.delete_delivery_config("nonexistent-tenant", "cloudwatch")
        assert exc_info.value.response.status_code == 404
    
    def test_large_data_operations(self, api_client):
        """Test operations with larger datasets via API"""
        # Create many delivery configurations (both cloudwatch and s3 for each tenant)
        tenant_count = 12
        created_configs = []
        
        for i in range(tenant_count):
            # Create CloudWatch delivery configuration
            cloudwatch_config = {
                "tenant_id": f"bulk-tenant-{i:03d}",
                "type": "cloudwatch",
                "log_distribution_role_arn": f"arn:aws:iam::123456789012:role/BulkRole{i}",
                "log_group_name": f"/aws/logs/bulk-tenant-{i:03d}",
                "target_region": "us-east-1",
                "enabled": i % 2 == 0,  # Alternate enabled/disabled
                "desired_logs": [f"app-{i}", f"service-{i}"]
            }
            
            # Create S3 delivery configuration
            s3_config = {
                "tenant_id": f"bulk-tenant-{i:03d}",
                "type": "s3",
                "bucket_name": f"bulk-tenant-{i:03d}-logs",
                "bucket_prefix": "logs/",
                "target_region": "us-east-1",
                "enabled": i % 3 == 0,  # Different pattern for S3
                "desired_logs": [f"app-{i}", f"service-{i}"]
            }
            
            cw_response = api_client.create_delivery_config(f"bulk-tenant-{i:03d}", cloudwatch_config)
            s3_response = api_client.create_delivery_config(f"bulk-tenant-{i:03d}", s3_config)
            created_configs.append((cw_response["data"]["tenant_id"], cw_response["data"]["type"]))
            created_configs.append((s3_response["data"]["tenant_id"], s3_response["data"]["type"]))
        
        assert len(created_configs) == tenant_count * 2  # 2 configs per tenant
        
        # Test paginated listing via API
        all_configs = []
        last_key = None
        page_size = 10
        
        while True:
            result = api_client.list_all_delivery_configs(limit=page_size, last_key=last_key)
            result_data = result["data"]
            
            all_configs.extend(result_data["configurations"])
            
            if "last_key" not in result_data:
                break
            last_key = result_data["last_key"]
        
        # Verify we got all created configurations (plus any from other tests)
        bulk_config_keys = [(c["tenant_id"], c["type"]) for c in all_configs if c["tenant_id"].startswith("bulk-tenant-")]
        assert len(bulk_config_keys) == tenant_count * 2
        
        # Verify pagination worked correctly
        assert len(all_configs) >= tenant_count * 2


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