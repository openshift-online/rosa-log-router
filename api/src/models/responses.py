"""
Standard API response models and utilities
"""

import json
from typing import Any, Dict, Optional, Union
from datetime import datetime, timezone


def create_api_response(
    status_code: int,
    data: Any = None,
    message: str = None,
    error: str = None,
    headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Create a standardized API response
    
    Args:
        status_code: HTTP status code
        data: Response data (for successful responses)
        message: Success message
        error: Error message (for error responses)
        headers: Additional HTTP headers
        
    Returns:
        API Gateway response dictionary
    """
    # Default headers
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-API-Timestamp",
        "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    }
    
    if headers:
        default_headers.update(headers)
    
    # Create response body
    response_body = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success" if 200 <= status_code < 300 else "error"
    }
    
    if data is not None:
        response_body["data"] = data
    
    if message:
        response_body["message"] = message
    
    if error:
        response_body["error"] = error
    
    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(response_body, default=str)
    }


def success_response(data: Any = None, message: str = None, status_code: int = 200) -> Dict[str, Any]:
    """
    Create a success response
    
    Args:
        data: Response data
        message: Success message
        status_code: HTTP status code (default 200)
        
    Returns:
        API Gateway success response
    """
    return create_api_response(status_code=status_code, data=data, message=message)


def error_response(error: str, status_code: int = 400, details: Any = None) -> Dict[str, Any]:
    """
    Create an error response
    
    Args:
        error: Error message
        status_code: HTTP status code (default 400)
        details: Additional error details
        
    Returns:
        API Gateway error response
    """
    response_data = {"error": error}
    if details:
        response_data["details"] = details
    
    return create_api_response(status_code=status_code, error=error)


def not_found_response(resource: str = "Resource") -> Dict[str, Any]:
    """
    Create a 404 Not Found response
    
    Args:
        resource: Name of the resource that was not found
        
    Returns:
        API Gateway 404 response
    """
    return error_response(f"{resource} not found", status_code=404)


def validation_error_response(errors: Union[str, list]) -> Dict[str, Any]:
    """
    Create a 400 Bad Request response for validation errors
    
    Args:
        errors: Validation error message(s)
        
    Returns:
        API Gateway 400 response
    """
    if isinstance(errors, str):
        error_msg = errors
        details = None
    else:
        error_msg = "Validation failed"
        details = errors
    
    return create_api_response(
        status_code=400,
        error=error_msg,
        data={"validation_errors": details} if details else None
    )


def internal_error_response(message: str = "Internal server error") -> Dict[str, Any]:
    """
    Create a 500 Internal Server Error response
    
    Args:
        message: Error message
        
    Returns:
        API Gateway 500 response
    """
    return error_response(message, status_code=500)