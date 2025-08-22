"""
Health check handler for the tenant management API
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_health_status() -> Dict[str, Any]:
    """
    Get basic health status information
    
    Returns:
        Dictionary containing health status
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "tenant-management-api",
        "version": "1.0.0",
        "uptime_seconds": int(time.time() - 0)  # Simplified for Lambda
    }


def handle_health_check(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle health check requests
    
    Args:
        event: API Gateway event
        
    Returns:
        Health check response
    """
    try:
        health_data = get_health_status()
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-API-Timestamp",
                "Access-Control-Allow-Methods": "GET,OPTIONS"
            },
            "body": json.dumps(health_data)
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        
        error_response = {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "Internal server error"
        }
        
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(error_response)
        }