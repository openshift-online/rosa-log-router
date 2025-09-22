"""
Unit tests for metrics functionality in log_processor.py
"""
import pytest
from unittest.mock import patch, Mock, MagicMock
from moto import mock_aws
import boto3
import botocore.exceptions

# Import the module under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../container'))

from log_processor import push_metrics


class TestPushMetrics:
    """Test the push_metrics function."""
    
    @pytest.fixture
    def mock_aws_credentials(self):
        """Mocked AWS Credentials for moto."""
        os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
        os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
        os.environ['AWS_SECURITY_TOKEN'] = 'testing'
        os.environ['AWS_SESSION_TOKEN'] = 'testing'
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        
    @pytest.fixture
    def mock_aws_region(self):
        """Set AWS_REGION environment variable for tests."""
        original_region = os.environ.get('AWS_REGION')
        os.environ['AWS_REGION'] = 'us-east-1'
        yield 'us-east-1'
        if original_region is None:
            os.environ.pop('AWS_REGION', None)
        else:
            os.environ['AWS_REGION'] = original_region

    def test_push_metrics_successful_single_metric(self, mock_aws_credentials, mock_aws_region):
        """Test successful push of a single metric to CloudWatch."""
        with mock_aws():
            tenant_id = "test-tenant"
            method = "cloudwatch"
            metrics_data = {"successful_events": 100}
            
            result = push_metrics(tenant_id, method, metrics_data)
            
            # Verify the response structure (moto returns a mock response)
            assert isinstance(result, dict)
            assert 'ResponseMetadata' in result

    def test_push_metrics_successful_multiple_metrics(self, mock_aws_credentials, mock_aws_region):
        """Test successful push of multiple metrics to CloudWatch."""
        with mock_aws():
            tenant_id = "test-tenant"
            method = "cloudwatch"
            metrics_data = {
                "successful_events": 150,
                "failed_events": 5,
                "processing_time": 2.5
            }
            
            result = push_metrics(tenant_id, method, metrics_data)
            
            # Verify the response structure
            assert isinstance(result, dict)
            assert 'ResponseMetadata' in result

    @patch('log_processor.boto3.client')
    def test_push_metrics_cloudwatch_client_called_correctly(self, mock_boto3_client, mock_aws_region):
        """Test that CloudWatch client is called with correct parameters for single metric."""
        mock_cloudwatch_client = Mock()
        mock_cloudwatch_client.put_metric_data.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        mock_boto3_client.return_value = mock_cloudwatch_client
        
        tenant_id = "test-tenant"
        method = "cloudwatch"
        metrics_data = {"successful_events": 100}
        
        result = push_metrics(tenant_id, method, metrics_data)
        
        # Verify boto3.client was called correctly
        mock_boto3_client.assert_called_once_with('cloudwatch', region_name='us-east-1')
        
        # Verify put_metric_data was called
        mock_cloudwatch_client.put_metric_data.assert_called_once()
        
        # Verify the structure of the call
        call_args = mock_cloudwatch_client.put_metric_data.call_args
        assert call_args[1]['Namespace'] == 'Test/LogForwarding'
        assert len(call_args[1]['MetricData']) == 1
        assert call_args[1]['MetricData'][0]['MetricName'] == 'LogCount/cloudwatch/successful_events'
        assert call_args[1]['MetricData'][0]['Value'] == 100
        assert call_args[1]['MetricData'][0]['Unit'] == 'Count'

    @patch('log_processor.boto3.client')
    def test_push_metrics_multiple_metrics_structure(self, mock_boto3_client, mock_aws_region):
        """Test that multiple metrics are structured correctly in the CloudWatch call."""
        mock_cloudwatch_client = Mock()
        mock_cloudwatch_client.put_metric_data.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        mock_boto3_client.return_value = mock_cloudwatch_client
        
        tenant_id = "test-tenant"
        method = "cloudwatch"
        metrics_data = {
            "successful_events": 150,
            "failed_events": 5,
            "processing_time": 2.5
        }
        
        result = push_metrics(tenant_id, method, metrics_data)
        
        call_args = mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Should have 3 metrics
        assert len(metric_data) == 3
        
        # Check each metric exists (order may vary)
        metric_names = [metric['MetricName'] for metric in metric_data]
        assert 'LogCount/cloudwatch/successful_events' in metric_names
        assert 'LogCount/cloudwatch/failed_events' in metric_names
        assert 'LogCount/cloudwatch/processing_time' in metric_names
        
        # Verify tenant_id dimension is present in all metrics
        for metric in metric_data:
            assert any(dim['Name'] == 'Tenant' and dim['Value'] == 'test-tenant' 
                      for dim in metric['Dimensions'])

    @patch('log_processor.boto3.client')
    def test_push_metrics_client_error_handling(self, mock_boto3_client, mock_aws_region):
        """Test handling of CloudWatch client errors."""
        mock_cloudwatch_client = Mock()
        mock_cloudwatch_client.put_metric_data.side_effect = botocore.exceptions.ClientError(
            error_response={'Error': {'Code': 'ValidationException', 'Message': 'Invalid parameter'}},
            operation_name='PutMetricData'
        )
        mock_boto3_client.return_value = mock_cloudwatch_client
        
        tenant_id = "test-tenant"
        method = "cloudwatch"
        metrics_data = {"successful_events": 100}
        
        # Should raise the exception when there's an error
        with pytest.raises(botocore.exceptions.ClientError):
            push_metrics(tenant_id, method, metrics_data)

    @patch('log_processor.boto3.client')
    def test_push_metrics_generic_exception_handling(self, mock_boto3_client, mock_aws_region):
        """Test handling of generic exceptions during metric push."""
        mock_cloudwatch_client = Mock()
        mock_cloudwatch_client.put_metric_data.side_effect = Exception("Network error")
        mock_boto3_client.return_value = mock_cloudwatch_client
        
        tenant_id = "test-tenant"
        method = "cloudwatch"
        metrics_data = {"successful_events": 100}
        
        # Should raise the exception when there's an error
        with pytest.raises(Exception):
            push_metrics(tenant_id, method, metrics_data)

    @patch('log_processor.boto3.client')
    def test_push_metrics_empty_metrics_data(self, mock_boto3_client, mock_aws_region):
        """Test behavior when metrics_data is empty."""
        mock_cloudwatch_client = Mock()
        mock_cloudwatch_client.put_metric_data.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        mock_boto3_client.return_value = mock_cloudwatch_client
        
        tenant_id = "test-tenant"
        method = "cloudwatch"
        metrics_data = {}
        
        result = push_metrics(tenant_id, method, metrics_data)
        
        call_args = mock_cloudwatch_client.put_metric_data.call_args
        # Should still call CloudWatch but with empty MetricData
        assert call_args[1]['MetricData'] == []

    @patch('builtins.print')
    @patch('log_processor.boto3.client')
    def test_push_metrics_error_logging(self, mock_boto3_client, mock_print, mock_aws_region):
        """Test that errors are properly logged."""
        error_message = "Detailed error message"
        mock_cloudwatch_client = Mock()
        mock_cloudwatch_client.put_metric_data.side_effect = Exception(error_message)
        mock_boto3_client.return_value = mock_cloudwatch_client
        
        tenant_id = "test-tenant"
        method = "cloudwatch"
        metrics_data = {"successful_events": 100}
        
        # Should raise the exception and print error message
        with pytest.raises(Exception):
            push_metrics(tenant_id, method, metrics_data)
        
        # Verify error was printed/logged
        mock_print.assert_called()
        # Check that the error message appears in one of the print calls
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any(error_message in call_str for call_str in print_calls)

    def test_push_metrics_no_aws_region_env_var(self, mock_aws_credentials):
        """Test behavior when AWS_REGION environment variable is not set."""
        # Remove AWS_REGION if it exists
        original_region = os.environ.pop('AWS_REGION', None)
        
        try:
            tenant_id = "test-tenant"
            method = "cloudwatch"
            metrics_data = {"successful_events": 100}
            
            # Should raise an exception when AWS_REGION is not set
            with pytest.raises(Exception):
                push_metrics(tenant_id, method, metrics_data)
            
        finally:
            # Restore original AWS_REGION if it existed
            if original_region:
                os.environ['AWS_REGION'] = original_region

    @patch('log_processor.boto3.client')
    def test_push_metrics_namespace_is_correct(self, mock_boto3_client, mock_aws_region):
        """Test that the correct namespace is used for CloudWatch metrics."""
        mock_cloudwatch_client = Mock()
        mock_cloudwatch_client.put_metric_data.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        mock_boto3_client.return_value = mock_cloudwatch_client
        
        tenant_id = "test-tenant"
        method = "cloudwatch"
        metrics_data = {"successful_events": 100}
        
        push_metrics(tenant_id, method, metrics_data)
        
        call_args = mock_cloudwatch_client.put_metric_data.call_args
        assert call_args[1]['Namespace'] == 'Test/LogForwarding'