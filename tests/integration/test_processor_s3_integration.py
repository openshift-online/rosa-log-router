"""
True End-to-End S3 Processor Integration Tests

These tests validate the complete logging pipeline from log generation through S3 delivery
using real infrastructure components: Vector -> MinIO -> Processor -> MinIO destination buckets.
All operations are performed against real services running in minikube.
"""

import pytest
import json
import gzip
import time
import boto3
import requests
from typing import Dict, Any, Generator
from datetime import datetime

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestEndToEndS3ProcessorIntegration:
    """True end-to-end integration tests with real infrastructure"""
    
    @pytest.fixture
    def minio_client(self):
        """Create MinIO client for integration testing"""
        return boto3.client(
            's3',
            endpoint_url='http://localhost:9000',  # MinIO endpoint via port-forward
            aws_access_key_id='minioadmin',
            aws_secret_access_key='minioadmin',
            region_name='us-east-1'
        )
    
    @pytest.fixture
    def api_client(self):
        """Create API client for tenant configuration"""
        class APIClient:
            def __init__(self):
                self.base_url = "http://localhost:8080"  # API endpoint via port-forward
                self.headers = {"Authorization": "Bearer integration-test-key"}
            
            def create_tenant_config(self, tenant_id: str, config: Dict[str, Any]):
                response = requests.post(
                    f"{self.base_url}/tenant/{tenant_id}/config",
                    json=config,
                    headers=self.headers
                )
                response.raise_for_status()
                return response.json()
            
            def get_tenant_config(self, tenant_id: str, config_type: str):
                response = requests.get(
                    f"{self.base_url}/tenant/{tenant_id}/config/{config_type}",
                    headers=self.headers
                )
                response.raise_for_status()
                return response.json()
            
            def list_tenant_configs(self, tenant_id: str):
                response = requests.get(
                    f"{self.base_url}/tenant/{tenant_id}/configs",
                    headers=self.headers
                )
                response.raise_for_status()
                return response.json()
            
            def delete_tenant_config(self, tenant_id: str, config_type: str):
                response = requests.delete(
                    f"{self.base_url}/tenant/{tenant_id}/config/{config_type}",
                    headers=self.headers
                )
                if response.status_code == 404:
                    return None  # Configuration doesn't exist, which is fine
                response.raise_for_status()
                return response.json()
            
            def cleanup_tenant_configs(self, tenant_id: str):
                """Clean up all configurations for a tenant"""
                try:
                    configs = self.list_tenant_configs(tenant_id)
                    for config in configs:
                        self.delete_tenant_config(tenant_id, config['type'])
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        pass  # No configs exist, which is fine
                    else:
                        raise
        
        return APIClient()
    
    def wait_for_s3_objects(self, minio_client, bucket: str, prefix: str = "", min_objects: int = 1, timeout: int = 120):
        """Wait for S3 objects to appear in bucket"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = minio_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
                objects = response.get('Contents', [])
                if len(objects) >= min_objects:
                    return objects
                time.sleep(5)
            except Exception as e:
                print(f"Error checking bucket {bucket}: {e}")
                time.sleep(5)
        
        raise TimeoutError(f"Timed out waiting for {min_objects} objects in bucket {bucket} with prefix {prefix}")
    
    def test_basic_s3_delivery_end_to_end(self, minio_client, api_client):
        """Test complete S3 delivery pipeline with real infrastructure"""
        
        # Step 0: Clean up any existing configurations
        tenant_id = "e2e-test-tenant"
        api_client.cleanup_tenant_configs(tenant_id)
        
        # Step 1: Create S3 delivery configuration via API
        s3_config = {
            "tenant_id": tenant_id,
            "type": "s3",
            "bucket_name": "customer-logs",
            "bucket_prefix": "e2e-logs/",
            "target_region": "us-east-1",
            "enabled": True,
            "desired_logs": ["fake-log-generator"]
        }
        
        print(f"Creating S3 delivery configuration for {tenant_id}")
        created_config = api_client.create_tenant_config(tenant_id, s3_config)
        assert created_config["tenant_id"] == tenant_id
        assert created_config["type"] == "s3"
        
        # Step 2: Verify configuration can be retrieved
        retrieved_config = api_client.get_tenant_config(tenant_id, "s3")
        assert retrieved_config["bucket_name"] == "customer-logs"
        assert retrieved_config["enabled"] is True
        
        # Step 3: Create a fake log file in source bucket to simulate Vector collection
        source_bucket = "test-logs"
        log_content = [
            {"timestamp": datetime.now().isoformat(), "message": "E2E test log 1", "level": "INFO"},
            {"timestamp": datetime.now().isoformat(), "message": "E2E test log 2", "level": "DEBUG"}
        ]
        
        # Create NDJSON content (Vector format)
        ndjson_content = '\n'.join(json.dumps(log) for log in log_content)
        compressed_content = gzip.compress(ndjson_content.encode('utf-8'))
        
        # Upload to source bucket with proper key structure
        object_key = f"test-cluster/{tenant_id}/fake-log-generator/fake-log-generator-pod-123/20241201-e2e-test.json.gz"
        
        print(f"Uploading test log file to source bucket: {object_key}")
        minio_client.put_object(
            Bucket=source_bucket,
            Key=object_key,
            Body=compressed_content,
            ContentType='application/gzip'
        )
        
        # Step 4: Wait for processor to detect and copy the file
        print("Waiting for log processor to detect and copy the file...")
        destination_objects = self.wait_for_s3_objects(
            minio_client, 
            "customer-logs", 
            prefix="e2e-logs/test-cluster",
            min_objects=1,
            timeout=180  # 3 minutes for processor to run
        )
        
        # Step 5: Verify S3-to-S3 copy occurred with correct structure
        assert len(destination_objects) >= 1, "No objects found in destination bucket"
        
        copied_object = destination_objects[0]
        # Verify the basic prefix pattern (allow dynamic pod names from real Vector logs)
        expected_key_pattern = f"e2e-logs/test-cluster/{tenant_id}/fake-log-generator/"
        assert copied_object['Key'].startswith(expected_key_pattern), f"Object key {copied_object['Key']} doesn't match expected pattern {expected_key_pattern}"
        
        # Step 6: Verify copied file content and metadata
        print(f"Verifying copied file: {copied_object['Key']}")
        copied_response = minio_client.get_object(Bucket="customer-logs", Key=copied_object['Key'])
        copied_metadata = copied_response.get('Metadata', {})
        
        # Check metadata was preserved
        assert copied_metadata.get('tenant-id') == tenant_id
        assert copied_metadata.get('cluster-id') == 'test-cluster'
        assert copied_metadata.get('application') == 'fake-log-generator'
        assert 'delivery-timestamp' in copied_metadata
        
        print(f"✅ End-to-end S3 delivery test completed successfully")
        print(f"   Source: s3://{source_bucket}/{object_key}")
        print(f"   Destination: s3://customer-logs/{copied_object['Key']}")
        print(f"   Metadata: {copied_metadata}")
    
    def test_multi_delivery_configuration(self, minio_client, api_client):
        """Test tenant with both CloudWatch and S3 delivery configurations"""
        
        tenant_id = "multi-delivery-tenant"
        api_client.cleanup_tenant_configs(tenant_id)
        
        # Create CloudWatch configuration
        cloudwatch_config = {
            "tenant_id": tenant_id,
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/CustomerCWRole",
            "log_group_name": "/aws/logs/multi-delivery-tenant",
            "target_region": "us-east-1",
            "enabled": True
        }
        
        # Create S3 configuration  
        s3_config = {
            "tenant_id": tenant_id,
            "type": "s3",
            "bucket_name": "multi-delivery-bucket",
            "bucket_prefix": "multi-logs/",
            "target_region": "us-east-1", 
            "enabled": True
        }
        
        print(f"Creating multi-delivery configurations for {tenant_id}")
        api_client.create_tenant_config(tenant_id, cloudwatch_config)
        api_client.create_tenant_config(tenant_id, s3_config)
        
        # Verify both configurations exist
        configs = api_client.list_tenant_configs(tenant_id)
        assert len(configs) == 2
        config_types = [c['type'] for c in configs]
        assert 'cloudwatch' in config_types
        assert 's3' in config_types
        
        # Create test log file
        log_content = [{"timestamp": datetime.now().isoformat(), "message": "Multi-delivery test log"}]
        ndjson_content = '\n'.join(json.dumps(log) for log in log_content)
        compressed_content = gzip.compress(ndjson_content.encode('utf-8'))
        
        object_key = f"test-cluster/{tenant_id}/fake-log-generator/multi-pod-456/20241201-multi-test.json.gz"
        
        print(f"Uploading test log file: {object_key}")
        minio_client.put_object(
            Bucket="test-logs",
            Key=object_key,
            Body=compressed_content
        )
        
        # Wait for S3 delivery (CloudWatch would fail due to mocked ARN but S3 should work)
        print("Waiting for S3 delivery to complete...")
        destination_objects = self.wait_for_s3_objects(
            minio_client,
            "multi-delivery-bucket",
            prefix="multi-logs/test-cluster",
            min_objects=1,
            timeout=180
        )
        
        assert len(destination_objects) >= 1
        copied_object = destination_objects[0]
        # Verify the basic prefix pattern (allow dynamic pod names from real Vector logs)
        expected_pattern = f"multi-logs/test-cluster/{tenant_id}/fake-log-generator/"
        assert expected_pattern in copied_object['Key'], f"Expected pattern {expected_pattern} not found in {copied_object['Key']}"
        
        print(f"✅ Multi-delivery configuration test completed")
        print(f"   S3 delivery successful: s3://multi-delivery-bucket/{copied_object['Key']}")
    
    def test_desired_logs_filtering(self, minio_client, api_client):
        """Test S3 delivery with desired_logs filtering"""
        
        tenant_id = "filtered-tenant"
        api_client.cleanup_tenant_configs(tenant_id)
        
        # Create S3 configuration that BLOCKS fake-log-generator (all pods use this app label)
        s3_config = {
            "tenant_id": tenant_id,
            "type": "s3",
            "bucket_name": "customer-logs",
            "bucket_prefix": "filtered-logs/",
            "target_region": "us-east-1",
            "enabled": True,
            "desired_logs": ["some-other-app"]  # Block fake-log-generator by not including it
        }
        
        print(f"Creating filtered S3 configuration for {tenant_id}")
        api_client.create_tenant_config(tenant_id, s3_config)
        
        # Test: Verify NO logs are delivered (fake-log-generator is not in desired_logs)
        print("Waiting to verify filtered tenant logs are NOT delivered...")
        time.sleep(30)  # Give processor time to potentially process logs
        
        try:
            # Check for any logs from fake-log-generator (should be blocked by desired_logs filter)
            blocked_objects = self.wait_for_s3_objects(
                minio_client,
                "customer-logs", 
                prefix=f"filtered-logs/test-cluster/{tenant_id}/fake-log-generator",
                min_objects=1,
                timeout=10  # Short timeout since we expect it to fail
            )
            assert False, f"Filtered application logs were unexpectedly delivered: {blocked_objects}"
        except TimeoutError:
            # This is expected - filtered application should not be delivered
            pass
        
        print(f"✅ Desired logs filtering test completed")
        print(f"   fake-log-generator application correctly filtered out (not in desired_logs)")
    
    def test_disabled_tenant_configuration(self, minio_client, api_client):
        """Test S3 delivery with disabled tenant configuration"""
        
        tenant_id = "disabled-tenant"
        api_client.cleanup_tenant_configs(tenant_id)
        
        # Create disabled S3 configuration
        s3_config = {
            "tenant_id": tenant_id,
            "type": "s3",
            "bucket_name": "customer-logs",
            "bucket_prefix": "disabled-logs/",
            "target_region": "us-east-1",
            "enabled": False,  # Disabled
            "desired_logs": ["test-app"]
        }
        
        print(f"Creating disabled S3 configuration for {tenant_id}")
        api_client.create_tenant_config(tenant_id, s3_config)
        
        # Create test log file
        log_content = [{
            "timestamp": datetime.now().isoformat(), 
            "message": "Disabled tenant test log", 
            "level": "INFO"
        }]
        ndjson_content = '\\n'.join(json.dumps(log) for log in log_content)
        compressed_content = gzip.compress(ndjson_content.encode('utf-8'))
        
        object_key = f"test-cluster/{tenant_id}/test-app/test-pod-123/20241201-disabled-test.json.gz"
        
        print(f"Uploading test log file: {object_key}")
        minio_client.put_object(
            Bucket="test-logs",
            Key=object_key,
            Body=compressed_content
        )
        
        # Wait and verify it's NOT delivered (tenant disabled)
        print("Waiting to verify disabled tenant is not processed...")
        time.sleep(30)  # Give processor time to potentially process it
        
        try:
            disabled_objects = self.wait_for_s3_objects(
                minio_client,
                "customer-logs",
                prefix=f"disabled-logs/test-cluster/{tenant_id}",
                min_objects=1,
                timeout=10  # Short timeout since we expect it to fail
            )
            assert False, f"Disabled tenant log was unexpectedly delivered: {disabled_objects}"
        except TimeoutError:
            # This is expected - disabled tenant should not be processed
            pass
        
        print(f"✅ Disabled tenant configuration test completed")
        print(f"   Disabled tenant correctly not processed")
    
    def test_cross_region_s3_delivery(self, minio_client, api_client):
        """Test S3 delivery configuration with different target region"""
        
        tenant_id = "cross-region-tenant"
        api_client.cleanup_tenant_configs(tenant_id)
        
        # Create S3 configuration targeting different region
        s3_config = {
            "tenant_id": tenant_id,
            "type": "s3", 
            "bucket_name": "customer-logs",
            "bucket_prefix": "eu-west-logs/",
            "target_region": "eu-west-1",  # Different region
            "enabled": True,
            "desired_logs": ["global-service"]
        }
        
        print(f"Creating cross-region S3 configuration for {tenant_id}")
        api_client.create_tenant_config(tenant_id, s3_config)
        
        # Create test log file
        log_content = [{
            "timestamp": datetime.now().isoformat(),
            "message": "Cross-region delivery test log",
            "level": "INFO",
            "service": "global-service"
        }]
        ndjson_content = '\\n'.join(json.dumps(log) for log in log_content)
        compressed_content = gzip.compress(ndjson_content.encode('utf-8'))
        
        object_key = f"test-cluster/{tenant_id}/global-service/global-pod-789/20241201-cross-region-test.json.gz"
        
        print(f"Uploading test log file: {object_key}")
        minio_client.put_object(
            Bucket="test-logs",
            Key=object_key,
            Body=compressed_content
        )
        
        # Wait for processor to detect and copy the file
        print("Waiting for cross-region log processor to detect and copy the file...")
        destination_objects = self.wait_for_s3_objects(
            minio_client,
            "customer-logs",
            prefix="eu-west-logs/test-cluster",
            min_objects=1,
            timeout=180
        )
        
        # Verify delivery occurred
        assert len(destination_objects) >= 1
        copied_object = destination_objects[0]
        expected_key_pattern = f"eu-west-logs/test-cluster/{tenant_id}/global-service/global-pod-789/"
        assert copied_object['Key'].startswith(expected_key_pattern)
        
        # Verify metadata
        copied_response = minio_client.get_object(Bucket="customer-logs", Key=copied_object['Key'])
        copied_metadata = copied_response.get('Metadata', {})
        
        assert copied_metadata.get('tenant-id') == tenant_id
        assert copied_metadata.get('cluster-id') == 'test-cluster'
        assert copied_metadata.get('application') == 'global-service'
        
        print(f"✅ Cross-region S3 delivery test completed")
        print(f"   Delivered: s3://customer-logs/{copied_object['Key']}")
        print(f"   Target region: eu-west-1")
        print(f"   Metadata: {copied_metadata}")


@pytest.fixture
def integration_s3_tenant_configs() -> list[Dict[str, Any]]:
    """S3-specific tenant configurations for integration testing"""
    return [
        # S3-only tenant
        {
            "tenant_id": "s3-only-tenant",
            "type": "s3",
            "bucket_name": "s3-only-logs",
            "bucket_prefix": "cluster-logs/",
            "target_region": "us-east-1",
            "enabled": True,
            "desired_logs": ["web-service", "api-service"]
        },
        # Multi-region S3 tenant
        {
            "tenant_id": "multi-region-tenant",
            "type": "s3",
            "bucket_name": "eu-multi-region-logs",
            "bucket_prefix": "eu-logs/",
            "target_region": "eu-west-1",
            "enabled": True
        },
        # S3 tenant with custom prefix
        {
            "tenant_id": "custom-prefix-tenant",
            "type": "s3",
            "bucket_name": "custom-logs-bucket",
            "bucket_prefix": "custom/tenant/logs/path/",
            "target_region": "us-west-2",
            "enabled": True
        }
    ]


@pytest.fixture
def populated_s3_integration_table(delivery_config_service, integration_s3_tenant_configs):
    """A delivery config service with pre-populated S3 integration test data"""
    for config in integration_s3_tenant_configs:
        delivery_config_service.create_tenant_config(config)
    return delivery_config_service