#!/usr/bin/env python3
"""
Unified log processor for multi-tenant logging pipeline
Supports Lambda runtime, SQS polling, and manual input modes
"""

import argparse
import gzip
import json
import logging
import os
import sys
import time
import urllib.parse
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

import boto3
from botocore.exceptions import ClientError

# Add shared utilities to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../shared'))
try:
    from validation_utils import normalize_bucket_prefix
except ImportError:
    # Fallback for cases where shared module isn't available
    def normalize_bucket_prefix(prefix: str) -> str:
        if prefix and not prefix.endswith('/'):
            return prefix + '/'
        return prefix

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Vector metadata fields to exclude when creating fallback messages
VECTOR_METADATA_FIELDS = {
    'cluster_id', 'namespace', 'application', 'pod_name',
    'ingest_timestamp', 'timestamp', 'kubernetes'
}

# Application group definitions for filtering
# Each group key maps to a list of application names that belong to that group
APPLICATION_GROUPS = {
    'API': ['kube-apiserver', 'openshift-apiserver'],
    'Authentication': ['oauth-server', 'oauth-apiserver'],
    'Controller Manager': ['kube-controller-manager', 'openshift-controller-manager', 'openshift-route-controller-manager'],
    'Scheduler': ['kube-scheduler']
}

# Custom exception classes
class NonRecoverableError(Exception):
    """Exception for errors that should not be retried (e.g., missing tenant config)"""
    pass

class TenantNotFoundError(NonRecoverableError):
    """Exception for when tenant configuration is not found"""
    pass

class InvalidS3NotificationError(NonRecoverableError):
    """Exception for invalid S3 notifications that cannot be processed"""
    pass

# For Lambda, we need to ensure the root logger and all handlers are set to INFO
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Set all existing handlers to INFO level (Lambda adds its own handler)
for handler in root_logger.handlers:
    handler.setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
