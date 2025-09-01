"""
DynamoDB service layer for tenant delivery configuration management
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from botocore.exceptions import ClientError
import boto3

logger = logging.getLogger(__name__)


class TenantNotFoundError(Exception):
    """Raised when a tenant delivery configuration is not found in DynamoDB"""
    pass


class DynamoDBError(Exception):
    """Raised for general DynamoDB operation errors"""
    pass


class TenantDeliveryConfigService:
    """
    Service class for managing tenant delivery configurations in DynamoDB.

    The DynamoDB table uses a composite primary key:
        - Partition key: tenant_id (string)
        - Sort key: type (string)

    Each item represents a delivery configuration for a tenant and a specific delivery type.

    Supported delivery types include (but are not limited to):
        - "cloudwatch"
        - "s3"

    Example item:
        {
            "tenant_id": "tenant-123",
            "type": "cloudwatch",
            "enabled": true,
            "created_at": "2024-06-01T12:00:00Z",
            "updated_at": "2024-06-01T12:00:00Z",
            ...
        }
    """
    
    def __init__(self, table_name: str, region: str = "us-east-1"):
        """
        Initialize the tenant delivery configuration service
        
        Args:
            table_name: Name of the DynamoDB table
            region: AWS region for DynamoDB
        """
        self.table_name = table_name
        self.region = region
        self._dynamodb = None
        self._table = None
    
    @property
    def dynamodb(self):
        """Lazy initialization of DynamoDB resource"""
        if self._dynamodb is None:
            self._dynamodb = boto3.resource('dynamodb', region_name=self.region)
        return self._dynamodb
    
    @property
    def table(self):
        """Lazy initialization of DynamoDB table"""
        if self._table is None:
            self._table = self.dynamodb.Table(self.table_name)
        return self._table
    
    def _apply_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply default values to configuration"""
        config = config.copy()
        
        # Apply defaults
        if 'enabled' not in config or config['enabled'] is None:
            config['enabled'] = True
        
        # Add timestamps
        current_time = datetime.now(timezone.utc).isoformat()
        if 'created_at' not in config or config['created_at'] is None:
            config['created_at'] = current_time
        config['updated_at'] = current_time
        
        return config
    
    def get_tenant_config(self, tenant_id: str, delivery_type: str) -> Dict[str, Any]:
        """
        Get a specific tenant delivery configuration by ID and type
        
        Args:
            tenant_id: The tenant identifier
            delivery_type: The delivery configuration type ("cloudwatch" or "s3")
            
        Returns:
            Dictionary containing tenant delivery configuration
            
        Raises:
            TenantNotFoundError: If configuration is not found
            DynamoDBError: For other DynamoDB errors
        """
        try:
            response = self.table.get_item(
                Key={
                    'tenant_id': tenant_id,
                    'type': delivery_type
                }
            )
            
            if 'Item' not in response:
                raise TenantNotFoundError(f"Tenant '{tenant_id}' delivery configuration '{delivery_type}' not found")
            
            return dict(response['Item'])
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB error getting tenant {tenant_id}/{delivery_type}: {error_code}")
            raise DynamoDBError(f"Failed to get tenant configuration: {error_code}")
    
    def get_tenant_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get all delivery configurations for a tenant
        
        Args:
            tenant_id: The tenant identifier
            
        Returns:
            List of dictionaries containing tenant delivery configurations
            
        Raises:
            DynamoDBError: For DynamoDB operation errors
        """
        try:
            response = self.table.query(
                KeyConditionExpression='tenant_id = :tenant_id',
                ExpressionAttributeValues={
                    ':tenant_id': tenant_id
                }
            )
            
            return [dict(item) for item in response.get('Items', [])]
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB error getting tenant configs for {tenant_id}: {error_code}")
            raise DynamoDBError(f"Failed to get tenant configurations: {error_code}")
    
    def get_enabled_tenant_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get all enabled delivery configurations for a tenant
        
        Args:
            tenant_id: The tenant identifier
            
        Returns:
            List of enabled delivery configurations
            
        Raises:
            DynamoDBError: For DynamoDB operation errors
        """
        configs = self.get_tenant_configs(tenant_id)
        
        # Filter for enabled configurations (default to True if not present)
        enabled_configs = []
        for config in configs:
            if config.get('enabled', True):
                enabled_configs.append(config)
        
        return enabled_configs
    
    def create_tenant_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new tenant delivery configuration
        
        Args:
            config_data: Dictionary containing tenant delivery configuration
            
        Returns:
            The created tenant configuration data
            
        Raises:
            DynamoDBError: For DynamoDB operation errors
        """
        try:
            # Apply defaults and timestamps
            item = self._apply_defaults(config_data)
            
            self.table.put_item(
                Item=item,
                ConditionExpression='attribute_not_exists(tenant_id) AND attribute_not_exists(#type)',
                ExpressionAttributeNames={'#type': 'type'}
            )
            
            logger.info(f"Created tenant delivery config: {config_data['tenant_id']}/{config_data['type']}")
            return item
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                raise DynamoDBError(f"Tenant '{config_data['tenant_id']}' delivery configuration '{config_data['type']}' already exists")
            logger.error(f"DynamoDB error creating tenant config: {error_code}")
            raise DynamoDBError(f"Failed to create tenant configuration: {error_code}")
    
    def update_tenant_config(self, tenant_id: str, delivery_type: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing tenant delivery configuration
        
        Args:
            tenant_id: The tenant identifier
            delivery_type: The delivery configuration type
            update_data: Dictionary containing updated configuration
            
        Returns:
            The updated tenant configuration data
            
        Raises:
            TenantNotFoundError: If configuration is not found
            DynamoDBError: For other DynamoDB errors
        """
        try:
            # Build update expression
            update_expr_parts = []
            expr_attr_values = {}
            expr_attr_names = {}
            
            # Always update the updated_at timestamp
            update_data = update_data.copy()
            update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            for key, value in update_data.items():
                if key not in ['tenant_id', 'type']:  # Don't update the primary keys
                    placeholder = f":{key}"
                    attr_name = f"#{key}"
                    update_expr_parts.append(f"{attr_name} = {placeholder}")
                    expr_attr_values[placeholder] = value
                    expr_attr_names[attr_name] = key
            
            if not update_expr_parts:
                raise DynamoDBError("No fields to update")
            
            update_expression = "SET " + ", ".join(update_expr_parts)
            
            # Add expression attribute name for the condition expression
            expr_attr_names['#delivery_type'] = 'type'
            
            response = self.table.update_item(
                Key={
                    'tenant_id': tenant_id,
                    'type': delivery_type
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expr_attr_values,
                ExpressionAttributeNames=expr_attr_names,
                ConditionExpression='attribute_exists(tenant_id) AND attribute_exists(#delivery_type)',
                ReturnValues='ALL_NEW'
            )
            
            logger.info(f"Updated tenant delivery config: {tenant_id}/{delivery_type}")
            return dict(response['Attributes'])
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                raise TenantNotFoundError(f"Tenant '{tenant_id}' delivery configuration '{delivery_type}' not found")
            logger.error(f"DynamoDB error updating tenant config {tenant_id}/{delivery_type}: {error_code}")
            raise DynamoDBError(f"Failed to update tenant configuration: {error_code}")
    
    def patch_tenant_config(self, tenant_id: str, delivery_type: str, patch_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Partially update a tenant delivery configuration
        
        Args:
            tenant_id: The tenant identifier
            delivery_type: The delivery configuration type
            patch_data: Dictionary containing fields to update
            
        Returns:
            The updated tenant configuration data
            
        Raises:
            TenantNotFoundError: If configuration is not found
            DynamoDBError: For other DynamoDB errors
        """
        return self.update_tenant_config(tenant_id, delivery_type, patch_data)
    
    def delete_tenant_config(self, tenant_id: str, delivery_type: str) -> bool:
        """
        Delete a tenant delivery configuration
        
        Args:
            tenant_id: The tenant identifier
            delivery_type: The delivery configuration type
            
        Returns:
            True if configuration was deleted
            
        Raises:
            TenantNotFoundError: If configuration is not found
            DynamoDBError: For other DynamoDB errors
        """
        try:
            self.table.delete_item(
                Key={
                    'tenant_id': tenant_id,
                    'type': delivery_type
                },
                ConditionExpression='attribute_exists(tenant_id) AND attribute_exists(#type)',
                ExpressionAttributeNames={'#type': 'type'}
            )
            
            logger.info(f"Deleted tenant delivery config: {tenant_id}/{delivery_type}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                raise TenantNotFoundError(f"Tenant '{tenant_id}' delivery configuration '{delivery_type}' not found")
            logger.error(f"DynamoDB error deleting tenant config {tenant_id}/{delivery_type}: {error_code}")
            raise DynamoDBError(f"Failed to delete tenant configuration: {error_code}")
    
    def list_tenant_configs(self, limit: int = 50, last_key: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        List tenant delivery configurations with pagination
        
        Args:
            limit: Maximum number of configurations to return
            last_key: Last evaluated key for pagination (dict with tenant_id and type)
            
        Returns:
            Dictionary containing configurations list and pagination info
            
        Raises:
            DynamoDBError: For DynamoDB operation errors
        """
        try:
            scan_kwargs = {
                'Limit': limit
            }
            
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = last_key
            
            response = self.table.scan(**scan_kwargs)
            
            configurations = [dict(item) for item in response.get('Items', [])]
            
            result = {
                'configurations': configurations,
                'count': len(configurations),
                'limit': limit
            }
            
            if 'LastEvaluatedKey' in response:
                result['last_key'] = f"{response['LastEvaluatedKey']['tenant_id']}#{response['LastEvaluatedKey']['type']}"
            
            return result
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB error listing tenant configs: {error_code}")
            raise DynamoDBError(f"Failed to list tenant configurations: {error_code}")
    
    def validate_tenant_config(self, tenant_id: str, delivery_type: str) -> Dict[str, Any]:
        """
        Validate a tenant delivery configuration
        
        Args:
            tenant_id: The tenant identifier
            delivery_type: The delivery configuration type
            
        Returns:
            Dictionary containing validation results
            
        Raises:
            TenantNotFoundError: If configuration is not found
            DynamoDBError: For other DynamoDB errors
        """
        config = self.get_tenant_config(tenant_id, delivery_type)
        
        validation_results = {
            'tenant_id': tenant_id,
            'type': delivery_type,
            'valid': True,
            'checks': []
        }
        
        # Common field validation
        common_fields = ['tenant_id', 'type']
        for field in common_fields:
            if field not in config or not config[field]:
                validation_results['valid'] = False
                validation_results['checks'].append({
                    'field': field,
                    'status': 'missing',
                    'message': f'Required field {field} is missing or empty'
                })
            else:
                validation_results['checks'].append({
                    'field': field,
                    'status': 'ok',
                    'message': f'Field {field} is present'
                })
        
        # Type-specific validation
        if delivery_type == 'cloudwatch':
            required_fields = ['log_distribution_role_arn', 'log_group_name']
            
            for field in required_fields:
                if field not in config or not config[field]:
                    validation_results['valid'] = False
                    validation_results['checks'].append({
                        'field': field,
                        'status': 'missing',
                        'message': f'Required CloudWatch field {field} is missing or empty'
                    })
                else:
                    validation_results['checks'].append({
                        'field': field,
                        'status': 'ok',
                        'message': f'CloudWatch field {field} is present'
                    })
            
            # Role ARN format validation
            role_arn = config.get('log_distribution_role_arn', '')
            if role_arn and not role_arn.startswith('arn:aws:iam::'):
                validation_results['valid'] = False
                validation_results['checks'].append({
                    'field': 'log_distribution_role_arn',
                    'status': 'invalid',
                    'message': 'Role ARN format is invalid'
                })
        
        elif delivery_type == 's3':
            required_fields = ['bucket_name']
            
            for field in required_fields:
                if field not in config or not config[field]:
                    validation_results['valid'] = False
                    validation_results['checks'].append({
                        'field': field,
                        'status': 'missing',
                        'message': f'Required S3 field {field} is missing or empty'
                    })
                else:
                    validation_results['checks'].append({
                        'field': field,
                        'status': 'ok',
                        'message': f'S3 field {field} is present'
                    })
            
            # S3 bucket name validation (basic)
            bucket_name = config.get('bucket_name', '')
            if bucket_name and not bucket_name.replace('-', '').replace('.', '').isalnum():
                validation_results['valid'] = False
                validation_results['checks'].append({
                    'field': 'bucket_name',
                    'status': 'invalid',
                    'message': 'S3 bucket name format appears invalid'
                })
        
        # Region validation (basic)
        target_region = config.get('target_region', '')
        if target_region and not target_region.replace('-', '').replace('_', '').isalnum():
            validation_results['valid'] = False
            validation_results['checks'].append({
                'field': 'target_region',
                'status': 'invalid',
                'message': 'Target region format appears invalid'
            })
        
        return validation_results