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
from datetime import datetime
from typing import Dict, List, Any, Optional

import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    """
    successful_records = 0
    failed_records = 0
    
    logger.info(f"Processing {len(event.get('Records', []))} SQS messages")
    
    for record in event.get('Records', []):
        try:
            process_sqs_record(record)
            successful_records += 1
        except Exception as e:
            logger.error(f"Failed to process record: {str(e)}")
            failed_records += 1
            
    logger.info(f"Processing complete. Success: {successful_records}, Failed: {failed_records}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': successful_records,
            'failed': failed_records
        })
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
                VisibilityTimeoutSeconds=300
            )
            
            messages = response.get('Messages', [])
            if not messages:
                logger.info("No messages received, continuing to poll...")
                continue
            
            logger.info(f"Received {len(messages)} messages from SQS")
            
            for message in messages:
                try:
                    # Convert SQS message to Lambda record format
                    lambda_record = {
                        'body': message['Body'],
                        'messageId': message['MessageId'],
                        'receiptHandle': message['ReceiptHandle']
                    }
                    
                    process_sqs_record(lambda_record)
                    
                    # Delete processed message
                    sqs_client.delete_message(
                        QueueUrl=SQS_QUEUE_URL,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    logger.info(f"Successfully processed and deleted message {message['MessageId']}")
                    
                except Exception as e:
                    logger.error(f"Failed to process message {message.get('MessageId', 'unknown')}: {str(e)}")
                    # Message will become visible again after visibility timeout
                    
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
        
        process_sqs_record(lambda_record)
        logger.info("Successfully processed manual input")
        
    except Exception as e:
        logger.error(f"Error processing manual input: {str(e)}")
        sys.exit(1)

def process_sqs_record(sqs_record: Dict[str, Any]) -> None:
    """
    Process a single SQS record containing S3 event notification
    """
    try:
        # Parse the SQS message body (SNS message)
        sns_message = json.loads(sqs_record['body'])
        s3_event = json.loads(sns_message['Message'])
        
        # Extract S3 event details
        for s3_record in s3_event['Records']:
            bucket_name = s3_record['s3']['bucket']['name']
            object_key = urllib.parse.unquote_plus(s3_record['s3']['object']['key'])
            
            logger.info(f"Processing S3 object: s3://{bucket_name}/{object_key}")
            
            # Extract tenant information from object key
            tenant_info = extract_tenant_info_from_key(object_key)
            
            # Get tenant configuration
            tenant_config = get_tenant_configuration(tenant_info['tenant_id'])
            
            # Download and process the log file
            log_events = download_and_process_log_file(bucket_name, object_key)
            
            # Deliver logs to customer account
            deliver_logs_to_customer(log_events, tenant_config, tenant_info)
            
    except Exception as e:
        logger.error(f"Error processing SQS record: {str(e)}")
        raise

def extract_tenant_info_from_key(object_key: str) -> Dict[str, str]:
    """
    Extract tenant information from S3 object key path
    Expected format: customer_id/cluster_id/application/pod_name/timestamp-uuid.json.gz
    """
    path_parts = object_key.split('/')
    
    if len(path_parts) < 5:
        raise ValueError(f"Invalid object key format. Expected at least 5 path segments, got {len(path_parts)}: {object_key}")
    
    tenant_info = {
        'tenant_id': path_parts[0],
        'customer_id': path_parts[0],
        'cluster_id': path_parts[1],
        'application': path_parts[2],
        'pod_name': path_parts[3],
        'environment': 'production'
    }
    
    # Extract environment from cluster_id if it contains it
    if '-' in tenant_info['cluster_id']:
        env_prefix = tenant_info['cluster_id'].split('-')[0]
        env_map = {'prod': 'production', 'stg': 'staging', 'dev': 'development'}
        tenant_info['environment'] = env_map.get(env_prefix, 'production')
    
    logger.info(f"Extracted tenant info: {tenant_info}")
    return tenant_info

def get_tenant_configuration(tenant_id: str) -> Dict[str, Any]:
    """
    Retrieve tenant configuration from DynamoDB
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(TENANT_CONFIG_TABLE)
        response = table.get_item(Key={'tenant_id': tenant_id})
        
        if 'Item' not in response:
            raise ValueError(f"No configuration found for tenant: {tenant_id}")
        
        config = response['Item']
        logger.info(f"Retrieved config for tenant {tenant_id}")
        return config
        
    except Exception as e:
        logger.error(f"Failed to get tenant configuration for {tenant_id}: {str(e)}")
        raise