TENANT_CONFIG_TABLE = os.environ.get('TENANT_CONFIG_TABLE', 'tenant-configurations')
MAX_BATCH_SIZE = int(os.environ.get('MAX_BATCH_SIZE', '1000'))
RETRY_ATTEMPTS = int(os.environ.get('RETRY_ATTEMPTS', '3'))
CENTRAL_LOG_DISTRIBUTION_ROLE_ARN = os.environ.get('CENTRAL_LOG_DISTRIBUTION_ROLE_ARN')
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    AWS Lambda handler for processing SQS messages containing S3 events
    
    Returns batchItemFailures to enable partial batch failure handling.
    Failed messages will be retried by SQS.
    """
    batch_item_failures = []
    successful_records = 0
    failed_records = 0
    total_successful_deliveries = 0
    total_failed_deliveries = 0

    logger.info(f"Processing {len(event.get('Records', []))} SQS messages")

    for record in event.get('Records', []):
        try:
            delivery_stats = process_sqs_record(record)
            successful_records += 1
            # Handle case where delivery_stats might be None (shouldn't happen but defensive coding)
            if delivery_stats:
                total_successful_deliveries += delivery_stats.get('successful_deliveries', 0)
                total_failed_deliveries += delivery_stats.get('failed_deliveries', 0)
        except NonRecoverableError as e:
            # Non-recoverable errors should not be retried
            logger.warning(f"Non-recoverable error processing record {record.get('messageId', 'unknown')}: {str(e)}. Message will be removed from queue.")
            successful_records += 1  # Count as successful to remove from queue
        except Exception as e:
            # Recoverable errors should be retried
            logger.error(f"Recoverable error processing record {record.get('messageId', 'unknown')}: {str(e)}. Message will be retried.", exc_info=True)
            failed_records += 1

            # Add failed message ID to batch item failures
            # This tells Lambda to not delete this message from SQS
            if 'messageId' in record:
                batch_item_failures.append({
                    'itemIdentifier': record['messageId']
                })

    logger.info(f"Processing complete. Records: Success: {successful_records}, Failed: {failed_records}. Deliveries: Success: {total_successful_deliveries}, Failed: {total_failed_deliveries}")

    # Return partial batch failure response
    # This ensures failed messages remain in the queue for retry
    return {
        'batchItemFailures': batch_item_failures
    }

def sqs_polling_mode():
    """
    SQS polling mode for local testing
    Continuously polls SQS queue and processes messages
    """
    if not SQS_QUEUE_URL:
        logger.error("SQS_QUEUE_URL environment variable not set")
        sys.exit(1)

    sqs_client = boto3.client('sqs', region_name=AWS_REGION)
    logger.info(f"Starting SQS polling mode for queue: {SQS_QUEUE_URL}")

    while True:
        try:
            # Poll for messages
            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,  # Long polling
                VisibilityTimeout=300
            )

            messages = response.get('Messages', [])
            if not messages:
                logger.info("No messages received, continuing to poll...")
                continue

            logger.info(f"Received {len(messages)} messages from SQS")

            for message in messages:
                should_delete_message = False
                try:
                    # Convert SQS message to Lambda record format
                    lambda_record = {
                        'body': message['Body'],
                        'messageId': message['MessageId'],
                        'receiptHandle': message['ReceiptHandle']
                    }

                    delivery_stats = process_sqs_record(lambda_record)
                    should_delete_message = True  # Successfully processed
                    if delivery_stats:
                        logger.info(f"Message processed. Deliveries: Success: {delivery_stats.get('successful_deliveries', 0)}, Failed: {delivery_stats.get('failed_deliveries', 0)}")
                    else:
                        logger.info("Message processed successfully")

                except NonRecoverableError as e:
                    logger.warning(f"Non-recoverable error processing message {message.get('MessageId', 'unknown')}: {str(e)}. Message will be deleted to prevent infinite retries.")
                    should_delete_message = True  # Delete to prevent infinite retries

                except Exception as e:
                    logger.error(f"Recoverable error processing message {message.get('MessageId', 'unknown')}: {str(e)}. Message will be retried.")
                    should_delete_message = False  # Don't delete - allow retry

                # Delete message if processing succeeded or if error is non-recoverable
                if should_delete_message:
                    try:
                        sqs_client.delete_message(
                            QueueUrl=SQS_QUEUE_URL,
                            ReceiptHandle=message['ReceiptHandle']
                        )
                        logger.info(f"Successfully deleted message {message['MessageId']}")
                    except Exception as delete_error:
                        logger.error(f"Failed to delete message {message['MessageId']}: {str(delete_error)}")
                        # Continue processing other messages even if delete fails

        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in SQS polling: {str(e)}")
            time.sleep(5)  # Wait before retrying

def manual_input_mode():
    """
    Manual input mode for development/testing
    Reads JSON input from stdin and processes it
    """
    logger.info("Manual input mode - reading JSON from stdin")
    logger.info("Expected format: SQS message body containing SNS message with S3 event")

    try:
        input_data = sys.stdin.read().strip()
        if not input_data:
            logger.error("No input data provided")
            sys.exit(1)

        # Parse input as SQS message body
        lambda_record = {
            'body': input_data,
            'messageId': 'manual-input',
            'receiptHandle': 'manual'
        }

        delivery_stats = process_sqs_record(lambda_record)
        if delivery_stats:
            logger.info(f"Successfully processed manual input. Deliveries: Success: {delivery_stats.get('successful_deliveries', 0)}, Failed: {delivery_stats.get('failed_deliveries', 0)}")
        else:
            logger.info("Successfully processed manual input")

    except Exception as e:
        logger.error(f"Error processing manual input: {str(e)}")
        sys.exit(1)

def process_sqs_record(sqs_record: Dict[str, Any]) -> Dict[str, int]:
    """
    Process a single SQS record containing S3 event notification
    Returns delivery success/failure counts for accurate metrics
    """
    delivery_stats = {'successful_deliveries': 0, 'failed_deliveries': 0}
    try:
        # Parse the SQS message body (SNS message)
        try:
            sns_message = json.loads(sqs_record['body'])
            s3_event = json.loads(sns_message['Message'])
        except (json.JSONDecodeError, KeyError) as e:
            raise InvalidS3NotificationError(f"Invalid SQS message format: {str(e)}")

        # Extract S3 event details
        for s3_record in s3_event['Records']:
            try:
                bucket_name = s3_record['s3']['bucket']['name']
                object_key = urllib.parse.unquote_plus(s3_record['s3']['object']['key'])
            except KeyError as e:
                raise InvalidS3NotificationError(f"Invalid S3 event format: missing {str(e)}")

            logger.info(f"Processing S3 object: s3://{bucket_name}/{object_key}")

            try:
                # Extract tenant information from object key
                tenant_info = extract_tenant_info_from_key(object_key)

                # Get all enabled delivery configurations for this tenant
                delivery_configs = get_tenant_delivery_configs(tenant_info['tenant_id'])

                # Process each delivery configuration independently with its own filtering
                for delivery_config in delivery_configs:
                    delivery_type = delivery_config['type']

                    try:
                        # Check if this delivery configuration should be processed
                        if not should_process_delivery_config(delivery_config, tenant_info['tenant_id'], delivery_type):
                            logger.info(f"Skipping {delivery_type} delivery for tenant '{tenant_info['tenant_id']}' because it is disabled")
                            continue

                        # Check if this application should be processed based on THIS config's desired_logs filtering
                        if not should_process_application(delivery_config, tenant_info['application']):
                            logger.info(f"Skipping {delivery_type} delivery for application '{tenant_info['application']}' due to desired_logs filtering")
                            continue

                        # This specific delivery config should process this application
                        logger.info(f"Processing {delivery_type} delivery for tenant '{tenant_info['tenant_id']}' application '{tenant_info['application']}'")

                        # Deliver logs based on delivery type with independent processing
                        if delivery_type == 'cloudwatch':
                            # CloudWatch requires downloading and processing log events
                            log_events, s3_timestamp = download_and_process_log_file(bucket_name, object_key)

                            # Check for processing offset and skip already processed events
                            processing_metadata = extract_processing_metadata(sqs_record)
                            offset = processing_metadata.get('offset', 0)

                            if offset > 0:
                                logger.info(f"Found processing offset {offset}, skipping already processed events")
                                log_events = should_skip_processed_events(log_events, offset)

                            if log_events:  # Only process if there are events remaining
                                deliver_logs_to_cloudwatch(log_events, delivery_config, tenant_info, s3_timestamp)
                                delivery_stats['successful_deliveries'] += 1
                            else:
                                logger.info("All events already processed, skipping delivery")
                                delivery_stats['successful_deliveries'] += 1

                        elif delivery_type == 's3':
                            # S3 delivery uses direct S3-to-S3 copy, no download needed
                            try:
                                deliver_logs_to_s3(bucket_name, object_key, delivery_config, tenant_info)
                                try:
                                    push_metrics(tenant_info['tenant_id'], "s3", {"successful_delivery": 1})
                                except Exception as metric_e:
                                    logger.error(f"Failed to write metrics to CW for S3 for tenant {tenant_info['tenant_id']} :{str(metric_e)}")
                            except Exception as e:
                                try:
                                    push_metrics(tenant_info['tenant_id'], "s3", {"failed_delivery": 1})
                                except Exception as metric_e:
                                    logger.error(f"Failed to write metrics to CW for S3 for tenant {tenant_info['tenant_id']} :{str(metric_e)}")
                                raise
                            delivery_stats['successful_deliveries'] += 1
                        else:
                            logger.error(f"Unknown delivery type '{delivery_type}' for tenant '{tenant_info['tenant_id']}' - skipping")
                            delivery_stats['unknown_delivery_types'] = delivery_stats.get('unknown_delivery_types', 0) + 1

                    except Exception as delivery_error:
                        logger.error(f"Failed to deliver logs via {delivery_type} for tenant '{tenant_info['tenant_id']}': {str(delivery_error)}")
                        delivery_stats['failed_deliveries'] += 1

                        # For CloudWatch failures, try to re-queue with offset if possible
                        if delivery_type == 'cloudwatch' and 'receiptHandle' in sqs_record:
                            try:
                                # Calculate how many events were successfully processed
                                processing_metadata = extract_processing_metadata(sqs_record)
                                current_offset = processing_metadata.get('offset', 0)

                                # For now, assume partial success isn't trackable, so retry from current offset
                                # In a more sophisticated implementation, we could track exactly which events failed
                                requeue_sqs_message_with_offset(
                                    message_body=sqs_record['body'],
                                    original_receipt_handle=sqs_record.get('receiptHandle', ''),
                                    processing_offset=current_offset,
                                    max_retries=3
                                )
                                logger.info(f"Re-queued message for retry with offset {current_offset}")
                            except Exception as requeue_error:
                                logger.error(f"Failed to re-queue message: {str(requeue_error)}")

                        # Continue with other delivery types even if one fails

            except TenantNotFoundError as e:
                logger.warning(f"Tenant not found for S3 object {object_key}: {str(e)}. Message will be removed from queue.")
                # Don't re-raise - this is a non-recoverable error
            except InvalidS3NotificationError as e:
                logger.warning(f"Invalid S3 notification for object {object_key}: {str(e)}. Message will be removed from queue.")
                # Don't re-raise - this is a non-recoverable error
            except NonRecoverableError as e:
                logger.warning(f"Non-recoverable error processing S3 object {object_key}: {str(e)}. Message will be removed from queue.")
                # Don't re-raise - this is a non-recoverable error
            except Exception as e:
                logger.error(f"Recoverable error processing S3 object {object_key}: {str(e)}. Message will be retried.")
                raise  # Re-raise recoverable errors for retry

    except NonRecoverableError as e:
        logger.warning(f"Non-recoverable error processing SQS record: {str(e)}. Message will be removed from queue.")
        # Don't re-raise - this is a non-recoverable error
    except Exception as e:
        logger.error(f"Recoverable error processing SQS record: {str(e)}. Message will be retried.")
        raise  # Re-raise recoverable errors for retry

    return delivery_stats

def extract_tenant_info_from_key(object_key: str) -> Dict[str, str]:
    """
    Extract tenant information from S3 object key path
    Expected format (from Vector): cluster_id/namespace/application/pod_name/timestamp-uuid.json.gz
    
    Where:
    - cluster_id: Management cluster ID (from CLUSTER_ID env var in Vector)  
    - namespace: Kubernetes pod namespace (used as tenant_id for delivery configuration lookup)
    - application: Application name from pod labels
    - pod_name: Kubernetes pod name
    """
    path_parts = object_key.split('/')

    if len(path_parts) < 5:
        raise InvalidS3NotificationError(f"Invalid object key format. Expected at least 5 path segments, got {len(path_parts)}: {object_key}")

    # Validate that required path segments are not empty (handles double slashes in paths)
    required_segments = ['cluster_id', 'namespace', 'application', 'pod_name']
    for i, segment_name in enumerate(required_segments):
        if not path_parts[i] or path_parts[i].strip() == '':
            raise InvalidS3NotificationError(f"Invalid object key format. {segment_name} (segment {i}) cannot be empty: {object_key}")

    # Vector schema: cluster_id/namespace/application/pod_name/file.gz
    # Use namespace as tenant_id for DynamoDB delivery configuration lookup
    tenant_info = {
        'cluster_id': path_parts[0],        # Management cluster ID from Vector CLUSTER_ID env var
        'namespace': path_parts[1],         # Kubernetes pod namespace from Vector
        'tenant_id': path_parts[1],         # Use namespace as tenant_id for DynamoDB lookup
        'application': path_parts[2],       # Application name from pod labels
        'pod_name': path_parts[3],          # Kubernetes pod name
        'environment': 'production'
    }

    # Extract environment from cluster_id if it contains it
    if '-' in tenant_info['cluster_id']:
        env_prefix = tenant_info['cluster_id'].split('-')[0]
        env_map = {'prod': 'production', 'stg': 'staging', 'dev': 'development'}
        tenant_info['environment'] = env_map.get(env_prefix, 'production')

    # Log extracted values to help debug any schema mismatches
    logger.info(f"Extracted tenant info from S3 key '{object_key}':")
    logger.info(f"  cluster_id: '{tenant_info['cluster_id']}' (management cluster from Vector CLUSTER_ID)")
    logger.info(f"  namespace: '{tenant_info['namespace']}' (Kubernetes pod namespace from Vector)")
    logger.info(f"  tenant_id: '{tenant_info['tenant_id']}' (using namespace as tenant_id for DynamoDB lookup)")
    logger.info(f"  application: '{tenant_info['application']}', pod_name: '{tenant_info['pod_name']}'")

    return tenant_info

def validate_tenant_delivery_config(config: Dict[str, Any], tenant_id: str) -> None:
    """
    Validate that tenant delivery configuration contains all required fields for its type
    """
    delivery_type = config.get('type')
    if not delivery_type:
        raise TenantNotFoundError(f"Tenant {tenant_id} delivery configuration missing 'type' field")

    if delivery_type == 'cloudwatch':
        required_fields = ['log_distribution_role_arn', 'log_group_name']
        for field in required_fields:
            if field not in config:
                raise TenantNotFoundError(f"Tenant {tenant_id} CloudWatch delivery config missing required field: {field}")

            value = config[field]
            if not value or (isinstance(value, str) and not value.strip()):
                raise TenantNotFoundError(f"Tenant {tenant_id} CloudWatch delivery config has empty or invalid value for required field: {field}")

    elif delivery_type == 's3':
        required_fields = ['bucket_name']
        for field in required_fields:
            if field not in config:
                raise TenantNotFoundError(f"Tenant {tenant_id} S3 delivery config missing required field: {field}")

            value = config[field]
            if not value or (isinstance(value, str) and not value.strip()):
                raise TenantNotFoundError(f"Tenant {tenant_id} S3 delivery config has empty or invalid value for required field: {field}")

    else:
        raise TenantNotFoundError(f"Tenant {tenant_id} has invalid delivery type: {delivery_type}")

def get_tenant_delivery_configs(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all tenant delivery configurations from DynamoDB and filter for enabled ones.
    
    This function queries all delivery configurations for a tenant and then filters
    them to return only the enabled ones internally.
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(TENANT_CONFIG_TABLE)

        # Query all delivery configurations for this tenant
        response = table.query(
            KeyConditionExpression='tenant_id = :tenant_id',
            ExpressionAttributeValues={
                ':tenant_id': tenant_id
            }
        )

        configs = response.get('Items', [])
        if not configs:
            raise TenantNotFoundError(f"No delivery configurations found for tenant: {tenant_id}")

        # Filter for enabled configurations (default to True if not present)
        enabled_configs = []
        for config in configs:
            if config.get('enabled', True):
                # Validate required fields for each delivery type
                validate_tenant_delivery_config(config, tenant_id)
                enabled_configs.append(dict(config))

        if not enabled_configs:
            raise TenantNotFoundError(f"No enabled delivery configurations found for tenant: {tenant_id}")

        # Log configuration details
        config_types = [config['type'] for config in enabled_configs]
        logger.info(f"Retrieved {len(enabled_configs)} enabled delivery config(s) for tenant {tenant_id}: {config_types}")

        for config in enabled_configs:
            desired_logs = config.get('desired_logs')
            if desired_logs:
                logger.info(f"  {config['type']} delivery with desired_logs filtering: {desired_logs}")
            else:
                logger.info(f"  {config['type']} delivery (no desired_logs filtering - all applications will be processed)")

        return enabled_configs

    except TenantNotFoundError:
        # Re-raise TenantNotFoundError as-is
        raise
    except Exception as e:
        # Handle DynamoDB ValidationException for empty string keys (from malformed S3 paths)
        if 'ValidationException' in str(e) and 'empty string value' in str(e):
            logger.warning(f"Invalid tenant_id (empty string) for DynamoDB lookup: '{tenant_id}'. This indicates a malformed S3 object path.")
            raise TenantNotFoundError(f"Invalid tenant_id (empty string) from malformed S3 path")

        logger.error(f"Failed to get tenant delivery configurations for {tenant_id}: {str(e)}")
        raise

def expand_groups_to_applications(groups: List[str]) -> List[str]:
    """
    Expand group names to their corresponding application lists
    
    Args:
        groups: List of group names to expand
        
    Returns:
        List of application names from all specified groups
    """
    expanded_applications = []
    
    for group in groups:
        if not isinstance(group, str):
            logger.warning(f"Group name is not a string: {type(group)}. Skipping.")
            continue
            
        # Case-insensitive group lookup
        group_found = False
        for key, applications in APPLICATION_GROUPS.items():
            if key.lower() == group.lower():
                expanded_applications.extend(applications)
                logger.info(f"Expanded group '{group}' to applications: {applications}")
                group_found = True
                break
        
        if not group_found:
            logger.warning(f"Group '{group}' not found in APPLICATION_GROUPS dictionary. Available groups: {list(APPLICATION_GROUPS.keys())}")
    
    return expanded_applications

def should_process_application(delivery_config: Dict[str, Any], application_name: str) -> bool:
    """
    Check if the application should be processed based on delivery configuration's desired_logs and groups
    
    Args:
        delivery_config: Delivery configuration from DynamoDB
        application_name: Name of the application from S3 object key
    
    Returns:
        True if application should be processed, False if it should be filtered out
    """
    desired_logs = delivery_config.get('desired_logs')
    groups = delivery_config.get('groups')

    # If neither desired_logs nor groups specified, process all applications (backward compatibility)
    if not desired_logs and not groups:
        return True

    # Collect all allowed applications from both desired_logs and groups
    allowed_applications = []
    
    # Process desired_logs field
    if desired_logs:
        if not isinstance(desired_logs, list):
            logger.warning(f"desired_logs is not a list: {type(desired_logs)}. Ignoring desired_logs field.")
        else:
            # Add applications from desired_logs
            allowed_applications.extend([log for log in desired_logs if isinstance(log, str)])
    
    # Process groups field
    if groups:
        if not isinstance(groups, list):
            logger.warning(f"groups is not a list: {type(groups)}. Ignoring groups field.")
        else:
            # Expand groups to applications and add them
            expanded_applications = expand_groups_to_applications(groups)
            allowed_applications.extend(expanded_applications)
    
    # If we still have no allowed applications after processing, process all applications
    if not allowed_applications:
        logger.warning("No valid applications found in desired_logs or groups. Processing all applications.")
        return True
    
    # Remove duplicates (case-sensitive application matching)
    unique_allowed_applications = list(set(allowed_applications))

    should_process = application_name in unique_allowed_applications

    if should_process:
        logger.info(f"Application '{application_name}' matches filtering criteria - will process")
    else:
        logger.info(f"Application '{application_name}' does NOT match filtering criteria - will skip processing")
        logger.debug(f"Allowed applications: {sorted(unique_allowed_applications)}")

    return should_process

def should_process_delivery_config(delivery_config: Dict[str, Any], tenant_id: str, delivery_type: str) -> bool:
    """
    Check if the delivery configuration should be processed based on enabled status
    
    Args:
        delivery_config: Delivery configuration from DynamoDB
        tenant_id: ID of the tenant
        delivery_type: Type of delivery configuration
    
    Returns:
        True if delivery config should be processed, False if it should be filtered out
    """
    enabled = delivery_config.get('enabled', True)  # Default to True if not present

    if enabled:
        logger.info(f"Tenant '{tenant_id}' {delivery_type} delivery is enabled - will process logs")
    else:
        logger.info(f"Tenant '{tenant_id}' {delivery_type} delivery is disabled - will skip processing")

    return enabled

def download_and_process_log_file(bucket_name: str, object_key: str) -> tuple[List[Dict[str, Any]], int]:
    """
    Download log file from S3 and extract log events
    Returns tuple of (log_events, s3_timestamp_ms)
    """
    try:
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response['Body'].read()

        # Extract S3 object timestamp for more accurate fallback timestamp
        s3_last_modified = response['LastModified']
        s3_timestamp_ms = int(s3_last_modified.timestamp() * 1000)
        logger.info(f"S3 object timestamp: {s3_last_modified} ({s3_timestamp_ms}ms)")

        logger.info(f"Downloaded file size: {len(file_content)} bytes (compressed)")

        # Decompress if gzipped
        if object_key.endswith('.gz'):
            file_content = gzip.decompress(file_content)
            logger.info(f"Decompressed file size: {len(file_content)} bytes")

        # Log first 500 characters of the file for debugging
        sample = file_content[:500].decode('utf-8', errors='replace')
        logger.info(f"File content sample (first 500 chars): {sample}")

        log_events = process_json_file(file_content)
        return log_events, s3_timestamp_ms

    except Exception as e:
        logger.error(f"Failed to download/process file s3://{bucket_name}/{object_key}: {str(e)}")
        raise

def process_json_file(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Process JSON file content and extract log events
    Prioritizes Vector's NDJSON (line-delimited JSON) format with JSON array fallback
    """
    try:
        log_events = []
        content = file_content.decode('utf-8')

        lines = content.strip().split('\n')
        logger.info(f"File contains {len(lines)} lines")

        # Try line-delimited JSON first (Vector NDJSON format)
        line_parse_success = 0
        line_parse_errors = 0

        for line_num, line in enumerate(lines):
            if line:
                try:
                    parsed_data = json.loads(line)
                    line_parse_success += 1

                    # Handle if the line is a JSON array
                    if isinstance(parsed_data, list):
                        logger.info(f"Line {line_num} is a JSON array with {len(parsed_data)} items")
                        for idx, log_record in enumerate(parsed_data):
                            if idx == 0 and line_num == 0:
                                if isinstance(log_record, dict):
                                    logger.info(f"First log record keys: {list(log_record.keys())}")
                                    logger.info(f"First log record sample: {str(log_record)[:200]}...")
                            event = convert_log_record_to_event(log_record)
                            if event:
                                log_events.append(event)
                    else:
                        # Single log record
                        if line_num == 0 and isinstance(parsed_data, dict):
                            logger.info(f"First log record keys: {list(parsed_data.keys())}")
                            logger.info(f"First log record sample: {str(parsed_data)[:200]}...")
                        event = convert_log_record_to_event(parsed_data)
                        if event:
                            log_events.append(event)
                        else:
                            logger.debug(f"Line {line_num}: convert_log_record_to_event returned None")
                except json.JSONDecodeError as e:
                    line_parse_errors += 1
                    if line_num < 3:  # Log first few parse errors
                        logger.warning(f"Line {line_num} JSON parse error: {str(e)}, content: {line[:100]}...")

        logger.info(f"Line parsing results: {line_parse_success} successful, {line_parse_errors} errors")

        # If no events found via line parsing, try fallback methods
        if len(log_events) == 0 and line_parse_errors > 0:
            logger.info("No events from line parsing, trying fallback JSON parsing")
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    logger.info(f"Parsed as JSON array with {len(data)} items")
                    for log_record in data:
                        event = convert_log_record_to_event(log_record)
                        if event:
                            log_events.append(event)
                else:
                    # Single JSON object
                    logger.info("Parsed as single JSON object")
                    event = convert_log_record_to_event(data)
                    if event:
                        log_events.append(event)
            except json.JSONDecodeError as e:
                logger.error(f"Fallback JSON parsing failed: {str(e)}")

        logger.info(f"Processed {len(log_events)} log events from JSON file")
        return log_events

    except Exception as e:
        logger.error(f"Failed to process JSON file: {str(e)}")
        raise

