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
    get_tenant_configuration,
    should_process_application,
    should_process_tenant,
    download_and_process_log_file,
    process_json_file,
    convert_log_record_to_event,
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
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'tenant_id',
                    'AttributeType': 'S'
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Add test tenant configurations
        table.put_item(Item={
            'tenant_id': 'acme-corp',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole',
            'log_group_name': '/aws/logs/acme-corp',
            'target_region': 'us-east-1',
            'enabled': True,
            'desired_logs': ['payment-service', 'user-service']
        })
        
        table.put_item(Item={
            'tenant_id': 'disabled-tenant',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole',
            'log_group_name': '/aws/logs/disabled',
            'target_region': 'us-east-1',
            'enabled': False
        })
        
        table.put_item(Item={
            'tenant_id': 'missing-fields',
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole'
            # Missing required fields
        })
        
        return table
    
    def test_get_tenant_configuration_success(self, environment_variables, dynamodb_table):
        """Test successful tenant configuration retrieval."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            config = get_tenant_configuration('acme-corp')
        
        assert config['tenant_id'] == 'acme-corp'
        assert config['log_distribution_role_arn'] == 'arn:aws:iam::987654321098:role/LogRole'
        assert config['log_group_name'] == '/aws/logs/acme-corp'
        assert config['target_region'] == 'us-east-1'
        assert config['enabled'] is True
        assert config['desired_logs'] == ['payment-service', 'user-service']
    
    def test_get_tenant_configuration_not_found(self, environment_variables, dynamodb_table):
        """Test tenant configuration not found."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            with pytest.raises(TenantNotFoundError) as exc_info:
                get_tenant_configuration('nonexistent-tenant')
        
        assert "No configuration found for tenant: nonexistent-tenant" in str(exc_info.value)
    
    def test_get_tenant_configuration_missing_required_fields(self, environment_variables, dynamodb_table):
        """Test tenant configuration with missing required fields."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            with pytest.raises(TenantNotFoundError) as exc_info:
                get_tenant_configuration('missing-fields')
        
        assert "missing required field" in str(exc_info.value)
    
    def test_should_process_tenant_enabled(self, environment_variables, dynamodb_table):
        """Test should_process_tenant with enabled tenant."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            config = get_tenant_configuration('acme-corp')
        assert should_process_tenant(config, 'acme-corp') is True
    
    def test_should_process_tenant_disabled(self, environment_variables, dynamodb_table):
        """Test should_process_tenant with disabled tenant."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            config = get_tenant_configuration('disabled-tenant')
        assert should_process_tenant(config, 'disabled-tenant') is False
    
    def test_should_process_application_with_desired_logs(self, environment_variables, dynamodb_table):
        """Test application filtering with desired_logs configuration."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            config = get_tenant_configuration('acme-corp')
        
        assert should_process_application(config, 'payment-service') is True
        assert should_process_application(config, 'user-service') is True
        assert should_process_application(config, 'admin-service') is False
    
    def test_should_process_application_case_insensitive(self, environment_variables, dynamodb_table):
        """Test application filtering is case insensitive."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            config = get_tenant_configuration('acme-corp')
        
        assert should_process_application(config, 'Payment-Service') is True
        assert should_process_application(config, 'USER-SERVICE') is True
    
    def test_should_process_application_no_filtering(self, environment_variables, dynamodb_table):
        """Test application processing when no desired_logs is specified."""
        with patch('log_processor.TENANT_CONFIG_TABLE', 'test-tenant-configs'):
            config = get_tenant_configuration('disabled-tenant')
        
        # Remove desired_logs to test default behavior
        if 'desired_logs' in config:
            del config['desired_logs']
        
        assert should_process_application(config, 'any-service') is True


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
        """Test converting log record with timestamp."""
        log_record = {
            "timestamp": "2024-01-01T10:00:00Z",
            "message": "Test log message"
        }
        
        event = convert_log_record_to_event(log_record)
        
        assert event is not None
        assert event['message'] == 'Test log message'
        # The timestamp should be around 2024-01-01T10:00:00Z, allow some tolerance for timezone conversion
        assert 1704099600000 <= event['timestamp'] <= 1704103200000
    
    @freeze_time("2024-01-01 12:00:00")
    def test_convert_log_record_to_event_without_timestamp(self):
        """Test converting log record without timestamp."""
        log_record = {"message": "Test log message"}
        
        event = convert_log_record_to_event(log_record)
        
        assert event is not None
        assert event['message'] == 'Test log message'
        assert event['timestamp'] == 1704110400000  # Current time in ms
    
    def test_convert_log_record_to_event_no_message(self):
        """Test converting log record without message field."""
        log_record = {"timestamp": "2024-01-01T10:00:00Z", "data": "some data"}
        
        event = convert_log_record_to_event(log_record)
        
        assert event is not None
        assert json.loads(event['message']) == log_record  # Entire record as JSON


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
        
        with patch('log_processor.get_tenant_configuration') as mock_get_tenant, \
             patch('log_processor.download_and_process_log_file') as mock_download, \
             patch('log_processor.deliver_logs_to_customer') as mock_deliver:
            
            mock_get_tenant.return_value = {
                'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/LogRole',
                'log_group_name': '/aws/logs/acme-corp',
                'target_region': 'us-east-1',
                'enabled': True
            }
            mock_download.return_value = ([{"message": "test", "timestamp": 1234567890}], 1234567890)
            mock_deliver.return_value = None
            
            # Should not raise an exception
            log_processor.process_sqs_record(sqs_record)
            
            mock_get_tenant.assert_called_once_with('acme-corp')
            mock_download.assert_called_once()
            mock_deliver.assert_called_once()
    
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
        
        with patch('log_processor.get_tenant_configuration') as mock_get_tenant:
            mock_get_tenant.side_effect = TenantNotFoundError("Tenant not found")
            
            # Should not raise an exception (handled as non-recoverable)
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
            mock_process.return_value = None
            
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
            mock_process.side_effect = [None, Exception("Recoverable error")]
            
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
                credentials=credentials,
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
                credentials=credentials,
                region='us-east-1',
                log_group='/aws/logs/test',
                log_stream='test-stream',
                session_id='test-session',
                s3_timestamp=1234567890
            )
        
        assert "Vector exited with non-zero code 1" in str(exc_info.value)


class TestCrossAccountRoleAssumption:
    """Test cross-account role assumption functionality."""
    
    @patch('boto3.client')
    def test_deliver_logs_to_customer_double_hop(self, mock_boto_client, environment_variables):
        """Test double-hop role assumption for log delivery."""
        # Mock STS clients
        mock_sts_client = Mock()
        mock_central_sts_client = Mock()
        
        # Mock role assumption responses
        central_role_response = {
            'Credentials': {
                'AccessKeyId': 'central-key',
                'SecretAccessKey': 'central-secret',
                'SessionToken': 'central-token'
            }
        }
        
        customer_role_response = {
            'Credentials': {
                'AccessKeyId': 'customer-key',
                'SecretAccessKey': 'customer-secret',
                'SessionToken': 'customer-token'
            }
        }
        
        mock_sts_client.assume_role.return_value = central_role_response
        mock_sts_client.get_caller_identity.return_value = {'Account': '123456789012'}
        mock_central_sts_client.assume_role.return_value = customer_role_response
        
        # Setup boto3.client to return appropriate clients
        def mock_client_factory(service, **kwargs):
            if service == 'sts':
                if 'aws_access_key_id' in kwargs:
                    return mock_central_sts_client
                else:
                    return mock_sts_client
            return Mock()
        
        mock_boto_client.side_effect = mock_client_factory
        
        log_events = [{"message": "Test log", "timestamp": 1234567890}]
        tenant_config = {
            'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/CustomerRole',
            'log_group_name': '/aws/logs/customer',
            'target_region': 'us-east-1'
        }
        tenant_info = {
            'tenant_id': 'test-tenant',
            'pod_name': 'test-pod'
        }
        
        with patch('log_processor.deliver_logs_with_vector') as mock_vector_delivery:
            log_processor.deliver_logs_to_customer(
                log_events=log_events,
                tenant_config=tenant_config,
                tenant_info=tenant_info,
                s3_timestamp=1234567890
            )
            
            # Verify role assumptions were called correctly
            mock_sts_client.assume_role.assert_called_once()
            mock_central_sts_client.assume_role.assert_called_once()
            
            # Verify Vector delivery was called with customer credentials
            mock_vector_delivery.assert_called_once()
            call_args = mock_vector_delivery.call_args
            assert call_args[1]['credentials'] == customer_role_response['Credentials']