def download_and_process_log_file(bucket_name: str, object_key: str) -> List[Dict[str, Any]]:
    """
    Download log file from S3 and extract log events
    """
    try:
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response['Body'].read()
        
        # Decompress if gzipped
        if object_key.endswith('.gz'):
            file_content = gzip.decompress(file_content)
        
        return process_json_file(file_content)
        
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
        
        # Try line-delimited JSON first (Vector NDJSON format)
        try:
            for line in content.strip().split('\n'):
                if line:
                    try:
                        log_record = json.loads(line)
                        event = convert_log_record_to_event(log_record)
                        if event:
                            log_events.append(event)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            # Fallback: try parsing as JSON array or single object
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for log_record in data:
                        event = convert_log_record_to_event(log_record)
                        if event:
                            log_events.append(event)
                else:
                    # Single JSON object
                    event = convert_log_record_to_event(data)
                    if event:
                        log_events.append(event)
            except json.JSONDecodeError:
                pass  # No valid JSON found
        
        logger.info(f"Processed {len(log_events)} log events from JSON file")
        return log_events
        
    except Exception as e:
        logger.error(f"Failed to process JSON file: {str(e)}")
        raise

def convert_log_record_to_event(log_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert log record to CloudWatch Logs event format
    """
    try:
        if isinstance(log_record, dict):
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
            
            message = log_record.get('message', str(log_record))
            
            return {
                'timestamp': timestamp_ms,
                'message': message
            }
    except Exception as e:
        logger.warning(f"Failed to convert log record: {str(e)}")
        return None

def deliver_logs_to_customer(
    log_events: List[Dict[str, Any]], 
    tenant_config: Dict[str, Any],
    tenant_info: Dict[str, str]
) -> None:
    """
    Deliver log events to customer's CloudWatch Logs using double-hop cross-account role assumption
    """
    try:
        sts_client = boto3.client('sts', region_name=AWS_REGION)
        
        # Step 1: Assume the central log distribution role with session tags
        central_role_response = sts_client.assume_role(
            RoleArn=CENTRAL_LOG_DISTRIBUTION_ROLE_ARN,
            RoleSessionName=f"CentralLogDistribution-{tenant_info['tenant_id']}-{int(datetime.now().timestamp())}",
            Tags=[
                {'Key': 'tenant_id', 'Value': tenant_info['tenant_id']},
                {'Key': 'cluster_id', 'Value': tenant_info['cluster_id']},
                {'Key': 'environment', 'Value': tenant_info['environment']}
            ]
        )
        
        # Step 2: Create STS client with central role credentials
        central_sts_client = boto3.client(
            'sts',
            aws_access_key_id=central_role_response['Credentials']['AccessKeyId'],
            aws_secret_access_key=central_role_response['Credentials']['SecretAccessKey'],
            aws_session_token=central_role_response['Credentials']['SessionToken']
        )
        
        # Step 3: Assume the customer's log distribution role using central role
        customer_role_response = central_sts_client.assume_role(
            RoleArn=tenant_config['log_distribution_role_arn'],
            RoleSessionName=f"CustomerLogDelivery-{tenant_info['tenant_id']}-{int(datetime.now().timestamp())}",
            Tags=[
                {'Key': 'tenant_id', 'Value': tenant_info['tenant_id']},
                {'Key': 'cluster_id', 'Value': tenant_info['cluster_id']},
                {'Key': 'environment', 'Value': tenant_info['environment']}
            ]
        )
        
        # Step 4: Create CloudWatch Logs client with customer role credentials
        logs_client = boto3.client(
            'logs',
            region_name=tenant_config['target_region'],
            aws_access_key_id=customer_role_response['Credentials']['AccessKeyId'],
            aws_secret_access_key=customer_role_response['Credentials']['SecretAccessKey'],
            aws_session_token=customer_role_response['Credentials']['SessionToken']
        )
        
        # Ensure log group and stream exist
        log_group_name = tenant_config['log_group_name']
        log_stream_name = f"{tenant_info['cluster_id']}-{tenant_info['environment']}-{datetime.now().strftime('%Y-%m-%d')}"
        
        ensure_log_stream_exists(logs_client, log_group_name, log_stream_name)
        
        # Deliver logs in batches
        deliver_logs_in_batches(logs_client, log_group_name, log_stream_name, log_events)
        
        logger.info(f"Successfully delivered {len(log_events)} log events to {tenant_info['tenant_id']}")
        
    except Exception as e:
        logger.error(f"Failed to deliver logs to customer {tenant_info['tenant_id']}: {str(e)}")
        raise

def ensure_log_stream_exists(logs_client, log_group_name: str, log_stream_name: str) -> None:
    """
    Ensure the log group and stream exist in the customer account
    """
    try:
        # Check if log group exists, create if not
        try:
            logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logs_client.create_log_group(logGroupName=log_group_name)
                logger.info(f"Created log group: {log_group_name}")
        
        # Check if log stream exists, create if not
        try:
            logs_client.describe_log_streams(
                logGroupName=log_group_name,
                logStreamNamePrefix=log_stream_name
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logs_client.create_log_stream(
                    logGroupName=log_group_name,
                    logStreamName=log_stream_name
                )
                logger.info(f"Created log stream: {log_stream_name}")
                
    except Exception as e:
        logger.error(f"Failed to ensure log stream exists: {str(e)}")
        raise

def deliver_logs_in_batches(
    logs_client, 
    log_group_name: str, 
    log_stream_name: str, 
    log_events: List[Dict[str, Any]]
) -> None:
    """
    Deliver log events to CloudWatch Logs in batches
    """
    # Sort events by timestamp
    log_events.sort(key=lambda x: x['timestamp'])
    
    # Get current sequence token
    sequence_token = get_sequence_token(logs_client, log_group_name, log_stream_name)
    
    # Process in batches
    for i in range(0, len(log_events), MAX_BATCH_SIZE):
        batch = log_events[i:i + MAX_BATCH_SIZE]
        
        put_events_kwargs = {
            'logGroupName': log_group_name,
            'logStreamName': log_stream_name,
            'logEvents': batch
        }
        
        if sequence_token:
            put_events_kwargs['sequenceToken'] = sequence_token
        
        try:
            response = logs_client.put_log_events(**put_events_kwargs)
            sequence_token = response.get('nextSequenceToken')
            
            logger.info(f"Delivered batch of {len(batch)} log events")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidSequenceTokenException':
                # Retry with correct sequence token
                sequence_token = get_sequence_token(logs_client, log_group_name, log_stream_name)
                put_events_kwargs['sequenceToken'] = sequence_token
                response = logs_client.put_log_events(**put_events_kwargs)
                sequence_token = response.get('nextSequenceToken')
            else:
                raise

def get_sequence_token(logs_client, log_group_name: str, log_stream_name: str) -> Optional[str]:
    """
    Get the current sequence token for the log stream
    """
    try:
        response = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            logStreamNamePrefix=log_stream_name
        )
        
        for stream in response['logStreams']:
            if stream['logStreamName'] == log_stream_name:
                return stream.get('uploadSequenceToken')
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get sequence token: {str(e)}")
        return None

def main():
    """
    Main entry point for standalone execution
    """
    parser = argparse.ArgumentParser(description='Multi-tenant log processor')
    parser.add_argument('--mode', choices=['sqs', 'manual'], default='sqs',
                        help='Execution mode: sqs (poll queue) or manual (stdin input)')
    
    args = parser.parse_args()
    
    if args.mode == 'sqs':
        sqs_polling_mode()
    elif args.mode == 'manual':
        manual_input_mode()

if __name__ == '__main__':
    main()