"""
Unit tests for log_processor.py
"""
import json
import gzip
import pytest
from unittest.mock import patch, Mock, MagicMock, call, mock_open
from datetime import datetime
import boto3
from moto import mock_aws
from freezegun import freeze_time

# Import the module under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../container'))

import log_processor
from log_processor import (
    extract_tenant_info_from_key,
    get_tenant_delivery_configs,
    should_process_application,
    should_process_delivery_config,
    download_and_process_log_file,
    process_json_file,
    convert_log_record_to_event,
    parse_vector_log_level,
    log_vector_line,
    TenantNotFoundError,
    InvalidS3NotificationError,
    NonRecoverableError
)


class TestExtractTenantInfoFromKey:
    """Test S3 object key parsing functionality."""
    
    def test_valid_object_key(self):
        """Test parsing a valid S3 object key."""
        object_key = "prod-cluster/acme-corp/payment-service/payment-pod-123/20240101-uuid.json.gz"
        result = extract_tenant_info_from_key(object_key)
        
        expected = {
            'cluster_id': 'prod-cluster',
            'tenant_id': 'acme-corp',
            'customer_id': 'acme-corp',
            'namespace': 'acme-corp',
            'application': 'payment-service',
            'pod_name': 'payment-pod-123',
            'environment': 'production'
        }
        assert result == expected
    
    def test_environment_extraction_from_cluster_id(self):
        """Test environment extraction from cluster_id prefix."""
        test_cases = [
            ("dev-cluster", "development"),
            ("stg-cluster", "staging"),
            ("prod-cluster", "production"),
            ("test-cluster", "production"),  # fallback
            ("cluster", "production")  # no prefix
        ]
        
        for cluster_id, expected_env in test_cases:
            object_key = f"{cluster_id}/tenant/app/pod/file.json.gz"
            result = extract_tenant_info_from_key(object_key)
            assert result['environment'] == expected_env
    
    def test_invalid_object_key_too_few_segments(self):
        """Test parsing invalid object key with too few segments."""
        object_key = "cluster/tenant/app"
        
        with pytest.raises(InvalidS3NotificationError) as exc_info:
            extract_tenant_info_from_key(object_key)
        
        assert "Invalid object key format" in str(exc_info.value)
        assert "Expected at least 5 path segments" in str(exc_info.value)
    
    def test_invalid_object_key_empty_cluster_id(self):
        """Test parsing object key with empty cluster_id (leading slash)."""
        object_key = "/tenant/app/pod/file.json.gz"
        
        with pytest.raises(InvalidS3NotificationError) as exc_info:
            extract_tenant_info_from_key(object_key)
        
        assert "cluster_id (segment 0) cannot be empty" in str(exc_info.value)
    
    def test_invalid_object_key_empty_tenant_id(self):
        """Test parsing object key with empty tenant_id (double slash)."""
        # This is the exact scenario from the bug report
        object_key = "scuppett-oepz//hosted-cluster-config-operator/hosted-cluster-config-operator-c66f74b5f-dhp62/20250831-104654.json.gz"
        
        with pytest.raises(InvalidS3NotificationError) as exc_info:
            extract_tenant_info_from_key(object_key)
        
        assert "tenant_id (segment 1) cannot be empty" in str(exc_info.value)
    
    def test_invalid_object_key_empty_application(self):
        """Test parsing object key with empty application."""
        object_key = "cluster/tenant//pod/file.json.gz"
        
        with pytest.raises(InvalidS3NotificationError) as exc_info:
            extract_tenant_info_from_key(object_key)
        
        assert "application (segment 2) cannot be empty" in str(exc_info.value)
    
    def test_invalid_object_key_empty_pod_name(self):
        """Test parsing object key with empty pod_name."""
        object_key = "cluster/tenant/app//file.json.gz"
        
        with pytest.raises(InvalidS3NotificationError) as exc_info:
            extract_tenant_info_from_key(object_key)
        
        assert "pod_name (segment 3) cannot be empty" in str(exc_info.value)
    
    def test_invalid_object_key_whitespace_only_segments(self):
        """Test parsing object key with whitespace-only segments."""
        object_key = "cluster/ /app/pod/file.json.gz"
        
        with pytest.raises(InvalidS3NotificationError) as exc_info:
            extract_tenant_info_from_key(object_key)
        
        assert "tenant_id (segment 1) cannot be empty" in str(exc_info.value)


