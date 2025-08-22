"""
Logging configuration for the API service
"""

import logging
import os
import sys


def setup_logging(level: str = None) -> logging.Logger:
    """
    Set up logging configuration for the API service
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        
    Returns:
        Configured logger instance
    """
    # Get log level from environment or use default
    if level is None:
        level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    # Create logger for our service
    logger = logging.getLogger('tenant-api')
    logger.setLevel(getattr(logging, level, logging.INFO))
    
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance
    
    Args:
        name: Logger name (defaults to calling module)
        
    Returns:
        Logger instance
    """
    if name is None:
        name = 'tenant-api'
    
    return logging.getLogger(name)