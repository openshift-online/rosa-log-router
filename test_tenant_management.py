#!/usr/bin/env python3
"""
Test script for tenant configuration management
Demonstrates adding, updating, and querying tenant configurations in DynamoDB
"""

import boto3
import json
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List

# AWS Configuration
AWS_PROFILE = 'scuppett-dev'
AWS_REGION = 'us-east-2'
TABLE_NAME = 'multi-tenant-logging-development-tenant-configs'

def get_dynamodb_client():
    """Create DynamoDB client"""
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return session.client('dynamodb')

def put_tenant_config(tenant_id: str, config: Dict[str, Any]) -> bool:
    """Add or update a tenant configuration"""
    dynamodb = get_dynamodb_client()
    
    # Prepare DynamoDB item
    item = {
        'tenant_id': {'S': tenant_id},
        'log_distribution_role_arn': {'S': config['log_distribution_role_arn']},
        'log_group_name': {'S': config['log_group_name']},
        'target_region': {'S': config['target_region']},
        'enabled': {'BOOL': config.get('enabled', True)},
        'created_at': {'S': datetime.now(timezone.utc).isoformat()},
        'updated_at': {'S': datetime.now(timezone.utc).isoformat()}
    }
    
    # Add desired_logs if specified
    if 'desired_logs' in config and config['desired_logs']:
        item['desired_logs'] = {'SS': config['desired_logs']}
    
    try:
        response = dynamodb.put_item(
            TableName=TABLE_NAME,
            Item=item
        )
        print(f"✅ Successfully added/updated tenant '{tenant_id}'")
        return True
    except Exception as e:
        print(f"❌ Failed to add tenant '{tenant_id}': {str(e)}")
        return False

def get_tenant_config(tenant_id: str) -> Dict[str, Any]:
    """Get a tenant configuration"""
    dynamodb = get_dynamodb_client()
    
    try:
        response = dynamodb.get_item(
            TableName=TABLE_NAME,
            Key={'tenant_id': {'S': tenant_id}}
        )
        
        if 'Item' not in response:
            print(f"❌ Tenant '{tenant_id}' not found")
            return {}
        
        # Convert DynamoDB item to Python dict
        item = response['Item']
        config = {
            'tenant_id': item['tenant_id']['S'],
            'log_distribution_role_arn': item['log_distribution_role_arn']['S'],
            'log_group_name': item['log_group_name']['S'],
            'target_region': item['target_region']['S'],
            'enabled': item.get('enabled', {}).get('BOOL', True),
            'created_at': item.get('created_at', {}).get('S', ''),
            'updated_at': item.get('updated_at', {}).get('S', '')
        }
        
        # Add desired_logs if present
        if 'desired_logs' in item and 'SS' in item['desired_logs']:
            config['desired_logs'] = item['desired_logs']['SS']
        
        return config
    except Exception as e:
        print(f"❌ Failed to get tenant '{tenant_id}': {str(e)}")
        return {}

def list_tenants() -> List[Dict[str, Any]]:
    """List all tenant configurations"""
    dynamodb = get_dynamodb_client()
    
    try:
        response = dynamodb.scan(TableName=TABLE_NAME)
        
        tenants = []
        for item in response['Items']:
            config = {
                'tenant_id': item['tenant_id']['S'],
                'enabled': item.get('enabled', {}).get('BOOL', True),
                'target_region': item['target_region']['S'],
                'log_group_name': item['log_group_name']['S']
            }
            tenants.append(config)
        
        return tenants
    except Exception as e:
        print(f"❌ Failed to list tenants: {str(e)}")
        return []

def disable_tenant(tenant_id: str) -> bool:
    """Disable a tenant by setting enabled=false"""
    dynamodb = get_dynamodb_client()
    
    try:
        response = dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={'tenant_id': {'S': tenant_id}},
            UpdateExpression='SET enabled = :val, updated_at = :time',
            ExpressionAttributeValues={
                ':val': {'BOOL': False},
                ':time': {'S': datetime.now(timezone.utc).isoformat()}
            }
        )
        print(f"✅ Successfully disabled tenant '{tenant_id}'")
        return True
    except Exception as e:
        print(f"❌ Failed to disable tenant '{tenant_id}': {str(e)}")
        return False

def enable_tenant(tenant_id: str) -> bool:
    """Enable a tenant by setting enabled=true"""
    dynamodb = get_dynamodb_client()
    
    try:
        response = dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={'tenant_id': {'S': tenant_id}},
            UpdateExpression='SET enabled = :val, updated_at = :time',
            ExpressionAttributeValues={
                ':val': {'BOOL': True},
                ':time': {'S': datetime.now(timezone.utc).isoformat()}
            }
        )
        print(f"✅ Successfully enabled tenant '{tenant_id}'")
        return True
    except Exception as e:
        print(f"❌ Failed to enable tenant '{tenant_id}': {str(e)}")
        return False

def main():
    """Test tenant management functionality"""
    print("🧪 Testing tenant configuration management")
    print("=" * 50)
    
    # Test data - Example tenant configurations
    test_tenants = [
        {
            'tenant_id': 'acme-corp',
            'config': {
                'log_distribution_role_arn': 'arn:aws:iam::123456789012:role/LogDistributionRole',
                'log_group_name': '/aws/logs/acme-corp',
                'target_region': 'us-east-1',
                'enabled': True,
                'desired_logs': ['payment-service', 'user-service', 'api-gateway']
            }
        },
        {
            'tenant_id': 'demo-company',
            'config': {
                'log_distribution_role_arn': 'arn:aws:iam::987654321098:role/CustomerLogDistribution',
                'log_group_name': '/aws/logs/demo-company',
                'target_region': 'us-west-2',
                'enabled': True
            }
        },
        {
            'tenant_id': 'test-org',
            'config': {
                'log_distribution_role_arn': 'arn:aws:iam::555666777888:role/TestOrgLogRole',
                'log_group_name': '/aws/logs/test-org',
                'target_region': 'eu-west-1',
                'enabled': False  # Start disabled for testing
            }
        }
    ]
    
    print("1. Adding test tenant configurations...")
    for tenant in test_tenants:
        put_tenant_config(tenant['tenant_id'], tenant['config'])
    
    print("\n2. Listing all tenants...")
    tenants = list_tenants()
    for tenant in tenants:
        status = "✅ Enabled" if tenant['enabled'] else "❌ Disabled"
        print(f"   {tenant['tenant_id']}: {status} -> {tenant['log_group_name']} ({tenant['target_region']})")
    
    print("\n3. Getting detailed configuration for 'acme-corp'...")
    config = get_tenant_config('acme-corp')
    if config:
        print(f"   Tenant ID: {config['tenant_id']}")
        print(f"   Role ARN: {config['log_distribution_role_arn']}")
        print(f"   Log Group: {config['log_group_name']}")
        print(f"   Region: {config['target_region']}")
        print(f"   Enabled: {config['enabled']}")
        if 'desired_logs' in config:
            print(f"   Desired Apps: {', '.join(config['desired_logs'])}")
    
    print("\n4. Testing tenant enable/disable...")
    print("   Disabling 'demo-company'...")
    disable_tenant('demo-company')
    
    print("   Enabling 'test-org'...")
    enable_tenant('test-org')
    
    print("\n5. Final tenant status...")
    tenants = list_tenants()
    for tenant in tenants:
        status = "✅ Enabled" if tenant['enabled'] else "❌ Disabled"
        print(f"   {tenant['tenant_id']}: {status}")
    
    print("\n✅ Tenant management testing completed!")
    print(f"💡 You can now use these tenants to test log processing with the enabled field")

if __name__ == '__main__':
    main()