class TestTenantConfiguration:
    """Test tenant configuration management."""
    
    @pytest.fixture
    def dynamodb_table(self, mock_aws_services):
        """Create a test DynamoDB table."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        table = dynamodb.create_table(
            TableName='test-tenant-configs',
            KeySchema=[
                {
                    'AttributeName': 'tenant_id',
                    'KeyType': 'HASH'
                },
                {
                    'AttributeName': 'type',
                    'KeyType': 'RANGE'
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'tenant_id',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'type',
                    'AttributeType': 'S'
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Add test tenant configurations with composite key
        table.put_item(Item={
            'tenant_id': 'acme-corp',
            'type': 'cloudwatch',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole',
            'log_group_name': '/aws/logs/acme-corp',
            'target_region': 'us-east-1',
            'enabled': True,
            'desired_logs': ['payment-service', 'user-service']
        })
        
        table.put_item(Item={
            'tenant_id': 'disabled-tenant',
            'type': 'cloudwatch',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole',
            'log_group_name': '/aws/logs/disabled',
            'target_region': 'us-east-1',
            'enabled': False
        })
        
        table.put_item(Item={
            'tenant_id': 'missing-fields',
            'type': 'cloudwatch',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole'
            # Missing required fields
        })
        
        return table
    
    def test_get_tenant_delivery_configs_success(self, environment_variables, dynamodb_table):
        """Test successful tenant delivery configuration retrieval."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            configs = get_tenant_delivery_configs('acme-corp')
        
        assert len(configs) == 1
        config = configs[0]
        assert config['tenant_id'] == 'acme-corp'
        assert config['type'] == 'cloudwatch'
        assert config['log_distribution_role_arn'] == 'arn:aws:iam::987654321098:role/LogRole'
        assert config['log_group_name'] == '/aws/logs/acme-corp'
        assert config['target_region'] == 'us-east-1'
        assert config['enabled'] is True
        assert config['desired_logs'] == ['payment-service', 'user-service']
    
    def test_get_tenant_delivery_configs_not_found(self, environment_variables, dynamodb_table):
        """Test tenant delivery configuration not found."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            with pytest.raises(TenantNotFoundError) as exc_info:
                get_tenant_delivery_configs('nonexistent-tenant')
        
        assert "No delivery configurations found for tenant: nonexistent-tenant" in str(exc_info.value)
    
    def test_get_tenant_delivery_configs_missing_required_fields(self, environment_variables, dynamodb_table):
        """Test tenant delivery configuration with missing required fields."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            with pytest.raises(TenantNotFoundError) as exc_info:
                get_tenant_delivery_configs('missing-fields')
        
        assert "missing required field" in str(exc_info.value)
    
    def test_should_process_delivery_config_enabled(self, environment_variables, dynamodb_table):
        """Test should_process_delivery_config with enabled tenant."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            configs = get_tenant_delivery_configs('acme-corp')
        config = configs[0]
        assert should_process_delivery_config(config, 'acme-corp', 'cloudwatch') is True
    
    def test_should_process_delivery_config_disabled(self, environment_variables, dynamodb_table):
        """Test should_process_delivery_config with disabled delivery config."""
        # Create a disabled config directly for testing the function
        disabled_config = {
            'tenant_id': 'disabled-tenant',
            'type': 'cloudwatch',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole',
            'log_group_name': '/aws/logs/disabled',
            'target_region': 'us-east-1',
            'enabled': False
        }
        assert should_process_delivery_config(disabled_config, 'disabled-tenant', 'cloudwatch') is False
    
    def test_should_process_application_with_desired_logs(self, environment_variables, dynamodb_table):
        """Test application filtering with desired_logs configuration."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            configs = get_tenant_delivery_configs('acme-corp')
        config = configs[0]
        
        assert should_process_application(config, 'payment-service') is True
        assert should_process_application(config, 'user-service') is True
        assert should_process_application(config, 'admin-service') is False
    
    def test_should_process_application_case_insensitive(self, environment_variables, dynamodb_table):
        """Test application filtering is case insensitive."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            configs = get_tenant_delivery_configs('acme-corp')
        config = configs[0]
        
        assert should_process_application(config, 'Payment-Service') is True
        assert should_process_application(config, 'USER-SERVICE') is True
    
    def test_should_process_application_no_filtering(self, environment_variables, dynamodb_table):
        """Test application processing when no desired_logs is specified."""
        # Create a config without desired_logs for testing
        config_without_filtering = {
            'tenant_id': 'test-tenant',
            'type': 'cloudwatch',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole',
            'log_group_name': '/aws/logs/test-tenant',
            'target_region': 'us-east-1',
            'enabled': True
            # No desired_logs field - should allow all applications
        }
        
        assert should_process_application(config_without_filtering, 'any-service') is True
    
    def test_get_tenant_delivery_configs_dynamodb_validation_exception(self, environment_variables):
        """Test DynamoDB ValidationException for empty string tenant_id."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            with patch('boto3.resource') as mock_boto3:
                mock_table = MagicMock()
                mock_boto3.return_value.Table.return_value = mock_table
                
                # Simulate DynamoDB ValidationException for empty string
                validation_error = Exception(
                    'ValidationException: One or more parameter values are not valid. '
                    'The AttributeValue for a key attribute cannot contain an empty string value. Key: tenant_id'
                )
                mock_table.query.side_effect = validation_error
                
                with pytest.raises(TenantNotFoundError) as exc_info:
                    get_tenant_delivery_configs('')
                
                assert "Invalid tenant_id (empty string) from malformed S3 path" in str(exc_info.value)
    
    def test_get_tenant_delivery_configs_other_dynamodb_error(self, environment_variables):
        """Test that other DynamoDB errors are not converted to TenantNotFoundError."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            with patch('boto3.resource') as mock_boto3:
                mock_table = MagicMock()
                mock_boto3.return_value.Table.return_value = mock_table
                
                # Simulate other DynamoDB error
                other_error = Exception('Some other DynamoDB error')
                mock_table.query.side_effect = other_error
                
                with pytest.raises(Exception) as exc_info:
                    get_tenant_delivery_configs('valid-tenant')
                
                # Should not be converted to TenantNotFoundError
                assert "Some other DynamoDB error" in str(exc_info.value)
                assert not isinstance(exc_info.value, TenantNotFoundError)


class TestLogProcessing:
    """Test log file processing functionality."""
    
    @pytest.fixture
    def s3_bucket(self, mock_aws_services):
        """Create a test S3 bucket with log files."""
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-log-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Create test log content
        log_data = [
            {"timestamp": "2024-01-01T10:00:00Z", "message": "Log message 1"},
            {"timestamp": "2024-01-01T10:00:01Z", "message": "Log message 2"}
        ]
        
        # Test NDJSON format (Vector format)
        ndjson_content = '\n'.join(json.dumps(log) for log in log_data)
        compressed_content = gzip.compress(ndjson_content.encode('utf-8'))
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key='test-logs.json.gz',
            Body=compressed_content
        )
        
        # Test JSON array format
        json_array_content = json.dumps(log_data)
        s3_client.put_object(
            Bucket=bucket_name,
            Key='test-logs-array.json',
            Body=json_array_content.encode('utf-8')
        )
        
        return bucket_name
    
    def test_download_and_process_log_file_gzipped(self, environment_variables, s3_bucket):
        """Test downloading and processing gzipped log file."""
        log_events, s3_timestamp = download_and_process_log_file(s3_bucket, 'test-logs.json.gz')
        
        assert len(log_events) == 2
        assert log_events[0]['message'] == 'Log message 1'
        assert log_events[1]['message'] == 'Log message 2'
        assert isinstance(s3_timestamp, int)
        assert s3_timestamp > 0
    
    def test_download_and_process_log_file_uncompressed(self, environment_variables, s3_bucket):
        """Test downloading and processing uncompressed log file."""
        log_events, s3_timestamp = download_and_process_log_file(s3_bucket, 'test-logs-array.json')
        
        assert len(log_events) == 2
        assert log_events[0]['message'] == 'Log message 1'
        assert log_events[1]['message'] == 'Log message 2'
    
    def test_process_json_file_ndjson_format(self):
        """Test processing NDJSON format log file."""
        log_data = [
            {"timestamp": "2024-01-01T10:00:00Z", "message": "Log 1"},
            {"timestamp": "2024-01-01T10:00:01Z", "message": "Log 2"}
        ]
        ndjson_content = '\n'.join(json.dumps(log) for log in log_data)
        
        log_events = process_json_file(ndjson_content.encode('utf-8'))
        
        assert len(log_events) == 2
        assert log_events[0]['message'] == 'Log 1'
        assert log_events[1]['message'] == 'Log 2'
    
    def test_process_json_file_array_format(self):
        """Test processing JSON array format log file."""
        log_data = [
            {"timestamp": "2024-01-01T10:00:00Z", "message": "Log 1"},
            {"timestamp": "2024-01-01T10:00:01Z", "message": "Log 2"}
        ]
        json_content = json.dumps(log_data)
        
        log_events = process_json_file(json_content.encode('utf-8'))
        
        assert len(log_events) == 2
        assert log_events[0]['message'] == 'Log 1'
        assert log_events[1]['message'] == 'Log 2'
    
    @freeze_time("2024-01-01 12:00:00")
    def test_convert_log_record_to_event_with_timestamp(self):
        """Test converting pre-structured log record with timestamp."""
        # Since Vector now handles JSON parsing, log records are already structured
        log_record = {
            "timestamp": "2024-01-01T10:00:00Z",
            "message": "Test log message",
            "level": "INFO",
            "cluster_id": "test-cluster",
            "namespace": "default",
            "application": "test-app"
        }
        
        event = convert_log_record_to_event(log_record)
        
        assert event is not None
        assert event['message'] == 'Test log message'
        # The timestamp should be around 2024-01-01T10:00:00Z, allow some tolerance for timezone conversion
        assert 1704099600000 <= event['timestamp'] <= 1704103200000
    
    @freeze_time("2024-01-01 12:00:00")
    def test_convert_log_record_to_event_without_timestamp(self):
        """Test converting pre-structured log record without timestamp."""
        # Since Vector now handles JSON parsing, log records are already structured
        log_record = {
            "message": "Test log message",
            "level": "INFO",
            "cluster_id": "test-cluster",
            "namespace": "default"
        }
        
        event = convert_log_record_to_event(log_record)
        
        assert event is not None
        assert event['message'] == 'Test log message'
        assert event['timestamp'] == 1704110400000  # Current time in ms
    
    def test_convert_log_record_to_event_no_message(self):
        """Test converting pre-structured log record without message field."""
        # Since Vector now handles JSON parsing, log records are already structured
        log_record = {
            "timestamp": "2024-01-01T10:00:00Z", 
            "level": "INFO",
            "cluster_id": "test-cluster",
            "data": "some data"
        }
        
        event = convert_log_record_to_event(log_record)
        
        assert event is not None
        assert json.loads(event['message']) == log_record  # Entire record as JSON fallback
    
    def test_convert_log_record_to_event_plain_text_from_vector(self):
        """Test converting plain text log that was processed by Vector."""
        # Vector wraps plain text logs with metadata
        log_record = {
            "timestamp": "2024-01-01T10:00:00Z",
            "message": "2024-01-01T10:00:00Z INFO auth.service: User login successful",
            "cluster_id": "test-cluster",
            "namespace": "default",
            "application": "auth-service",
            "pod_name": "auth-pod-123"
        }
        
        event = convert_log_record_to_event(log_record)
        
        assert event is not None
        assert event['message'] == "2024-01-01T10:00:00Z INFO auth.service: User login successful"
        assert 1704099600000 <= event['timestamp'] <= 1704103200000
    
    def test_convert_log_record_to_event_json_log_from_vector(self):
        """Test converting JSON log that was processed and parsed by Vector."""
        # Vector parses JSON logs and merges fields into the top level
        log_record = {
            "timestamp": "2024-01-01T10:00:00Z",
            "message": "Payment processed successfully",
            "level": "INFO",
            "request_id": "req-12345",
            "user_id": "user-789",
            "amount": 100.50,
            "cluster_id": "test-cluster",
            "namespace": "default",
            "application": "payment-service",
            "pod_name": "payment-pod-456"
        }
        
        event = convert_log_record_to_event(log_record)
        
        assert event is not None
        assert event['message'] == "Payment processed successfully"
        assert 1704099600000 <= event['timestamp'] <= 1704103200000


class TestSQSRecordProcessing:
    """Test SQS record processing functionality."""
    
    def test_process_sqs_record_valid_sns_message(self, environment_variables, mock_aws_services):
        """Test processing valid SQS record with SNS message."""
        # Create S3 event
        s3_event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "prod-cluster/acme-corp/payment-service/pod-123/file.json.gz"}
                }
            }]
        }
        
        # Create SNS message
        sns_message = {"Message": json.dumps(s3_event)}
        
        # Create SQS record
        sqs_record = {
            "body": json.dumps(sns_message),
            "messageId": "test-message-id"
        }
        
        with patch('log_processor.get_tenant_delivery_configs') as mock_get_tenant, \
             patch('log_processor.download_and_process_log_file') as mock_download, \
             patch('log_processor.deliver_logs_to_cloudwatch') as mock_deliver_cw:
            
            mock_get_tenant.return_value = [{
                'tenant_id': 'acme-corp',
                'type': 'cloudwatch',
                'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole',
                'log_group_name': '/aws/logs/acme-corp',
                'target_region': 'us-east-1',
                'enabled': True
            }]
            mock_download.return_value = ([{"message": "test", "timestamp": 1234567890}], 1234567890)
            mock_deliver_cw.return_value = None
            
            # Should not raise an exception
            log_processor.process_sqs_record(sqs_record)
            
            mock_get_tenant.assert_called_once_with('acme-corp')
            mock_download.assert_called_once()
            mock_deliver_cw.assert_called_once()
    
    def test_process_sqs_record_invalid_json(self, environment_variables):
        """Test processing SQS record with invalid JSON."""
        sqs_record = {
            "body": "invalid json",
            "messageId": "test-message-id"
        }
        
        # The function logs the error and returns without raising
        # (it's designed to handle this gracefully in the SQS context)
        log_processor.process_sqs_record(sqs_record)
    
    def test_process_sqs_record_tenant_not_found(self, environment_variables, mock_aws_services):
        """Test processing SQS record when tenant is not found."""
        s3_event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "prod-cluster/nonexistent-tenant/app/pod/file.json.gz"}
                }
            }]
        }
        
        sns_message = {"Message": json.dumps(s3_event)}
        sqs_record = {
            "body": json.dumps(sns_message),
            "messageId": "test-message-id"
        }
        
        with patch('log_processor.get_tenant_delivery_configs') as mock_get_tenant:
            mock_get_tenant.side_effect = TenantNotFoundError("Tenant not found")
            
            # Should not raise an exception (handled as non-recoverable)
            log_processor.process_sqs_record(sqs_record)
    
    def test_process_sqs_record_malformed_s3_path_empty_tenant_id(self, environment_variables):
        """Test processing SQS record with malformed S3 path (empty tenant_id)."""
        # Create S3 event with malformed path (double slash - the exact bug scenario)
        s3_event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "scuppett-oepz//hosted-cluster-config-operator/pod-123/file.json.gz"}
                }
            }]
        }
        
        # Create SNS message
        sns_message = {"Message": json.dumps(s3_event)}
        
        # Create SQS record
        sqs_record = {
            "body": json.dumps(sns_message),
            "messageId": "test-message-id"
        }
        
        # Should not raise an exception (handled as non-recoverable)
        # The InvalidS3NotificationError should be caught and handled
        log_processor.process_sqs_record(sqs_record)
    
    def test_process_sqs_record_malformed_s3_path_empty_cluster_id(self, environment_variables):
        """Test processing SQS record with malformed S3 path (empty cluster_id)."""
        # Create S3 event with malformed path (leading slash)
        s3_event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "/tenant/app/pod/file.json.gz"}
                }
            }]
        }
        
        # Create SNS message
        sns_message = {"Message": json.dumps(s3_event)}
        
        # Create SQS record
        sqs_record = {
            "body": json.dumps(sns_message),
            "messageId": "test-message-id"
        }
        
        # Should not raise an exception (handled as non-recoverable)
        log_processor.process_sqs_record(sqs_record)
    
    def test_process_sqs_record_dynamodb_validation_exception(self, environment_variables):
        """Test processing SQS record that triggers DynamoDB ValidationException."""
        # Create S3 event with valid path but simulate ValidationException in DynamoDB
        s3_event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "cluster/tenant/app/pod/file.json.gz"}
                }
            }]
        }
        
        # Create SNS message
        sns_message = {"Message": json.dumps(s3_event)}
        
        # Create SQS record
        sqs_record = {
            "body": json.dumps(sns_message),
            "messageId": "test-message-id"
        }
        
        with patch('boto3.resource') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.return_value.Table.return_value = mock_table
            
            # Simulate DynamoDB ValidationException for empty string
            validation_error = Exception(
                'ValidationException: One or more parameter values are not valid. '
                'The AttributeValue for a key attribute cannot contain an empty string value. Key: tenant_id'
            )
            mock_table.get_item.side_effect = validation_error
            
            # Should not raise an exception (ValidationException converted to TenantNotFoundError)
            log_processor.process_sqs_record(sqs_record)


class TestLambdaHandler:
    """Test Lambda handler functionality."""
    
    def test_lambda_handler_success(self, environment_variables):
        """Test Lambda handler with successful processing."""
        event = {
            "Records": [
                {"messageId": "msg-1", "body": "test-body-1"},
                {"messageId": "msg-2", "body": "test-body-2"}
            ]
        }
        
        with patch('log_processor.process_sqs_record') as mock_process:
            mock_process.return_value = {'successful_deliveries': 1, 'failed_deliveries': 0}
            
            result = log_processor.lambda_handler(event, None)
            
            assert result == {'batchItemFailures': []}
            assert mock_process.call_count == 2
    
    def test_lambda_handler_partial_failure(self, environment_variables):
        """Test Lambda handler with partial batch failure."""
        event = {
            "Records": [
                {"messageId": "msg-1", "body": "test-body-1"},
                {"messageId": "msg-2", "body": "test-body-2"}
            ]
        }
        
        with patch('log_processor.process_sqs_record') as mock_process:
            # First message succeeds, second fails
            mock_process.side_effect = [{'successful_deliveries': 1, 'failed_deliveries': 0}, Exception("Recoverable error")]
            
            result = log_processor.lambda_handler(event, None)
            
            assert result == {'batchItemFailures': [{'itemIdentifier': 'msg-2'}]}
    
    def test_lambda_handler_non_recoverable_error(self, environment_variables):
        """Test Lambda handler with non-recoverable error."""
        event = {
            "Records": [
                {"messageId": "msg-1", "body": "test-body-1"}
            ]
        }
        
        with patch('log_processor.process_sqs_record') as mock_process:
            mock_process.side_effect = NonRecoverableError("Non-recoverable error")
            
            result = log_processor.lambda_handler(event, None)
            
            # Non-recoverable errors should not cause retry
            assert result == {'batchItemFailures': []}


class TestVectorDelivery:
    """Test Vector log delivery functionality."""
    
    @patch('log_processor.subprocess.Popen')
    @patch('log_processor.tempfile.mkstemp')
    @patch('log_processor.os.makedirs')
    def test_deliver_logs_with_vector_success(self, mock_makedirs, mock_mkstemp, mock_popen):
        """Test successful Vector log delivery."""
        # Mock tempfile creation
        mock_mkstemp.return_value = (5, '/tmp/vector-config-123.yaml')
        
        # Mock subprocess
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.communicate.return_value = ('Vector output', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        log_events = [
            {"message": "Test log 1", "timestamp": 1234567890},
            {"message": "Test log 2", "timestamp": 1234567891}
        ]
        
        credentials = {
            'AccessKeyId': 'test-key',
            'SecretAccessKey': 'test-secret',
            'SessionToken': 'test-token'
        }
        
        # Mock file operations properly using mock_open
        mocked_open = mock_open(read_data='mock config template')
        
        with patch('builtins.open', mocked_open), \
             patch('os.fdopen', mock_open()), \
             patch('os.path.exists', return_value=True), \
             patch('os.unlink'), \
             patch('shutil.rmtree'):
            
            log_processor.deliver_logs_with_vector(
                log_events=log_events,
                central_credentials=credentials,
                customer_role_arn='arn:aws:iam::987654321098:role/CustomerRole',
                external_id='123456789012',
                region='us-east-1',
                log_group='/aws/logs/test',
                log_stream='test-stream',
                session_id='test-session',
                s3_timestamp=1234567890
            )
            
            mock_popen.assert_called_once()
            mock_process.communicate.assert_called_once()
    
    @patch('log_processor.subprocess.Popen')
    @patch('log_processor.tempfile.mkstemp')
    def test_deliver_logs_with_vector_failure(self, mock_mkstemp, mock_popen):
        """Test Vector log delivery failure."""
        mock_mkstemp.return_value = (5, '/tmp/vector-config-123.yaml')
        
        # Mock subprocess failure
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.communicate.return_value = ('', 'Error output')
        mock_process.returncode = 1
        mock_popen.return_value = mock_process
        
        log_events = [{"message": "Test log", "timestamp": 1234567890}]
        credentials = {
            'AccessKeyId': 'test-key',
            'SecretAccessKey': 'test-secret',
            'SessionToken': 'test-token'
        }
        
        # Mock file operations properly using mock_open
        mocked_open = mock_open(read_data='mock config template')
        
        with patch('builtins.open', mocked_open), \
             patch('os.fdopen', mock_open()), \
             patch('os.path.exists', return_value=True), \
             patch('os.unlink'), \
             patch('shutil.rmtree'), \
             pytest.raises(Exception) as exc_info:
            
            log_processor.deliver_logs_with_vector(
                log_events=log_events,
                central_credentials=credentials,
                customer_role_arn='arn:aws:iam::987654321098:role/CustomerRole',
                external_id='123456789012',
                region='us-east-1',
                log_group='/aws/logs/test',
                log_stream='test-stream',
                session_id='test-session',
                s3_timestamp=1234567890
            )
        
        assert "Vector exited with non-zero code 1" in str(exc_info.value)
    
    @patch('log_processor.subprocess.Popen')
    @patch('log_processor.tempfile.mkstemp')
    def test_deliver_logs_with_vector_timestamp_conversion(self, mock_mkstemp, mock_popen):
        """Test Vector log delivery with proper timestamp format conversion."""
        mock_mkstemp.return_value = (5, '/tmp/vector-config-123.yaml')
        
        # Mock subprocess
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.communicate.return_value = ('Vector output', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        # Test with millisecond timestamps (should be converted to seconds)
        log_events = [
            {"message": "Test log 1", "timestamp": 1609459200000},  # 2021-01-01 00:00:00 in ms
            {"message": "Test log 2", "timestamp": 1609459260000},  # 2021-01-01 00:01:00 in ms
            {"message": "Test log 3", "timestamp": 1609459200}     # Already in seconds
        ]
        
        credentials = {
            'AccessKeyId': 'test-key',
            'SecretAccessKey': 'test-secret',
            'SessionToken': 'test-token'
        }
        
        # Mock file operations
        mocked_open = mock_open(read_data='mock config template')
        
        with patch('builtins.open', mocked_open), \
             patch('os.fdopen', mock_open()), \
             patch('os.path.exists', return_value=True), \
             patch('os.unlink'), \
             patch('shutil.rmtree'):
            
            log_processor.deliver_logs_with_vector(
                log_events=log_events,
                central_credentials=credentials,
                customer_role_arn='arn:aws:iam::987654321098:role/CustomerRole',
                external_id='123456789012',
                region='us-east-1',
                log_group='/aws/logs/test',
                log_stream='test-stream',
                session_id='test-session',
                s3_timestamp=1609459200000
            )
            
            # Verify subprocess was called
            mock_popen.assert_called_once()
            
            # Verify the input sent to Vector subprocess
            call_args = mock_process.communicate.call_args
            input_data = call_args[1]['input']  # communicate(input=data, timeout=300)
            
            # Parse the NDJSON input to verify timestamp conversion
            lines = input_data.strip().split('\n')
            assert len(lines) == 3
            
            # Check first event (millisecond timestamp converted to seconds)
            import json
            event1 = json.loads(lines[0])
            assert event1['message'] == 'Test log 1'
            assert event1['timestamp'] == 1609459200.0  # Converted from ms to seconds
            
            # Check second event
            event2 = json.loads(lines[1])
            assert event2['message'] == 'Test log 2'
            assert event2['timestamp'] == 1609459260.0  # Converted from ms to seconds
            
            # Check third event (already in seconds, should remain unchanged)
            event3 = json.loads(lines[2])
            assert event3['message'] == 'Test log 3'
            assert event3['timestamp'] == 1609459200  # Should remain as seconds


class TestCrossAccountRoleAssumption:
    """Test cross-account role assumption functionality."""
    
    @patch('boto3.client')
    def test_deliver_logs_to_cloudwatch_double_hop(self, mock_boto_client, environment_variables):
        """Test role assumption for CloudWatch log delivery using Vector's native assume_role."""
        # Mock STS client
        mock_sts_client = Mock()
        
        # Mock role assumption responses
        central_role_response = {
            'Credentials': {
                'AccessKeyId': 'central-key',
                'SecretAccessKey': 'central-secret',
                'SessionToken': 'central-token'
            }
        }
        
        mock_sts_client.assume_role.return_value = central_role_response
        mock_sts_client.get_caller_identity.return_value = {'Account': '123456789012'}
        
        # Setup boto3.client to return STS client
        def mock_client_factory(service, **kwargs):
            if service == 'sts':
                return mock_sts_client
            return Mock()
        
        mock_boto_client.side_effect = mock_client_factory
        
        log_events = [{"message": "Test log", "timestamp": 1234567890}]
        delivery_config = {
            'tenant_id': 'test-tenant',
            'type': 'cloudwatch',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/CustomerRole',
            'log_group_name': '/aws/logs/customer',
            'target_region': 'us-east-1'
        }
        tenant_info = {
            'tenant_id': 'test-tenant',
            'pod_name': 'test-pod'
        }
        
        with patch('log_processor.deliver_logs_with_vector') as mock_vector_delivery:
            log_processor.deliver_logs_to_cloudwatch(
                log_events=log_events,
                delivery_config=delivery_config,
                tenant_info=tenant_info,
                s3_timestamp=1234567890
            )
            
            # Verify only central role assumption was called (customer role handled by Vector)
            mock_sts_client.assume_role.assert_called_once()
            
            # Verify deliver_logs_with_vector was called with central credentials and customer role ARN
            mock_vector_delivery.assert_called_once()
            call_args = mock_vector_delivery.call_args
            assert call_args[1]['central_credentials']['AccessKeyId'] == 'central-key'
            assert call_args[1]['customer_role_arn'] == 'arn:aws:iam::987654321098:role/CustomerRole'
            assert call_args[1]['external_id'] == '123456789012'