def convert_log_record_to_event(log_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert log record to CloudWatch Logs event format
    
    Uses the parsed log timestamp for CloudWatch delivery and preserves original message content.
    JSON messages are delivered as JSON objects to CloudWatch, not escaped strings.
    """
    try:
        # Use the actual log timestamp for CloudWatch delivery
        # ingest_timestamp is only for metadata - CloudWatch gets the real log timestamp
        timestamp = log_record.get('timestamp')
        if timestamp:
            if isinstance(timestamp, str):
                try:
                    # Handle ISO format timestamps
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    # Fallback to current time
                    timestamp_ms = int(datetime.now().timestamp() * 1000)
            else:
                # Handle numeric timestamps
                timestamp_ms = int(timestamp * 1000) if timestamp < 1e12 else int(timestamp)
        else:
            timestamp_ms = int(datetime.now().timestamp() * 1000)

        # Extract message from the structured log record
        # Vector preserves the original log content in the 'message' field
        # This could be JSON (dict/list) or plain text (string)
        message = log_record.get('message', '')

        if not message:
            # Fallback: if no message field, use the entire record (excluding Vector metadata)
            # Remove Vector control fields to get clean log data
            message = {k: v for k, v in log_record.items()
                      if k not in VECTOR_METADATA_FIELDS}

        # Keep JSON as JSON objects for CloudWatch - don't escape to strings
        # CloudWatch Logs will receive actual JSON structure, not escaped JSON strings
        return {
            'timestamp': timestamp_ms,
            'message': message  # Preserve JSON structure or plain text as-is
        }
    except Exception as e:
        logger.warning(f"Failed to convert log record: {str(e)}, record: {str(log_record)[:200]}...")
        return None

def deliver_logs_to_cloudwatch(
    log_events: List[Dict[str, Any]],
    delivery_config: Dict[str, Any],
    tenant_info: Dict[str, str],
    s3_timestamp: int
) -> None:
    """
    Deliver log events to customer's CloudWatch Logs using Vector with native assume_role capability
    """
    try:
        sts_client = boto3.client('sts', region_name=AWS_REGION)

        # Step 1: Assume the central log distribution role
        central_role_response = sts_client.assume_role(
            RoleArn=CENTRAL_LOG_DISTRIBUTION_ROLE_ARN,
            RoleSessionName=f"CentralLogDistribution-{str(uuid.uuid4())}"
        )

        # Extract central role credentials (Vector will use these to assume customer role)
        central_credentials = central_role_response['Credentials']

        # Get the current account ID for ExternalId
        current_account_id = boto3.client('sts').get_caller_identity()['Account']

        # Generate unique session ID for Vector
        session_id = str(uuid.uuid4())

        # Prepare log group and stream names
        log_group_name = delivery_config['log_group_name']
        log_stream_name = tenant_info['pod_name']
        target_region = delivery_config.get('target_region', AWS_REGION)

        # Use native Python CloudWatch Logs delivery (replaces Vector)
        delivery_stats = deliver_logs_to_cloudwatch_native(
            log_events=log_events,
            central_credentials=central_credentials,
            customer_role_arn=delivery_config['log_distribution_role_arn'],
            external_id=current_account_id,
            region=target_region,
            log_group=log_group_name,
            log_stream=log_stream_name,
            session_id=session_id,
            s3_timestamp=s3_timestamp
        )

        try:
            push_metrics(
                tenant_info['tenant_id'],
                "cloudwatch",
                {
                    "successful_events": delivery_stats["successful_events"],
                    "failed_events": delivery_stats["failed_events"],
                    "successful_delivery": 1,
                })
        except Exception as e:
            logger.error(f"Failed to write metrics to CW for CW for tenant {tenant_info['tenant_id']} :{str(e)}")

        logger.info(f"Successfully delivered {len(log_events)} log events to {tenant_info['tenant_id']} CloudWatch Logs using native Python implementation")

    except Exception as e:

        try:
            push_metrics(
                tenant_info['tenant_id'],
                "cloudwatch",
                {
                    "failed_delivery": 1,
                })
        except Exception as metric_e:
            logger.error(f"Failed to write metrics to CW for CW for tenant {tenant_info['tenant_id']} :{str(metric_e)}")

        logger.error(f"Failed to deliver logs to customer {tenant_info['tenant_id']}: {str(e)}")
        raise

def deliver_logs_to_cloudwatch_native(
    log_events: List[Dict[str, Any]],
    central_credentials: Dict[str, Any],
    customer_role_arn: str,
    external_id: str,
    region: str,
    log_group: str,
    log_stream: str,
    session_id: str,
    s3_timestamp: int
) -> dict[str, int]:
    """
    Pure Python implementation to deliver logs to CloudWatch Logs
    Replicates all Vector functionality without subprocess dependency
    """
    logger.info(f"Starting native CloudWatch delivery for {len(log_events)} log events")
    logger.info(f"Target: {log_group}/{log_stream} in {region}")

    try:
        # Step 1: Create STS client with central credentials to assume customer role
        sts_client = boto3.client(
            'sts',
            region_name=region,
            aws_access_key_id=central_credentials['AccessKeyId'],
            aws_secret_access_key=central_credentials['SecretAccessKey'],
            aws_session_token=central_credentials['SessionToken']
        )

        # Step 2: Assume customer role (second hop)
        logger.info(f"Assuming customer role: {customer_role_arn}")
        customer_role_response = sts_client.assume_role(
            RoleArn=customer_role_arn,
            RoleSessionName=f"CloudWatchLogDelivery-{session_id}",
            ExternalId=external_id
        )

        customer_credentials = customer_role_response['Credentials']
        logger.info(f"Successfully assumed customer role")

        # Step 3: Create CloudWatch Logs client with customer credentials
        logs_client = boto3.client(
            'logs',
            region_name=region,
            aws_access_key_id=customer_credentials['AccessKeyId'],
            aws_secret_access_key=customer_credentials['SecretAccessKey'],
            aws_session_token=customer_credentials['SessionToken']
        )

        # Step 4: Process events with Vector-equivalent timestamp handling
        processed_events = []
        for event in log_events:
            message = event.get('message', '')
            timestamp = event.get('timestamp', s3_timestamp)

            # Replicate Vector's timestamp processing logic exactly
            processed_timestamp = process_timestamp_like_vector(timestamp)

            processed_events.append({
                'timestamp': processed_timestamp,
                'message': str(message)
            })

        # Step 5: Sort events chronologically (CloudWatch requirement)
        processed_events.sort(key=lambda x: x['timestamp'])

        # Step 6: Ensure log group and stream exist
        ensure_log_group_and_stream_exist(logs_client, log_group, log_stream)

        # Step 7: Batch and deliver events with Vector-equivalent settings
        delivery_stats = deliver_events_in_batches(
            logs_client=logs_client,
            log_group=log_group,
            log_stream=log_stream,
            events=processed_events,
            max_events_per_batch=1000,  # Match Vector's max_events
            max_bytes_per_batch=1047576,  # AWS CloudWatch limit
            timeout_secs=5  # Match Vector's timeout_secs
        )

        logger.info(f"CloudWatch delivery complete: {delivery_stats['successful_events']} successful, {delivery_stats['failed_events']} failed")

        # If there were failures, we should raise an exception to trigger re-queuing
        if delivery_stats['failed_events'] > 0:
            raise Exception(f"Failed to deliver {delivery_stats['failed_events']} out of {delivery_stats['total_processed']} events to CloudWatch")

        return delivery_stats

    except Exception as e:
        logger.error(f"Failed to deliver logs to CloudWatch: {str(e)}")
        raise


def process_timestamp_like_vector(timestamp: Any) -> int:
    """
    Process timestamp exactly like Vector's extract_timestamp transform
    Handles ISO strings, numeric values, and millisecond/second detection
    Returns timestamp in milliseconds for CloudWatch API
    """
    try:
        if isinstance(timestamp, str):
            # Handle ISO timestamp string (Vector uses "%+" format)
            try:
                # Remove 'Z' and handle timezone properly
                if timestamp.endswith('Z'):
                    timestamp = timestamp[:-1] + '+00:00'
                dt = datetime.fromisoformat(timestamp)
                return int(dt.timestamp() * 1000)
            except ValueError:
                logger.warning(f"Failed to parse timestamp string: {timestamp}")
                return int(datetime.now().timestamp() * 1000)

        elif isinstance(timestamp, (int, float)):
            ts_value = float(timestamp)
            # Vector's logic: if value > 1000000000000.0, it's milliseconds
            if ts_value > 1000000000000.0:
                # Already in milliseconds
                return int(ts_value)
            else:
                # In seconds, convert to milliseconds
                return int(ts_value * 1000)

        else:
            logger.warning(f"Unknown timestamp type: {type(timestamp)}, value: {timestamp}")
            return int(datetime.now().timestamp() * 1000)

    except Exception as e:
        logger.warning(f"Error processing timestamp {timestamp}: {str(e)}")
        return int(datetime.now().timestamp() * 1000)


def ensure_log_group_and_stream_exist(logs_client, log_group: str, log_stream: str) -> None:
    """
    Ensure log group and log stream exist, creating them if necessary
    """
    try:
        # Check if log group exists, create if not
        groups = logs_client.describe_log_groups(logGroupNamePrefix=log_group)
        for group in groups['logGroups']:
            if group['logGroupName'] == log_group:
                break
        else:
            logger.info(f"Creating log group: {log_group}")
            logs_client.create_log_group(logGroupName=log_group)

        # Check if log stream exists, create if not
        streams = logs_client.describe_log_streams(
            logGroupName=log_group,
            logStreamNamePrefix=log_stream
        )
        for stream in streams['logStreams']:
            if stream['logStreamName'] == log_stream:
                break
        else:
            logger.info(f"Creating log stream: {log_stream} in group: {log_group}")
            logs_client.create_log_stream(
                logGroupName=log_group,
                logStreamName=log_stream
            )

    except Exception as e:
        logger.error(f"Error ensuring log group/stream exist: {str(e)}")
        raise


def deliver_events_in_batches(
    logs_client,
    log_group: str,
    log_stream: str,
    events: List[Dict[str, Any]],
    max_events_per_batch: int = 1000,
    max_bytes_per_batch: int = 1047576,
    timeout_secs: int = 5
) -> Dict[str, int]:
    """
    Deliver events in batches with Vector-equivalent retry logic
    
    Returns:
        Dictionary with 'successful_events' and 'failed_events' counts
    """
    import time

    batch_start_time = time.time()
    current_batch = []
    current_batch_size = 0
    events_processed = 0
    successful_events = 0
    failed_events = 0

    def send_batch():
        nonlocal successful_events, failed_events, current_batch, current_batch_size
        if not current_batch:
            return

        logger.info(f"Sending batch of {len(current_batch)} events to CloudWatch")

        # Retry logic matching Vector: 3 attempts, 30 second max duration
        max_retries = 3
        retry_delay = 1  # Start with 1 second

        for attempt in range(max_retries):
            try:
                response = logs_client.put_log_events(
                    logGroupName=log_group,
                    logStreamName=log_stream,
                    logEvents=list(current_batch)  # Make a copy to avoid reference issues
                )

                # Check for rejected events
                rejected_count = 0
                if response.get('rejectedLogEventsInfo'):
                    rejected_info = response['rejectedLogEventsInfo']
                    if rejected_info.get('tooNewLogEventStartIndex') is not None:
                        logger.warning(f"Some events were too new: {rejected_info}")
                        rejected_count += len(current_batch) - rejected_info['tooNewLogEventStartIndex']
                    if rejected_info.get('tooOldLogEventEndIndex') is not None:
                        logger.warning(f"Some events were too old: {rejected_info}")
                        rejected_count += rejected_info['tooOldLogEventEndIndex'] + 1
                    if rejected_info.get('expiredLogEventEndIndex') is not None:
                        logger.warning(f"Some events were expired: {rejected_info}")
                        rejected_count += rejected_info['expiredLogEventEndIndex'] + 1

                batch_successful = len(current_batch) - rejected_count
                successful_events += max(0, batch_successful)
                failed_events += max(0, rejected_count)

                logger.info(f"Successfully sent batch: {batch_successful} successful, {rejected_count} rejected")

                # Clear batch after successful sending
                current_batch.clear()
                current_batch_size = 0
                return

            except ClientError as e:
                error_code = e.response['Error']['Code']

                if error_code in ['Throttling', 'ServiceUnavailable']:
                    if attempt < max_retries - 1:
                        logger.warning(f"Throttled/unavailable, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, 30)  # Exponential backoff, max 30s
                        continue
                    else:
                        logger.error(f"Failed after {max_retries} attempts due to throttling")
                        failed_events += len(current_batch)
                        raise

                elif error_code == 'InvalidSequenceTokenException':
                    # Sequence tokens are now ignored by AWS, but just in case
                    logger.warning("Invalid sequence token, retrying without token")
                    continue

                else:
                    # Other errors, don't retry
                    logger.error(f"CloudWatch API error: {error_code}: {e}")
                    failed_events += len(current_batch)
                    raise

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Unexpected error, retrying in {retry_delay}s: {str(e)}")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)
                    continue
                else:
                    logger.error(f"Failed after {max_retries} attempts: {str(e)}")
                    failed_events += len(current_batch)
                    raise

    for event in events:
        # Calculate event size (approximate)
        event_size = len(event['message'].encode('utf-8')) + 26  # 26 bytes overhead per event

        # Add event to current batch first
        current_batch.append(event)
        current_batch_size += event_size
        events_processed += 1

        # Check if we need to send current batch after adding this event
        should_send = (
            len(current_batch) >= max_events_per_batch or
            current_batch_size > max_bytes_per_batch or
            (time.time() - batch_start_time) >= timeout_secs
        )

        if should_send:
            send_batch()
            batch_start_time = time.time()

    # Send final batch
    if current_batch:
        send_batch()

    return {
        'successful_events': successful_events,
        'failed_events': failed_events,
        'total_processed': events_processed
    }


def requeue_sqs_message_with_offset(
    message_body: str,
    original_receipt_handle: str,
    processing_offset: int = 0,
    max_retries: int = 3
) -> None:
    """
    Re-queue an SQS message with processing offset information for resilient processing
    
    Args:
        message_body: Original SQS message body
        original_receipt_handle: Receipt handle of the original message (for tracking)
        processing_offset: Offset indicating which log events have been processed successfully
        max_retries: Maximum number of times to retry re-queuing
    """
    if not SQS_QUEUE_URL:
        logger.warning("SQS_QUEUE_URL not configured, cannot re-queue message")
        return

    try:
        # Parse original message to add offset information
        try:
            message_data = json.loads(message_body)
        except json.JSONDecodeError:
            logger.error("Failed to parse message body for re-queuing")
            return

        # Add processing metadata
        if 'processing_metadata' not in message_data:
            message_data['processing_metadata'] = {}

        # Get current retry count before incrementing
        current_retry_count = message_data.get('processing_metadata', {}).get('retry_count', 0)
        new_retry_count = current_retry_count + 1

        message_data['processing_metadata']['offset'] = processing_offset
        message_data['processing_metadata']['retry_count'] = new_retry_count
        message_data['processing_metadata']['original_receipt_handle'] = original_receipt_handle
        message_data['processing_metadata']['requeued_at'] = datetime.now().isoformat()

        # Check if we've exceeded retry limits
        if new_retry_count > max_retries:
            logger.error(f"Message has exceeded maximum retry count ({max_retries}), discarding")
            return

        sqs_client = boto3.client('sqs', region_name=AWS_REGION)

        # Calculate delay based on original retry count (exponential backoff)
        delay_seconds = min(2 ** (current_retry_count + 1), 900)  # Max 15 minutes delay

        logger.info(f"Re-queuing message with offset {processing_offset}, retry {new_retry_count}, delay {delay_seconds}s")

        # Send message back to queue with delay
        response = sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(message_data),
            DelaySeconds=delay_seconds,
            MessageAttributes={
                'ProcessingOffset': {
                    'StringValue': str(processing_offset),
                    'DataType': 'Number'
                },
                'RetryCount': {
                    'StringValue': str(new_retry_count),
                    'DataType': 'Number'
                }
            }
        )

        logger.info(f"Successfully re-queued message with ID: {response.get('MessageId')}")

    except Exception as e:
        logger.error(f"Failed to re-queue SQS message: {str(e)}")


def extract_processing_metadata(sqs_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract processing metadata from SQS record (offset, retry count, etc.)
    
    Returns:
        Dictionary with processing metadata or empty dict if none found
    """
    try:
        message_body = json.loads(sqs_record['body'])
        return message_body.get('processing_metadata', {})
    except (json.JSONDecodeError, KeyError):
        return {}


def should_skip_processed_events(events: List[Dict[str, Any]], offset: int) -> List[Dict[str, Any]]:
    """
    Skip events that have already been processed based on offset
    
    Args:
        events: List of log events
        offset: Number of events to skip (already processed)
        
    Returns:
        List of events starting from the offset
    """
    if offset <= 0:
        return events

    if offset >= len(events):
        logger.warning(f"Offset {offset} is >= event count {len(events)}, no events to process")
        return []

    logger.info(f"Skipping first {offset} events (already processed), processing remaining {len(events) - offset}")
    return events[offset:]


def deliver_logs_to_s3(
    source_bucket: str,
    source_key: str,
    delivery_config: Dict[str, Any],
    tenant_info: Dict[str, str]
) -> None:
    """
    Delivers a log file from the central S3 bucket to a customer's S3 bucket using a direct S3-to-S3 copy.

    This function assumes a central log distribution role, creates an S3 client with the assumed credentials,
    and copies the specified object to the target bucket, supporting cross-region operations if required.

    Parameters:
        source_bucket (str): The name of the S3 bucket containing the source log file.
        source_key (str): The S3 object key (path) of the source log file.
        delivery_config (Dict[str, Any]): Configuration for delivery, must include:
            - 'bucket_name' (str): Target S3 bucket name.
            - 'target_region' (str, optional): AWS region of the target bucket. Defaults to AWS_REGION if not provided.
            - 'target_key' (str): S3 object key (path) for the delivered log file.
        tenant_info (Dict[str, str]): Information about the tenant, must include:
            - 'tenant_id' (str): Unique identifier for the tenant.

    Returns:
        None

    Raises:
        botocore.exceptions.ClientError: If there is an error with AWS STS or S3 operations.
        KeyError: If required keys are missing from delivery_config or tenant_info.
        NonRecoverableError: For known non-recoverable delivery errors (custom exception).
        Exception: For any other unexpected errors.

    Example:
        try:
            deliver_logs_to_s3(
                source_bucket="central-logs",
                source_key="logs/2024/06/01/logfile.gz",
                delivery_config={
                    "bucket_name": "customer-logs",
                    "target_region": "us-west-2",
                    "target_key": "delivered/2024/06/01/logfile.gz"
                },
                tenant_info={"tenant_id": "tenant-123"}
            )
        except ClientError as e:
            # Handle AWS errors
            print(f"AWS error: {e}")
        except NonRecoverableError as e:
            # Handle non-recoverable delivery errors
            print(f"Delivery failed: {e}")
        except Exception as e:
            # Handle unexpected errors
            print(f"Unexpected error: {e}")

    Notes:
        - This function supports cross-region S3 copy by specifying 'target_region' in delivery_config.
        - The function assumes the central log distribution role for secure access.
        - All errors are logged; non-recoverable errors are re-raised for upstream handling.
    """
    try:
        sts_client = boto3.client('sts', region_name=AWS_REGION)

        # Assume the central log distribution role (single-hop)
        central_role_response = sts_client.assume_role(
            RoleArn=CENTRAL_LOG_DISTRIBUTION_ROLE_ARN,
            RoleSessionName=f"S3LogDelivery-{str(uuid.uuid4())}"
        )

        # Create S3 client with central role credentials
        central_credentials = central_role_response['Credentials']
        s3_client = boto3.client(
            's3',
            region_name=delivery_config.get('target_region', AWS_REGION),
            aws_access_key_id=central_credentials['AccessKeyId'],
            aws_secret_access_key=central_credentials['SecretAccessKey'],
            aws_session_token=central_credentials['SessionToken']
        )

        # Prepare destination S3 details
        destination_bucket = delivery_config['bucket_name']
        bucket_prefix = delivery_config.get('bucket_prefix', 'ROSA/cluster-logs/')

        # Normalize prefix using shared utility
        bucket_prefix = normalize_bucket_prefix(bucket_prefix)

        # Create destination key maintaining directory structure
        # Format: {prefix}{tenant_id}/{application}/{pod_name}/{filename}
        # This excludes cluster_id to avoid exposing MC cluster ID to destination
        source_filename = source_key.split('/')[-1]  # Extract just the filename
        destination_key = (
            f"{bucket_prefix}{tenant_info['tenant_id']}/"
            f"{tenant_info['application']}/"
            f"{tenant_info['pod_name']}/{source_filename}"
        )

        logger.info(f"Starting S3-to-S3 copy for tenant {tenant_info['tenant_id']}")
        logger.info(f"Source: s3://{source_bucket}/{source_key}")
        logger.info(f"Destination: s3://{destination_bucket}/{destination_key}")

        # Copy source for the S3 copy operation
        copy_source = {
            'Bucket': source_bucket,
            'Key': source_key
        }

        # Additional metadata for traceability
        metadata = {
            'source-bucket': source_bucket,
            'source-key': source_key,
            'tenant-id': tenant_info['tenant_id'],
            'application': tenant_info['application'],
            'pod-name': tenant_info['pod_name'],
            'delivery-timestamp': str(int(datetime.now().timestamp()))
        }

        # Perform S3-to-S3 copy with bucket-owner-full-control ACL
        try:
            s3_client.copy_object(
                Bucket=destination_bucket,
                Key=destination_key,
                CopySource=copy_source,
                ACL='bucket-owner-full-control',
                Metadata=metadata,
                MetadataDirective='REPLACE'
            )

            logger.info(f"Successfully copied log file to S3 for tenant {tenant_info['tenant_id']}")
            logger.info(f"Delivered to: s3://{destination_bucket}/{destination_key}")

            try:
                push_metrics(tenant_info['tenant_id'], "s3", {"successful_delivery": 1})
            except Exception as metric_e:
                logger.error(f"Failed to write metrics to CW for S3 for tenant {tenant_info['tenant_id']} :{str(metric_e)}")

        except ClientError as copy_error:
            error_code = copy_error.response['Error']['Code']

            try:
                push_metrics(tenant_info['tenant_id'], "s3", {"failed_delivery": 1})
            except Exception as metric_e:
                logger.error(f"Failed to write metrics to CW for S3 for tenant {tenant_info['tenant_id']} :{str(metric_e)}")

            if error_code == 'NoSuchBucket':
                raise NonRecoverableError(f"Destination S3 bucket '{destination_bucket}' does not exist")
            elif error_code == 'AccessDenied':
                raise NonRecoverableError(f"Access denied to S3 bucket '{destination_bucket}'. Check bucket policy and Central Role permissions")
            elif error_code == 'NoSuchKey':
                raise NonRecoverableError(f"Source S3 object s3://{source_bucket}/{source_key} not found")
            else:
                # For other errors, treat as recoverable (temporary issues)
                logger.error(f"S3 copy operation failed with error {error_code}: {str(copy_error)}")
                raise

    except NonRecoverableError:
        # Re-raise non-recoverable errors
        raise
    except Exception as e:
        logger.error(f"Failed to deliver logs to S3 for tenant {tenant_info['tenant_id']}: {str(e)}")
        raise


def push_metrics(tenant_id: str, method: str, metrics_data: {str, int}):
    """
    Push metrics to cloudwatch
    """
    post_data = []
    for metric_dimension, count in metrics_data.items():
        post_data.append({
            'MetricName': f'LogCount/{method}/{metric_dimension}',
            'Dimensions': [
                {
                    'Name': 'Tenant',
                    'Value': tenant_id
                },
            ],
            'Value': count,
            'Unit': 'Count'
        })

    cloudwatch_client = boto3.client('cloudwatch', region_name=AWS_REGION)
    try:
        response = cloudwatch_client.put_metric_data(
            Namespace='Test/LogForwarding',  # A custom namespace for your metrics
            MetricData=post_data
        )
        return response
    except Exception as e:
        print(f"Error publishing metric: {e}")
        raise

def scan_mode():
    """
    Scan mode for integration testing
    Continuously scans S3 bucket for new files and processes them
    """
    logger.info("Starting log processor in scan mode")

    # Get configuration from environment variables
    source_bucket = os.environ.get('SOURCE_BUCKET', 'test-logs')
    scan_interval = int(os.environ.get('SCAN_INTERVAL', '10'))
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')

    # For integration testing, detect MinIO endpoint
    s3_endpoint = os.environ.get('S3_ENDPOINT_URL')
    if not s3_endpoint:
        # Check if we're running in integration test environment
        if os.environ.get('TENANT_CONFIG_TABLE') == 'integration-test-tenant-configs':
            s3_endpoint = 'http://minio:9000'
            logger.info("Integration test environment detected, using MinIO endpoint")

    # Create S3 client with appropriate configuration
    s3_config = {
        'region_name': aws_region
    }

    if s3_endpoint:
        s3_config['endpoint_url'] = s3_endpoint
        # For MinIO integration testing, use hardcoded credentials
        if 'minio' in s3_endpoint.lower():
            s3_config['aws_access_key_id'] = 'minioadmin'
            s3_config['aws_secret_access_key'] = 'minioadmin'

    s3_client = boto3.client('s3', **s3_config)

    logger.info(f"Scan mode configuration:")
    logger.info(f"  Source bucket: {source_bucket}")
    logger.info(f"  Scan interval: {scan_interval} seconds")
    logger.info(f"  AWS region: {aws_region}")
    logger.info(f"  S3 endpoint: {s3_endpoint or 'default (AWS S3)'}")

    # Track processed objects to avoid reprocessing
    processed_objects = set()

    while True:
        try:
            logger.debug(f"Scanning bucket {source_bucket} for new files...")

            # List objects in source bucket
            response = s3_client.list_objects_v2(Bucket=source_bucket)
            objects = response.get('Contents', [])

            new_objects_found = 0
            for obj in objects:
                object_key = obj['Key']

                # Only process .json.gz files that haven't been processed yet
                if (object_key not in processed_objects and
                    object_key.endswith('.json.gz')):

                    logger.info(f"Processing new object: {object_key}")
                    new_objects_found += 1

                    try:
                        # Create simulated SQS record for existing process_sqs_record function
                        s3_event = {
                            "Records": [{
                                "s3": {
                                    "bucket": {"name": source_bucket},
                                    "object": {"key": object_key}
                                }
                            }]
                        }

                        # Create simulated SNS message
                        sns_message = {"Message": json.dumps(s3_event)}

                        # Create simulated SQS record
                        sqs_record = {
                            "body": json.dumps(sns_message),
                            "messageId": f"scan-{object_key.replace('/', '-')}"
                        }

                        # Use existing process_sqs_record function
                        delivery_stats = process_sqs_record(sqs_record)
                        processed_objects.add(object_key)

                        if delivery_stats:
                            logger.info(f"Successfully processed {object_key}. Deliveries: Success: {delivery_stats.get('successful_deliveries', 0)}, Failed: {delivery_stats.get('failed_deliveries', 0)}")
                        else:
                            logger.info(f"Successfully processed {object_key}")

                    except Exception as e:
                        logger.error(f"Failed to process {object_key}: {str(e)}")
                        # Don't add to processed_objects so it will be retried

            if new_objects_found > 0:
                logger.info(f"Processed {new_objects_found} new objects in this scan")
            else:
                logger.debug("No new objects found")

            logger.debug(f"Waiting {scan_interval} seconds before next scan...")
            time.sleep(scan_interval)

        except Exception as e:
            logger.error(f"Error in scan mode main loop: {str(e)}")
            logger.info(f"Retrying in {scan_interval} seconds...")
            time.sleep(scan_interval)


def main():
    """
    Main entry point for standalone execution
    """
    parser = argparse.ArgumentParser(description='Multi-tenant log processor')
    parser.add_argument('--mode', choices=['sqs', 'manual', 'scan'], default='sqs',
                        help='Execution mode: sqs (poll queue), manual (stdin input), or scan (periodic bucket scan)')

    args = parser.parse_args()

    if args.mode == 'sqs':
        sqs_polling_mode()
    elif args.mode == 'manual':
        manual_input_mode()
    elif args.mode == 'scan':
        scan_mode()

if __name__ == '__main__':
    main()