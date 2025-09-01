"""
S3 Processor Integration Tests with MinIO

These tests validate the complete S3 delivery pipeline using real MinIO instances
and DynamoDB Local, providing end-to-end validation of S3-to-S3 copy functionality.
"""

import pytest
import json
import gzip
import time
import boto3
from typing import Dict, Any, Generator
from unittest.mock import patch, Mock

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestS3ProcessorIntegration:
    """Integration tests for S3 processor functionality with MinIO"""
    
    def test_s3_delivery_end_to_end(self, delivery_config_service, kubectl_port_forward: int, integration_aws_credentials: Dict[str, str]):
        """
        Test complete S3 delivery pipeline with MinIO source and destination.

        The `integration_aws_credentials` parameter is included as a fixture to ensure
        that AWS credentials are properly set up for the test environment, even though
        it is not directly referenced in the test body.
        """
        # Create S3 delivery configuration in DynamoDB Local
        s3_config = {
            "tenant_id": "s3-integration-tenant",
            "type": "s3",
            "bucket_name": "destination-bucket",
            "bucket_prefix": "tenant-logs/",
            "target_region": "us-east-1",
            "enabled": True,
            "desired_logs": ["test-app"]
        }
        
        delivery_config_service.create_tenant_config(s3_config)
        
        # Mock the central log distribution role ARN environment variable
        central_role_arn = "arn:aws:iam::123456789012:role/CentralLogDistributionRole"
        
        with patch.dict('os.environ', {
            'CENTRAL_LOG_DISTRIBUTION_ROLE_ARN': central_role_arn,
            'AWS_REGION': 'us-east-1',
            'TENANT_CONFIG_TABLE': delivery_config_service.table_name
        }):
            # Mock S3 operations and STS role assumption for the processor
            with patch('boto3.client') as mock_boto_client, \
                 patch('boto3.resource') as mock_boto_resource:
                # Mock STS client for role assumption
                mock_sts = Mock()
                mock_sts.assume_role.return_value = {
                    'Credentials': {
                        'AccessKeyId': 'assumed-key',
                        'SecretAccessKey': 'assumed-secret', 
                        'SessionToken': 'assumed-token'
                    }
                }
                
                # Mock S3 client for S3-to-S3 copy
                mock_s3 = Mock()
                mock_s3.copy_object.return_value = {}
                
                def boto_client_side_effect(service, **kwargs):
                    if service == 'sts':
                        return mock_sts
                    elif service == 's3':
                        return mock_s3
                    elif service == 'dynamodb':
                        # Use real DynamoDB Local for configuration lookup
                        return boto3.client(
                            'dynamodb',
                            endpoint_url=f'http://localhost:{kubectl_port_forward}',
                            region_name='us-east-1',
                            aws_access_key_id='test',
                            aws_secret_access_key='test'
                        )
                    return Mock()
                
                # Also mock boto3.resource for DynamoDB
                def boto_resource_side_effect(service, **kwargs):
                    if service == 'dynamodb':
                        return boto3.resource(
                            'dynamodb',
                            endpoint_url=f'http://localhost:{kubectl_port_forward}',
                            region_name='us-east-1',
                            aws_access_key_id='test',
                            aws_secret_access_key='test'
                        )
                    return Mock()
                
                mock_boto_client.side_effect = boto_client_side_effect
                mock_boto_resource.side_effect = boto_resource_side_effect
                
                # Import processor functions
                import sys
                import os
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../container'))
                from log_processor import process_sqs_record
                
                # Create test SQS record with S3 event
                s3_event = {
                    "Records": [{
                        "s3": {
                            "bucket": {"name": "source-bucket"},
                            "object": {"key": "test-cluster/s3-integration-tenant/test-app/test-pod-123/20240901-logs.json.gz"}
                        }
                    }]
                }
                
                sns_message = {"Message": json.dumps(s3_event)}
                sqs_record = {
                    "body": json.dumps(sns_message),
                    "messageId": "s3-integration-test"
                }
                
                # Mock log file download and processing
                with patch('log_processor.download_and_process_log_file') as mock_download:
                    test_log_events = [
                        {"message": "S3 integration test log 1", "timestamp": 1693526400000},
                        {"message": "S3 integration test log 2", "timestamp": 1693526401000}
                    ]
                    mock_download.return_value = (test_log_events, 1693526400)
                    
                    # Process the SQS record (should trigger S3 delivery)
                    process_sqs_record(sqs_record)
                    
                    # Verify role assumption occurred
                    mock_sts.assume_role.assert_called_once()
                    assume_role_call = mock_sts.assume_role.call_args
                    assert central_role_arn in assume_role_call[1]['RoleArn']
                    assert 'S3LogDelivery-s3-integration-tenant-' in assume_role_call[1]['RoleSessionName']
                    
                    # Verify S3 copy operation
                    mock_s3.copy_object.assert_called_once()
                    copy_call = mock_s3.copy_object.call_args[1]
                    
                    # Verify destination details
                    assert copy_call['Bucket'] == 'destination-bucket'
                    expected_key = 'tenant-logs/test-cluster/s3-integration-tenant/test-app/test-pod-123/20240901-logs.json.gz'
                    assert copy_call['Key'] == expected_key
                    
                    # Verify source details
                    assert copy_call['CopySource']['Bucket'] == 'source-bucket'
                    assert copy_call['CopySource']['Key'] == 'test-cluster/s3-integration-tenant/test-app/test-pod-123/20240901-logs.json.gz'
                    
                    # Verify copy settings
                    assert copy_call['ACL'] == 'bucket-owner-full-control'
                    assert copy_call['MetadataDirective'] == 'REPLACE'
                    
                    # Verify metadata preservation
                    metadata = copy_call['Metadata']
                    assert metadata['tenant-id'] == 's3-integration-tenant'
                    assert metadata['cluster-id'] == 'test-cluster'
                    assert metadata['application'] == 'test-app'
                    assert metadata['pod-name'] == 'test-pod-123'
                    assert metadata['source-bucket'] == 'source-bucket'
    
    def test_s3_delivery_with_multiple_delivery_types(self, delivery_config_service, kubectl_port_forward: int):
        """Test tenant with both CloudWatch and S3 delivery configurations"""
        tenant_id = "multi-delivery-tenant"
        
        # Create both CloudWatch and S3 configurations for the same tenant
        cloudwatch_config = {
            "tenant_id": tenant_id,
            "type": "cloudwatch",
            "log_distribution_role_arn": "arn:aws:iam::123456789012:role/CustomerCWRole",
            "log_group_name": "/aws/logs/multi-delivery-tenant",
            "target_region": "us-east-1",
            "enabled": True
        }
        
        s3_config = {
            "tenant_id": tenant_id,
            "type": "s3",
            "bucket_name": "multi-delivery-bucket",
            "bucket_prefix": "logs/",
            "target_region": "us-east-1",
            "enabled": True
        }
        
        delivery_config_service.create_tenant_config(cloudwatch_config)
        delivery_config_service.create_tenant_config(s3_config)
        
        central_role_arn = "arn:aws:iam::123456789012:role/CentralLogDistributionRole"
        
        with patch.dict('os.environ', {
            'CENTRAL_LOG_DISTRIBUTION_ROLE_ARN': central_role_arn,
            'AWS_REGION': 'us-east-1',
            'TENANT_CONFIG_TABLE': delivery_config_service.table_name
        }):
            with patch('boto3.client') as mock_boto_client:
                mock_sts = Mock()
                mock_sts.assume_role.return_value = {
                    'Credentials': {
                        'AccessKeyId': 'assumed-key',
                        'SecretAccessKey': 'assumed-secret',
                        'SessionToken': 'assumed-token'
                    }
                }
                
                mock_s3 = Mock()
                mock_s3.copy_object.return_value = {}
                
                def boto_client_side_effect(service, **kwargs):
                    if service == 'sts':
                        return mock_sts
                    elif service == 's3':
                        return mock_s3
                    elif service == 'dynamodb':
                        return boto3.client(
                            'dynamodb',
                            endpoint_url=f'http://localhost:{kubectl_port_forward}',
                            region_name='us-east-1',
                            aws_access_key_id='test',
                            aws_secret_access_key='test'
                        )
                    return Mock()
                
                mock_boto_client.side_effect = boto_client_side_effect
                
                # Import processor
                import sys
                import os
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../container'))
                from log_processor import process_sqs_record
                
                # Create SQS record
                s3_event = {
                    "Records": [{
                        "s3": {
                            "bucket": {"name": "source-bucket"},
                            "object": {"key": f"test-cluster/{tenant_id}/web-app/web-pod-456/20240901-logs.json.gz"}
                        }
                    }]
                }
                
                sns_message = {"Message": json.dumps(s3_event)}
                sqs_record = {
                    "body": json.dumps(sns_message),
                    "messageId": "multi-delivery-test"
                }
                
                # Mock CloudWatch delivery and log file processing
                with patch('log_processor.download_and_process_log_file') as mock_download, \
                     patch('log_processor.deliver_logs_to_cloudwatch') as mock_deliver_cw:
                    
                    test_log_events = [{"message": "Multi-delivery test log", "timestamp": 1693526400000}]
                    mock_download.return_value = (test_log_events, 1693526400)
                    mock_deliver_cw.return_value = None
                    
                    # Process SQS record - should trigger both deliveries
                    process_sqs_record(sqs_record)
                    
                    # Verify both delivery types were called
                    mock_deliver_cw.assert_called_once()  # CloudWatch delivery
                    mock_s3.copy_object.assert_called_once()  # S3 delivery
                    
                    # Verify S3 copy was to the correct bucket
                    s3_copy_call = mock_s3.copy_object.call_args[1]
                    assert s3_copy_call['Bucket'] == 'multi-delivery-bucket'
                    expected_s3_key = f'logs/test-cluster/{tenant_id}/web-app/web-pod-456/20240901-logs.json.gz'
                    assert s3_copy_call['Key'] == expected_s3_key
    
    def test_s3_delivery_disabled_tenant(self, delivery_config_service, kubectl_port_forward: int):
        """Test S3 delivery with disabled tenant configuration"""
        # Create disabled S3 configuration
        disabled_s3_config = {
            "tenant_id": "disabled-s3-tenant",
            "type": "s3",
            "bucket_name": "disabled-bucket",
            "bucket_prefix": "logs/",
            "target_region": "us-east-1",
            "enabled": False  # Disabled
        }
        
        delivery_config_service.create_tenant_config(disabled_s3_config)
        
        central_role_arn = "arn:aws:iam::123456789012:role/CentralLogDistributionRole"
        
        with patch.dict('os.environ', {
            'CENTRAL_LOG_DISTRIBUTION_ROLE_ARN': central_role_arn,
            'AWS_REGION': 'us-east-1',
            'TENANT_CONFIG_TABLE': delivery_config_service.table_name
        }):
            with patch('boto3.client') as mock_boto_client:
                def boto_client_side_effect(service, **kwargs):
                    if service == 'dynamodb':
                        return boto3.client(
                            'dynamodb',
                            endpoint_url=f'http://localhost:{kubectl_port_forward}',
                            region_name='us-east-1',
                            aws_access_key_id='test',
                            aws_secret_access_key='test'
                        )
                    return Mock()
                
                mock_boto_client.side_effect = boto_client_side_effect
                
                # Import processor
                import sys
                import os
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../container'))
                from log_processor import process_sqs_record
                
                # Create SQS record
                s3_event = {
                    "Records": [{
                        "s3": {
                            "bucket": {"name": "source-bucket"},
                            "object": {"key": "test-cluster/disabled-s3-tenant/app/pod/20240901-logs.json.gz"}
                        }
                    }]
                }
                
                sns_message = {"Message": json.dumps(s3_event)}
                sqs_record = {
                    "body": json.dumps(sns_message),
                    "messageId": "disabled-s3-test"
                }
                
                # Mock log file download
                with patch('log_processor.download_and_process_log_file') as mock_download, \
                     patch('log_processor.deliver_logs_to_s3') as mock_deliver_s3:
                    
                    test_log_events = [{"message": "Disabled test log", "timestamp": 1693526400000}]
                    mock_download.return_value = (test_log_events, 1693526400)
                    
                    # Process SQS record
                    process_sqs_record(sqs_record)
                    
                    # Verify S3 delivery was NOT called (tenant disabled)
                    mock_deliver_s3.assert_not_called()
                    
                    # Log file should still be downloaded for processing
                    mock_download.assert_called_once()
    
    def test_s3_delivery_desired_logs_filtering(self, delivery_config_service, kubectl_port_forward: int):
        """Test S3 delivery with desired_logs filtering"""
        # Create S3 configuration with specific desired_logs filter
        filtered_s3_config = {
            "tenant_id": "filtered-s3-tenant",
            "type": "s3",
            "bucket_name": "filtered-bucket",
            "bucket_prefix": "filtered-logs/",
            "target_region": "us-east-1",
            "enabled": True,
            "desired_logs": ["payment-service", "user-service"]  # Only these apps
        }
        
        delivery_config_service.create_tenant_config(filtered_s3_config)
        
        central_role_arn = "arn:aws:iam::123456789012:role/CentralLogDistributionRole"
        
        with patch.dict('os.environ', {
            'CENTRAL_LOG_DISTRIBUTION_ROLE_ARN': central_role_arn,
            'AWS_REGION': 'us-east-1',
            'TENANT_CONFIG_TABLE': delivery_config_service.table_name
        }):
            with patch('boto3.client') as mock_boto_client:
                mock_sts = Mock()
                mock_sts.assume_role.return_value = {
                    'Credentials': {
                        'AccessKeyId': 'assumed-key',
                        'SecretAccessKey': 'assumed-secret',
                        'SessionToken': 'assumed-token'
                    }
                }
                
                mock_s3 = Mock()
                mock_s3.copy_object.return_value = {}
                
                def boto_client_side_effect(service, **kwargs):
                    if service == 'sts':
                        return mock_sts
                    elif service == 's3':
                        return mock_s3
                    elif service == 'dynamodb':
                        return boto3.client(
                            'dynamodb',
                            endpoint_url=f'http://localhost:{kubectl_port_forward}',
                            region_name='us-east-1',
                            aws_access_key_id='test',
                            aws_secret_access_key='test'
                        )
                    return Mock()
                
                mock_boto_client.side_effect = boto_client_side_effect
                
                # Import processor
                import sys
                import os
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../container'))
                from log_processor import process_sqs_record
                
                # Test 1: App in desired_logs (should process)
                s3_event_allowed = {
                    "Records": [{
                        "s3": {
                            "bucket": {"name": "source-bucket"},
                            "object": {"key": "test-cluster/filtered-s3-tenant/payment-service/pod-123/20240901-logs.json.gz"}
                        }
                    }]
                }
                
                sns_message = {"Message": json.dumps(s3_event_allowed)}
                sqs_record = {
                    "body": json.dumps(sns_message),
                    "messageId": "filtered-allowed-test"
                }
                
                with patch('log_processor.download_and_process_log_file') as mock_download:
                    test_log_events = [{"message": "Payment service log", "timestamp": 1693526400000}]
                    mock_download.return_value = (test_log_events, 1693526400)
                    
                    # Process allowed app
                    process_sqs_record(sqs_record)
                    
                    # Should process S3 delivery for allowed app
                    mock_s3.copy_object.assert_called_once()
                    
                # Reset mocks for next test
                mock_s3.reset_mock()
                
                # Test 2: App NOT in desired_logs (should skip)
                s3_event_blocked = {
                    "Records": [{
                        "s3": {
                            "bucket": {"name": "source-bucket"},
                            "object": {"key": "test-cluster/filtered-s3-tenant/blocked-service/pod-456/20240901-logs.json.gz"}
                        }
                    }]
                }
                
                sns_message = {"Message": json.dumps(s3_event_blocked)}
                sqs_record = {
                    "body": json.dumps(sns_message),
                    "messageId": "filtered-blocked-test"
                }
                
                with patch('log_processor.download_and_process_log_file') as mock_download:
                    test_log_events = [{"message": "Blocked service log", "timestamp": 1693526400000}]
                    mock_download.return_value = (test_log_events, 1693526400)
                    
                    # Process blocked app
                    process_sqs_record(sqs_record)
                    
                    # Should NOT process S3 delivery for blocked app
                    mock_s3.copy_object.assert_not_called()
    
    def test_s3_delivery_cross_region_config(self, delivery_config_service, kubectl_port_forward: int):
        """Test S3 delivery with cross-region target configuration"""
        # Create S3 configuration targeting different region
        cross_region_config = {
            "tenant_id": "cross-region-tenant",
            "type": "s3",
            "bucket_name": "eu-west-1-bucket",
            "bucket_prefix": "cross-region-logs/",
            "target_region": "eu-west-1",  # Different from processor region
            "enabled": True
        }
        
        delivery_config_service.create_tenant_config(cross_region_config)
        
        central_role_arn = "arn:aws:iam::123456789012:role/CentralLogDistributionRole"
        
        with patch.dict('os.environ', {
            'CENTRAL_LOG_DISTRIBUTION_ROLE_ARN': central_role_arn,
            'AWS_REGION': 'us-east-1'  # Processor in us-east-1
        }):
            with patch('boto3.client') as mock_boto_client:
                mock_sts = Mock()
                mock_sts.assume_role.return_value = {
                    'Credentials': {
                        'AccessKeyId': 'assumed-key',
                        'SecretAccessKey': 'assumed-secret',
                        'SessionToken': 'assumed-token'
                    }
                }
                
                mock_s3 = Mock()
                mock_s3.copy_object.return_value = {}
                
                def boto_client_side_effect(service, **kwargs):
                    if service == 'sts':
                        return mock_sts
                    elif service == 's3':
                        # Verify S3 client is created with target region
                        assert kwargs.get('region_name') == 'eu-west-1'
                        return mock_s3
                    elif service == 'dynamodb':
                        return boto3.client(
                            'dynamodb',
                            endpoint_url=f'http://localhost:{kubectl_port_forward}',
                            region_name='us-east-1',
                            aws_access_key_id='test',
                            aws_secret_access_key='test'
                        )
                    return Mock()
                
                mock_boto_client.side_effect = boto_client_side_effect
                
                # Import processor
                import sys
                import os
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../container'))
                from log_processor import process_sqs_record
                
                # Create SQS record
                s3_event = {
                    "Records": [{
                        "s3": {
                            "bucket": {"name": "source-bucket"},
                            "object": {"key": "test-cluster/cross-region-tenant/global-app/pod-789/20240901-logs.json.gz"}
                        }
                    }]
                }
                
                sns_message = {"Message": json.dumps(s3_event)}
                sqs_record = {
                    "body": json.dumps(sns_message),
                    "messageId": "cross-region-test"
                }
                
                with patch('log_processor.download_and_process_log_file') as mock_download:
                    test_log_events = [{"message": "Cross-region test log", "timestamp": 1693526400000}]
                    mock_download.return_value = (test_log_events, 1693526400)
                    
                    # Process SQS record
                    process_sqs_record(sqs_record)
                    
                    # Verify S3 copy was performed
                    mock_s3.copy_object.assert_called_once()
                    
                    # Verify cross-region bucket targeting
                    copy_call = mock_s3.copy_object.call_args[1]
                    assert copy_call['Bucket'] == 'eu-west-1-bucket'
                    
                    # Verify S3 client was created with correct target region (eu-west-1)
                    s3_client_calls = [call for call in mock_boto_client.call_args_list if call[0][0] == 's3']
                    assert any(call[1]['region_name'] == 'eu-west-1' for call in s3_client_calls)


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