class TestVectorLogParsing:
    """Test Vector log level parsing functionality."""
    
    def test_parse_vector_log_level_info(self):
        """Test parsing Vector INFO level logs."""
        import logging
        log_line = "2025-08-31T10:53:48.817588Z INFO vector::app: Log level is enabled. level=\"info\""
        result = parse_vector_log_level(log_line)
        assert result == logging.INFO
    
    def test_parse_vector_log_level_warn(self):
        """Test parsing Vector WARN level logs."""
        import logging
        log_line = "2025-08-31T10:53:48.817588Z WARN vector::config: Deprecated configuration option used"
        result = parse_vector_log_level(log_line)
        assert result == logging.WARNING
    
    def test_parse_vector_log_level_error(self):
        """Test parsing Vector ERROR level logs."""
        import logging
        log_line = "2025-08-31T10:53:48.817588Z ERROR vector::sources: Failed to connect to source"
        result = parse_vector_log_level(log_line)
        assert result == logging.ERROR
    
    def test_parse_vector_log_level_debug(self):
        """Test parsing Vector DEBUG level logs."""
        import logging
        log_line = "2025-08-31T10:53:48.817588Z DEBUG vector::internal: Debug information"
        result = parse_vector_log_level(log_line)
        assert result == logging.DEBUG
    
    def test_parse_vector_log_level_trace(self):
        """Test parsing Vector TRACE level logs."""
        import logging
        log_line = "2025-08-31T10:53:48.817588Z TRACE vector::internal: Trace information"
        result = parse_vector_log_level(log_line)
        assert result == logging.DEBUG  # TRACE maps to DEBUG
    
    def test_parse_vector_log_level_with_microseconds(self):
        """Test parsing Vector logs with microsecond timestamps."""
        import logging
        log_line = "2025-08-31T10:53:48.817588123Z INFO vector::app: Message with microseconds"
        result = parse_vector_log_level(log_line)
        assert result == logging.INFO
    
    def test_parse_vector_log_level_invalid_format(self):
        """Test parsing non-Vector log format falls back to WARNING."""
        import logging
        log_line = "This is not a Vector log line"
        result = parse_vector_log_level(log_line)
        assert result == logging.WARNING
    
    def test_parse_vector_log_level_unknown_level(self):
        """Test parsing Vector log with unknown level falls back to WARNING."""
        import logging
        log_line = "2025-08-31T10:53:48.817588Z UNKNOWN vector::app: Unknown level"
        result = parse_vector_log_level(log_line)
        assert result == logging.WARNING
    
    def test_log_vector_line_info(self, caplog):
        """Test log_vector_line with INFO level."""
        import logging
        with caplog.at_level(logging.INFO):
            log_line = "2025-08-31T10:53:48.817588Z INFO vector::app: Test message"
            log_vector_line(log_line)
        
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.INFO
        assert "VECTOR: 2025-08-31T10:53:48.817588Z INFO vector::app: Test message" in caplog.records[0].message
    
    def test_log_vector_line_warning(self, caplog):
        """Test log_vector_line with WARNING level."""
        import logging
        with caplog.at_level(logging.WARNING):
            log_line = "2025-08-31T10:53:48.817588Z WARN vector::config: Test warning"
            log_vector_line(log_line)
        
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING
        assert "VECTOR: 2025-08-31T10:53:48.817588Z WARN vector::config: Test warning" in caplog.records[0].message
    
    def test_log_vector_line_error(self, caplog):
        """Test log_vector_line with ERROR level."""
        import logging
        with caplog.at_level(logging.ERROR):
            log_line = "2025-08-31T10:53:48.817588Z ERROR vector::sources: Test error"
            log_vector_line(log_line)
        
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.ERROR
        assert "VECTOR: 2025-08-31T10:53:48.817588Z ERROR vector::sources: Test error" in caplog.records[0].message
    
    def test_parse_vector_log_level_long_message_performance(self):
        """Test that parsing only checks first 50 characters for performance."""
        import logging
        # Create a very long log message - the level should still be parsed correctly
        # because we only check the first 50 characters
        very_long_message = "This is a very long message that goes on and on and contains many characters and could potentially be thousands of characters long in production but we should only scan the first 50 characters for performance reasons"
        log_line = f"2025-08-31T10:53:48.817588Z INFO vector::app: {very_long_message}"
        
        result = parse_vector_log_level(log_line)
        assert result == logging.INFO
        
        # Test that it works even if the message is shorter than 50 characters
        short_log_line = "2025-08-31T10:53:48.817588Z WARN vector::config: Short"
        result = parse_vector_log_level(short_log_line)
        assert result == logging.WARNING
    
    def test_parse_vector_log_level_simplified_regex_edge_cases(self):
        """Test simplified regex handles edge cases correctly."""
        import logging
        
        # Test that log level keywords in message content don't interfere
        # (should pick up the first occurrence which is the actual log level)
        log_line = "2025-08-31T10:53:48.817588Z INFO vector::app: ERROR occurred in downstream"
        result = parse_vector_log_level(log_line)
        assert result == logging.INFO  # Should pick up INFO, not ERROR
        
        # Test that partial matches don't work (word boundaries)
        log_line = "2025-08-31T10:53:48.817588Z INFO vector::app: INFORMATION message"
        result = parse_vector_log_level(log_line)
        assert result == logging.INFO  # Should pick up INFO, not be confused by INFORMATION
        
        # Test line with no recognizable log level
        log_line = "Some random text without log level keywords"
        result = parse_vector_log_level(log_line)
        assert result == logging.WARNING  # Should fallback to WARNING



