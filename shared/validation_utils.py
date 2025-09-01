"""
Shared validation utilities for both API and container components
"""


def normalize_bucket_prefix(prefix: str) -> str:
    """
    Normalize S3 bucket prefix by ensuring it ends with a slash.
    
    Args:
        prefix: S3 bucket prefix string
        
    Returns:
        Normalized prefix with trailing slash
    """
    if prefix and not prefix.endswith('/'):
        return prefix + '/'
    return prefix