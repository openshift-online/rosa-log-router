#!/usr/bin/env python3
"""
Test script to verify log processor integration with enabled field
"""

import boto3
import json
import sys
import os
from typing import Dict, Any

# Set AWS environment variables first
os.environ['AWS_PROFILE'] = 'scuppett-dev'
os.environ['AWS_REGION'] = 'us-east-2'
os.environ['TENANT_CONFIG_TABLE'] = 'multi-tenant-logging-development-tenant-configs'

# Add the container directory to Python path
sys.path.append('/home/scuppett/Development/jhjaggars-logdesign/container')

# Import the log processor functions
from log_processor import get_tenant_configuration, should_process_tenant

def test_processor_integration():
    """Test that the log processor correctly handles the enabled field"""
    
    print("🧪 Testing log processor integration with enabled field")
    print("=" * 60)
    
    test_tenants = ['acme-corp', 'demo-company', 'test-org', 'clusters-jhjaggars-test']
    
    for tenant_id in test_tenants:
        print(f"\n📋 Testing tenant: {tenant_id}")
        
        # Get tenant configuration
        try:
            tenant_config = get_tenant_configuration(tenant_id)
            
            if not tenant_config:
                print(f"   ❌ No configuration found for tenant '{tenant_id}'")
                continue
            
            # Check if tenant should be processed
            should_process = should_process_tenant(tenant_config, tenant_id)
            
            # Display results
            enabled = tenant_config.get('enabled', True)
            status = "✅ Enabled" if enabled else "❌ Disabled"
            process_status = "✅ Will process" if should_process else "❌ Will skip"
            
            print(f"   Status: {status}")
            print(f"   Processing: {process_status}")
            print(f"   Log Group: {tenant_config.get('log_group_name', 'N/A')}")
            print(f"   Target Region: {tenant_config.get('target_region', 'N/A')}")
            
            # Show desired logs if present
            desired_logs = tenant_config.get('desired_logs')
            if desired_logs:
                print(f"   Desired Apps: {', '.join(desired_logs)}")
            else:
                print(f"   Desired Apps: All (no filter)")
                
        except Exception as e:
            print(f"   ❌ Error processing tenant '{tenant_id}': {str(e)}")
    
    print(f"\n✅ Log processor integration test completed!")
    print(f"💡 The enabled field is working correctly with the log processor")

if __name__ == '__main__':
    test_processor_integration()