class TestVectorSubprocessTimestampMapping:
    """Test Vector subprocess configuration for CloudWatch timestamp mapping."""
    
    @patch('log_processor.subprocess.Popen')
    @patch('log_processor.tempfile.mkstemp')
    def test_vector_config_includes_timestamp_transform(self, mock_mkstemp, mock_popen):
        """Test that Vector config template includes timestamp transform for CloudWatch mapping."""
        mock_mkstemp.return_value = (5, '/tmp/vector-config-123.yaml')
        
        # Mock subprocess
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.communicate.return_value = ('Vector output', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        log_events = [{"message": "Test log", "timestamp": 1725108058}]
        
        credentials = {
            'AccessKeyId': 'test-key',
            'SecretAccessKey': 'test-secret',
            'SessionToken': 'test-token'
        }
        
        # We'll capture what's written to the temporary config file
        written_config = None
        
        def mock_fdopen(fd, mode):
            if mode == 'w':
                # Create a mock file object that captures what's written
                mock_file = Mock()
                written_configs = []
                
                def write_side_effect(content):
                    written_configs.append(content)
                    return len(content)
                
                def context_manager():
                    return mock_file
                
                mock_file.write.side_effect = write_side_effect
                mock_file.__enter__ = lambda self: self
                mock_file.__exit__ = lambda self, *args: None
                
                # Store reference so we can access it later
                mock_fdopen.written_configs = written_configs
                return mock_file
            return Mock()
        
        # Mock the template file read with timestamp transform approach
        template_content = '''data_dir: /tmp/vector-{session_id}

sources:
  stdin:
    type: stdin
    decoding:
      codec: "json"

transforms:
  extract_timestamp:
    type: remap
    inputs: ["stdin"]
    source: |
      # Extract timestamp from JSON and convert to proper format
      if exists(.timestamp) {{
        if is_string(.timestamp) {{
          # Parse ISO timestamp string
          parsed_ts, err = parse_timestamp(.timestamp, "%+")
          if err == null {{
            .timestamp = parsed_ts
          }}
        }} else if is_float(.timestamp) || is_integer(.timestamp) {{
          # Convert numeric timestamp to proper timestamp object
          ts_value = to_float!(.timestamp)
          if ts_value > 1000000000000.0 {{
            .timestamp = from_unix_timestamp!(to_int!(ts_value / 1000.0), "seconds")
          }} else {{
            .timestamp = from_unix_timestamp!(to_int!(ts_value), "seconds")
          }}
        }}
      }}

sinks:
  cloudwatch_logs:
    type: aws_cloudwatch_logs
    inputs: ["extract_timestamp"]
    region: "{region}"
    group_name: "{log_group}"
    stream_name: "{log_stream}"
    encoding:
      codec: "text"
      timestamp_format: "unix"
    auth:
      assume_role: "{customer_role_arn}"
      external_id: "{external_id}"
    batch:
      max_events: 1000
      timeout_secs: 5
    request:
      retry_attempts: 3
      retry_max_duration_secs: 30'''
        
        with patch('builtins.open', mock_open(read_data=template_content)), \
             patch('os.fdopen', side_effect=mock_fdopen), \
             patch('os.path.exists', return_value=True), \
             patch('os.unlink'), \
             patch('shutil.rmtree'):
            
            log_processor.deliver_logs_with_vector(
                log_events=log_events,
                central_credentials=credentials,
                customer_role_arn='arn:aws:iam::987654321098:role/CustomerRole',
                external_id='123456789012',
                region='us-east-1',
                log_group='/aws/logs/test',
                log_stream='test-stream',
                session_id='test-session',
                s3_timestamp=1725108058000
            )
            
            # Verify the config was written with timestamp transform
            written_config = ''.join(mock_fdopen.written_configs)
            assert 'extract_timestamp:' in written_config
            assert 'type: remap' in written_config
            assert 'parse_timestamp(.timestamp' in written_config
            assert 'timestamp_format: "unix"' in written_config
            assert 'region: "us-east-1"' in written_config
            assert 'group_name: "/aws/logs/test"' in written_config
    
    @patch('log_processor.subprocess.Popen')
    @patch('log_processor.tempfile.mkstemp')
    def test_vector_receives_proper_timestamp_format(self, mock_mkstemp, mock_popen):
        """Test that Vector subprocess receives timestamps in proper Unix seconds format."""
        mock_mkstemp.return_value = (5, '/tmp/vector-config-123.yaml')
        
        # Mock subprocess
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.communicate.return_value = ('Vector output', '')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        # Test with mixed timestamp formats
        log_events = [
            {"message": "Log 1", "timestamp": 1725108058000},  # Milliseconds
            {"message": "Log 2", "timestamp": 1725108059},     # Seconds
            {"message": "Log 3", "timestamp": 1725108060000}   # Milliseconds
        ]
        
        credentials = {
            'AccessKeyId': 'test-key',
            'SecretAccessKey': 'test-secret',
            'SessionToken': 'test-token'
        }
        
        # Mock file operations
        mocked_open = mock_open(read_data='mock config template')
        
        with patch('builtins.open', mocked_open), \
             patch('os.fdopen', mock_open()), \
             patch('os.path.exists', return_value=True), \
             patch('os.unlink'), \
             patch('shutil.rmtree'):
            
            log_processor.deliver_logs_with_vector(
                log_events=log_events,
                central_credentials=credentials,
                customer_role_arn='arn:aws:iam::987654321098:role/CustomerRole',
                external_id='123456789012',
                region='us-east-1',
                log_group='/aws/logs/test',
                log_stream='test-stream',
                session_id='test-session',
                s3_timestamp=1725108058000
            )
            
            # Verify subprocess was called
            assert mock_popen.called
            
            # Get the input sent to Vector via communicate()
            communicate_call = mock_process.communicate.call_args
            vector_input = communicate_call[1]['input']
            
            # Parse the NDJSON input to verify timestamp conversion
            lines = vector_input.strip().split('\n')
            assert len(lines) == 3
            
            # Check first event (millisecond timestamp converted to seconds)
            event1 = json.loads(lines[0])
            assert event1['message'] == "Log 1"
            assert event1['timestamp'] == 1725108058.0  # Converted from ms to seconds
            
            # Check second event (already in seconds)
            event2 = json.loads(lines[1])
            assert event2['message'] == "Log 2"
            assert event2['timestamp'] == 1725108059  # Should remain as seconds
            
            # Check third event (millisecond timestamp converted to seconds)
            event3 = json.loads(lines[2])
            assert event3['message'] == "Log 3"
            assert event3['timestamp'] == 1725108060.0  # Converted from ms to seconds