"""
Pydantic models for tenant delivery configuration validation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../shared'))

from typing import List, Optional, Union, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
# from validation_utils import normalize_bucket_prefix


# Shared validation utilities
def normalize_bucket_prefix(prefix: str) -> str:
    """Normalize S3 bucket prefix by ensuring it ends with a slash"""
    if not prefix:
        return ""
    return prefix if prefix.endswith('/') else prefix + '/'

def validate_iam_role_arn(arn: Optional[str]) -> Optional[str]:
    """Shared validator for IAM role ARN format"""
    if arn is not None and not arn.startswith('arn:aws:iam::'):
        raise ValueError('Role ARN must be a valid IAM role ARN')
    return arn


def validate_aws_region(region: Optional[str]) -> Optional[str]:
    """Shared validator for AWS region format"""
    if region is not None and not region.replace('-', '').isalnum():
        raise ValueError('Region must be a valid AWS region')
    return region


def validate_desired_logs_list(logs: Optional[List[str]]) -> Optional[List[str]]:
    """Shared validator for desired_logs list"""
    if logs is not None:
        if not isinstance(logs, list):
            raise ValueError('desired_logs must be a list')
        for app in logs:
            if not isinstance(app, str) or len(app.strip()) == 0:
                raise ValueError('All items in desired_logs must be non-empty strings')
    return logs


def validate_delivery_type_fields(type_value: str, **fields) -> None:
    """Shared validator for type-specific required fields"""
    if type_value == "cloudwatch":
        if not fields.get('log_distribution_role_arn'):
            raise ValueError("log_distribution_role_arn is required for CloudWatch delivery")
        if not fields.get('log_group_name'):
            raise ValueError("log_group_name is required for CloudWatch delivery")
    elif type_value == "s3":
        if not fields.get('bucket_name'):
            raise ValueError("bucket_name is required for S3 delivery")


class TenantDeliveryConfigBase(BaseModel):
    """Base model for tenant delivery configuration"""
    tenant_id: str = Field(..., min_length=1, max_length=128, description="Unique tenant identifier")
    type: Literal["cloudwatch", "s3"] = Field(..., description="Delivery configuration type")
    enabled: Optional[bool] = Field(default=None, description="Enable/disable this delivery configuration (defaults to True)")
    desired_logs: Optional[List[str]] = Field(default=None, description="List of application names to process (defaults to all applications)")
    target_region: Optional[str] = Field(default=None, description="AWS region for delivery (defaults to processor region)")
    ttl: Optional[int] = Field(default=None, description="Unix timestamp for DynamoDB TTL expiration")
    created_at: Optional[datetime] = Field(default=None, description="Configuration creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Configuration last update timestamp")
    
    @field_validator('tenant_id')
    @classmethod
    def validate_tenant_id(cls, v):
        """Validate tenant ID format"""
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('tenant_id must contain only alphanumeric characters, hyphens, and underscores')
        return v
    
    @field_validator('target_region')
    @classmethod
    def validate_region(cls, v):
        """Validate AWS region format"""
        if v is not None and not v.replace('-', '').isalnum():
            raise ValueError('target_region must be a valid AWS region')
        return v
    
    @field_validator('desired_logs')
    @classmethod
    def validate_desired_logs(cls, v):
        """Validate desired_logs list"""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError('desired_logs must be a list')
            for app in v:
                if not isinstance(app, str) or len(app.strip()) == 0:
                    raise ValueError('All items in desired_logs must be non-empty strings')
        return v


class CloudWatchDeliveryConfig(TenantDeliveryConfigBase):
    """Model for CloudWatch delivery configuration"""
    type: Literal["cloudwatch"] = Field(default="cloudwatch", description="CloudWatch delivery type")
    log_distribution_role_arn: str = Field(..., min_length=1, description="ARN of the customer's IAM role for log delivery")
    log_group_name: str = Field(..., min_length=1, description="CloudWatch Logs group name for log delivery")
    
    @field_validator('log_distribution_role_arn')
    @classmethod
    def validate_role_arn(cls, v):
        """Validate IAM role ARN format"""
        if not v.startswith('arn:aws:iam::'):
            raise ValueError('log_distribution_role_arn must be a valid IAM role ARN')
        return v


class S3DeliveryConfig(TenantDeliveryConfigBase):
    """Model for S3 delivery configuration"""
    type: Literal["s3"] = Field(default="s3", description="S3 delivery type")
    bucket_name: str = Field(..., min_length=1, description="Target S3 bucket name")
    bucket_prefix: Optional[str] = Field(default="ROSA/cluster-logs/", description="S3 object prefix")
    
    @field_validator('bucket_name')
    @classmethod
    def validate_bucket_name(cls, v):
        """Validate S3 bucket name format"""
        if not v.replace('-', '').replace('.', '').isalnum():
            raise ValueError('bucket_name must be a valid S3 bucket name')
        return v
    
    @field_validator('bucket_prefix')
    @classmethod
    def validate_bucket_prefix(cls, v):
        """Validate S3 bucket prefix format"""
        if v is not None:
            return normalize_bucket_prefix(v)
        return v


class TenantDeliveryConfigCreateRequest(BaseModel):
    """Model for creating tenant delivery configurations"""
    tenant_id: str = Field(..., min_length=1, max_length=128, description="Unique tenant identifier")
    type: Literal["cloudwatch", "s3"] = Field(..., description="Delivery configuration type")
    enabled: Optional[bool] = Field(default=None, description="Enable/disable this delivery configuration")
    desired_logs: Optional[List[str]] = Field(default=None, description="List of application names to process")
    target_region: Optional[str] = Field(default=None, description="AWS region for delivery")
    ttl: Optional[int] = Field(default=None, description="Unix timestamp for DynamoDB TTL expiration")
    
    # CloudWatch-specific fields
    log_distribution_role_arn: Optional[str] = Field(default=None, description="ARN of the customer's IAM role for log delivery")
    log_group_name: Optional[str] = Field(default=None, description="CloudWatch Logs group name for log delivery")
    
    # S3-specific fields
    bucket_name: Optional[str] = Field(default=None, description="Target S3 bucket name")
    bucket_prefix: Optional[str] = Field(default=None, description="S3 object prefix")
    
    @field_validator('tenant_id')
    @classmethod
    def validate_tenant_id(cls, v):
        """Validate tenant ID format"""
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('tenant_id must contain only alphanumeric characters, hyphens, and underscores')
        return v
    
    @field_validator('log_distribution_role_arn')
    @classmethod
    def validate_role_arn(cls, v):
        """Validate IAM role ARN format"""
        if v is not None and not v.startswith('arn:aws:iam::'):
            raise ValueError('log_distribution_role_arn must be a valid IAM role ARN')
        return v
    
    @field_validator('bucket_name')
    @classmethod
    def validate_bucket_name(cls, v):
        """Validate S3 bucket name format"""
        if v is not None and not v.replace('-', '').replace('.', '').isalnum():
            raise ValueError('bucket_name must be a valid S3 bucket name')
        return v
    
    @field_validator('desired_logs')
    @classmethod
    def validate_desired_logs(cls, v):
        """Validate desired_logs list"""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError('desired_logs must be a list')
            for app in v:
                if not isinstance(app, str) or len(app.strip()) == 0:
                    raise ValueError('All items in desired_logs must be non-empty strings')
        return v


    def model_post_init(self, __context) -> None:
        """Validate type-specific required fields"""
        validate_delivery_type_fields(
            self.type,
            log_distribution_role_arn=self.log_distribution_role_arn,
            log_group_name=self.log_group_name,
            bucket_name=self.bucket_name
        )


class TenantDeliveryConfigUpdateRequest(BaseModel):
    """Model for updating tenant delivery configurations"""
    enabled: Optional[bool] = Field(default=None, description="Enable/disable this delivery configuration")
    desired_logs: Optional[List[str]] = Field(default=None, description="List of application names to process")
    target_region: Optional[str] = Field(default=None, description="AWS region for delivery")
    ttl: Optional[int] = Field(default=None, description="Unix timestamp for DynamoDB TTL expiration")
    
    # CloudWatch-specific fields
    log_distribution_role_arn: Optional[str] = Field(default=None, description="ARN of the customer's IAM role for log delivery")
    log_group_name: Optional[str] = Field(default=None, description="CloudWatch Logs group name for log delivery")
    
    # S3-specific fields
    bucket_name: Optional[str] = Field(default=None, description="Target S3 bucket name")
    bucket_prefix: Optional[str] = Field(default=None, description="S3 object prefix")
    
    @field_validator('log_distribution_role_arn')
    @classmethod
    def validate_role_arn(cls, v):
        """Validate IAM role ARN format"""
        if v is not None and not v.startswith('arn:aws:iam::'):
            raise ValueError('log_distribution_role_arn must be a valid IAM role ARN')
        return v
    
    @field_validator('target_region')
    @classmethod
    def validate_region(cls, v):
        """Validate AWS region format"""
        if v is not None and not v.replace('-', '').isalnum():
            raise ValueError('target_region must be a valid AWS region')
        return v

    @field_validator('desired_logs')
    @classmethod
    def validate_desired_logs(cls, v):
        """Validate desired_logs list"""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError('desired_logs must be a list')
            for app in v:
                if not isinstance(app, str) or len(app.strip()) == 0:
                    raise ValueError('All items in desired_logs must be non-empty strings')
        return v


class TenantDeliveryConfigPatchRequest(BaseModel):
    """Model for partial updates to tenant delivery configurations"""
    enabled: Optional[bool] = Field(default=None, description="Enable/disable this delivery configuration")
    desired_logs: Optional[List[str]] = Field(default=None, description="List of application names to process")

    @field_validator('desired_logs')
    @classmethod
    def validate_desired_logs(cls, v):
        """Validate desired_logs list"""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError('desired_logs must be a list')
            for app in v:
                if not isinstance(app, str) or len(app.strip()) == 0:
                    raise ValueError('All items in desired_logs must be non-empty strings')
        return v


# Union type for responses
TenantDeliveryConfigResponse = Union[CloudWatchDeliveryConfig, S3DeliveryConfig]


class TenantDeliveryConfigListResponse(BaseModel):
    """Model for tenant delivery configuration list response"""
    configurations: List[TenantDeliveryConfigResponse]
    count: int
    limit: int
    last_key: Optional[str] = None


class ValidationCheck(BaseModel):
    """Model for individual validation check"""
    field: str
    status: str  # 'ok', 'missing', 'invalid'
    message: str


class TenantDeliveryConfigValidationResponse(BaseModel):
    """Model for tenant delivery configuration validation response"""
    tenant_id: str
    type: str
    valid: bool
    checks: List[ValidationCheck]