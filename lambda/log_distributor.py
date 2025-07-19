"""
AWS Lambda function for cross-account log delivery
Processes S3 events from SQS queue and delivers logs to customer CloudWatch Logs
"""

import json
import urllib.parse
import gzip
import boto3
import pandas as pd
import pyarrow.parquet as pq
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging
import os
import io
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
sts_client = boto3.client('sts')
dynamodb = boto3.resource('dynamodb')

# Environment variables
TENANT_CONFIG_TABLE = os.environ.get('TENANT_CONFIG_TABLE', 'tenant-configurations')
MAX_BATCH_SIZE = int(os.environ.get('MAX_BATCH_SIZE', '1000'))
RETRY_ATTEMPTS = int(os.environ.get('RETRY_ATTEMPTS', '3'))
CENTRAL_LOG_DISTRIBUTION_ROLE_ARN = os.environ.get('CENTRAL_LOG_DISTRIBUTION_ROLE_ARN')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Main Lambda handler for processing SQS messages containing S3 events
    """
    successful_records = 0
    failed_records = 0
    
    logger.info(f"Processing {len(event['Records'])} SQS messages")
    
    for record in event['Records']:
        try:
            process_sqs_record(record)
            successful_records += 1
        except Exception as e:
            logger.error(f"Failed to process record: {str(e)}")
            failed_records += 1
            # In production, you might want to send failed records to a DLQ
            
    logger.info(f"Processing complete. Success: {successful_records}, Failed: {failed_records}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': successful_records,
            'failed': failed_records
        })
    }

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
    Example: acme-corp/prod-cluster-1/payment-app/pod-xyz-123/20240101120000-a1b2c3d4.json.gz
    """
    path_parts = object_key.split('/')
    
    # Ensure we have at least 5 parts (customer_id/cluster_id/application/pod_name/filename)
    if len(path_parts) < 5:
        raise ValueError(f"Invalid object key format. Expected at least 5 path segments, got {len(path_parts)}: {object_key}")
    
    tenant_info = {
        'tenant_id': path_parts[0],  # Map customer_id to tenant_id for compatibility
        'customer_id': path_parts[0],
        'cluster_id': path_parts[1],
        'application': path_parts[2],
        'pod_name': path_parts[3],
        'environment': 'production'  # Default, can be extracted from cluster_id or metadata
    }
    
    # Extract environment from cluster_id if it contains it (e.g., prod-cluster-1)
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
    Handles both Parquet and JSON formats
    """
    try:
        # Download the file
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response['Body'].read()
        
        # Decompress if gzipped
        if object_key.endswith('.gz'):
            file_content = gzip.decompress(file_content)
        
        # Process based on file format
        if object_key.endswith('.parquet') or object_key.endswith('.parquet.gz'):
            return process_parquet_file(file_content)
        else:
            return process_json_file(file_content)
            
    except Exception as e:
        logger.error(f"Failed to download/process file s3://{bucket_name}/{object_key}: {str(e)}")
        raise

def process_parquet_file(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Process Parquet file content and extract log events
    """
    try:
        # Read Parquet data using pandas
        df = pd.read_parquet(io.BytesIO(file_content))
        
        # Convert to list of dictionaries
        log_events = []
        for _, row in df.iterrows():
            event = {
                'timestamp': int(pd.to_datetime(row['timestamp']).timestamp() * 1000),
                'message': str(row['message'])
            }
            log_events.append(event)
        
        logger.info(f"Processed {len(log_events)} log events from Parquet file")
        return log_events
        
    except Exception as e:
        logger.error(f"Failed to process Parquet file: {str(e)}")
        raise

def process_json_file(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Process JSON file content and extract log events
    """
    try:
        log_events = []
        
        # Process line-delimited JSON
        for line in file_content.decode('utf-8').strip().split('\n'):
            if line:
                log_record = json.loads(line)
                event = {
                    'timestamp': int(pd.to_datetime(log_record['timestamp']).timestamp() * 1000),
                    'message': log_record['message']
                }
                log_events.append(event)
        
        logger.info(f"Processed {len(log_events)} log events from JSON file")
        return log_events
        
    except Exception as e:
        logger.error(f"Failed to process JSON file: {str(e)}")
        raise

def deliver_logs_to_customer(
    log_events: List[Dict[str, Any]], 
    tenant_config: Dict[str, Any],
    tenant_info: Dict[str, str]
) -> None:
    """
    Deliver log events to customer's CloudWatch Logs using double-hop cross-account role assumption
    """
    try:
        # Step 1: Assume the central log distribution role with session tags
        central_role_response = sts_client.assume_role(
            RoleArn=CENTRAL_LOG_DISTRIBUTION_ROLE_ARN,
            RoleSessionName=f"CentralLogDistribution-{tenant_info['tenant_id']}-{int(datetime.now().timestamp())}",
            Tags=[
                {
                    'Key': 'tenant_id',
                    'Value': tenant_info['tenant_id']
                },
                {
                    'Key': 'cluster_id', 
                    'Value': tenant_info['cluster_id']
                },
                {
                    'Key': 'environment',
                    'Value': tenant_info['environment']
                }
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
                {
                    'Key': 'tenant_id',
                    'Value': tenant_info['tenant_id']
                },
                {
                    'Key': 'cluster_id', 
                    'Value': tenant_info['cluster_id']
                },
                {
                    'Key': 'environment',
                    'Value': tenant_info['environment']
                }
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