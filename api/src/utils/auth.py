"""
Authentication utilities for HMAC-based request signing and validation
"""

import hmac
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional, Tuple
import boto3
import logging

logger = logging.getLogger(__name__)

# Cache for psk values to reduce API calls
_psk_cache = {}
_cache_ttl = 300  # 5 minutes


class AuthenticationError(Exception):
    """Raised when authentication fails"""
    pass


def get_psk_from_secrets_manager(secret_name: str, region: str) -> str:
    """
    Retrieve PSK from AWS Secrets Manager with caching
    
    Args:
        secret_name: Name of the secret containing the PSK
        region: AWS region for Secrets Manager client
        
    Returns:
        The PSK value as a string
        
    Raises:
        AuthenticationError: If secret cannot be retrieved
    """
    cache_key = f"{region}:{secret_name}"
    current_time = time.time()
    
    # Check cache first
    if cache_key in _psk_cache:
        cached_value, cached_time = _psk_cache[cache_key]
        if current_time - cached_time < _cache_ttl:
            return cached_value
    
    try:
        secrets_client = boto3.client('secretsmanager', region_name=region)
        response = secrets_client.get_secret_value(SecretId=secret_name)
        psk = response['SecretString']
        
        # Cache the value
        _psk_cache[cache_key] = (psk, current_time)
        
        return psk
        
    except Exception as e:
        logger.error(f"Failed to retrieve PSK from Secrets Manager secret {secret_name}: {str(e)}")
        raise AuthenticationError(f"Failed to retrieve authentication key")


def generate_signature(psk: str, method: str, uri: str, timestamp: str, body: str = "", include_body: bool = True) -> str:
    """
    Generate HMAC-SHA256 signature for a request
    
    Args:
        psk: Pre-shared key for signing
        method: HTTP method (GET, POST, etc.)
        uri: Request URI including query parameters
        timestamp: ISO timestamp string
        body: Request body (empty string for GET requests)
        include_body: Whether to include body hash in signature (False for API Gateway authorizers)
        
    Returns:
        Hex-encoded HMAC-SHA256 signature
    """
    if include_body:
        # Calculate body hash
        body_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()
        # Create message to sign: METHOD + URI + TIMESTAMP + BODY_HASH
        message = f"{method.upper()}{uri}{timestamp}{body_hash}"
    else:
        # For API Gateway authorizers that don't have access to body
        # Create message to sign: METHOD + URI + TIMESTAMP
        message = f"{method.upper()}{uri}{timestamp}"
    
    # Generate HMAC-SHA256 signature
    signature = hmac.new(
        psk.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature


def validate_timestamp(timestamp_str: str, max_age_seconds: int = 300) -> bool:
    """
    Validate that timestamp is within acceptable range
    
    Args:
        timestamp_str: ISO timestamp string
        max_age_seconds: Maximum age in seconds (default 5 minutes)
        
    Returns:
        True if timestamp is valid, False otherwise
    """
    try:
        # Parse timestamp
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        
        request_time = datetime.fromisoformat(timestamp_str)
        current_time = datetime.now(timezone.utc)
        
        # Ensure request_time is timezone-aware
        if request_time.tzinfo is None:
            request_time = request_time.replace(tzinfo=timezone.utc)
        
        # Check if timestamp is within acceptable range
        time_diff = abs((current_time - request_time).total_seconds())
        
        return time_diff <= max_age_seconds
        
    except Exception as e:
        logger.warning(f"Invalid timestamp format: {timestamp_str}, error: {str(e)}")
        return False


def validate_request_signature(
    psk: str,
    method: str,
    uri: str,
    timestamp: str,
    provided_signature: str,
    body: str = "",
    include_body: bool = True
) -> bool:
    """
    Validate HMAC signature for a request
    
    Args:
        psk: Pre-shared key for validation
        method: HTTP method
        uri: Request URI
        timestamp: Request timestamp
        provided_signature: Signature from Authorization header
        body: Request body
        include_body: Whether to include body in signature validation
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Generate expected signature
        expected_signature = generate_signature(psk, method, uri, timestamp, body, include_body)
        
        # Calculate message for detailed logging
        if include_body:
            body_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()
            message = f"{method.upper()}{uri}{timestamp}{body_hash}"
        else:
            body_hash = "N/A (excluded)"
            message = f"{method.upper()}{uri}{timestamp}"
        
        # Log signature validation details
        print(f"SIGNATURE VALIDATION:")
        print(f"  Method: '{method}'")
        print(f"  URI: '{uri}'")
        print(f"  Timestamp: '{timestamp}'")
        print(f"  Body: '{body}'")
        print(f"  Body length: {len(body)}")
        print(f"  Include body: {include_body}")
        print(f"  Body hash: {body_hash}")
        print(f"  Message: '{message}'")
        print(f"  Expected signature: {expected_signature}")
        print(f"  Provided signature: {provided_signature}")
        
        # Use constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(expected_signature, provided_signature)
        logger.info(f"  Signature valid: {is_valid}")
        
        return is_valid
        
    except Exception as e:
        logger.warning(f"Signature validation error: {str(e)}")
        return False


def extract_auth_headers(headers: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract authentication headers from request
    
    Args:
        headers: Dictionary of HTTP headers (case-insensitive keys expected)
        
    Returns:
        Tuple of (timestamp, signature) or (None, None) if not found
    """
    # Convert headers to lowercase for case-insensitive lookup
    headers_lower = {k.lower(): v for k, v in headers.items()}
    
    timestamp = headers_lower.get('x-api-timestamp')
    
    # Extract signature from Authorization header
    auth_header = headers_lower.get('authorization', '')
    signature = None
    
    if auth_header.startswith('HMAC-SHA256 '):
        signature = auth_header[12:]  # Remove 'HMAC-SHA256 ' prefix
    
    return timestamp, signature


def authenticate_request(
    headers: dict,
    method: str,
    uri: str,
    body: str,
    psk_secret_name: str,
    region: str
) -> bool:
    """
    Complete request authentication workflow
    
    Args:
        headers: Request headers
        method: HTTP method
        uri: Request URI
        body: Request body
        psk_secret_name: Secrets Manager secret name for PSK
        region: AWS region
        
    Returns:
        True if request is authenticated, False otherwise
        
    Raises:
        AuthenticationError: If PSK cannot be retrieved
    """
    # Extract authentication headers
    timestamp, signature = extract_auth_headers(headers)
    
    if not timestamp or not signature:
        logger.warning("Missing authentication headers")
        return False
    
    # Validate timestamp
    if not validate_timestamp(timestamp):
        logger.warning(f"Invalid or expired timestamp: {timestamp}")
        return False
    
    # Get PSK from Secrets Manager
    psk = get_psk_from_secrets_manager(psk_secret_name, region)
    
    # Validate signature (exclude body for API Gateway authorizers)
    if not validate_request_signature(psk, method, uri, timestamp, signature, body, include_body=False):
        logger.warning("Invalid request signature")
        return False
    
    return True