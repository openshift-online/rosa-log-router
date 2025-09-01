"""
Main API handler for the tenant management service
"""

import os
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from mangum import Mangum
from pydantic import ValidationError

# Import our utilities
from src.models.responses import success_response, error_response, not_found_response, validation_error_response
from src.utils.logger import setup_logging
from src.services.dynamo import TenantDeliveryConfigService, TenantNotFoundError, DynamoDBError
from src.models.tenant import (
    TenantDeliveryConfigCreateRequest, TenantDeliveryConfigUpdateRequest, TenantDeliveryConfigPatchRequest,
    TenantDeliveryConfigResponse, TenantDeliveryConfigListResponse, TenantDeliveryConfigValidationResponse
)

# Set up logging
logger = setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Multi-Tenant Logging Configuration API",
    description="REST API for managing multi-tenant logging delivery configurations (CloudWatch and S3)",
    version="2.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc"
)

# CORS middleware removed - API does not require browser access

# Environment variables
TENANT_CONFIG_TABLE = os.environ.get('TENANT_CONFIG_TABLE', 'tenant-configurations')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Initialize tenant delivery config service
delivery_config_service = TenantDeliveryConfigService(table_name=TENANT_CONFIG_TABLE, region=AWS_REGION)

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint - no authentication required"""
    try:
        from src.handlers.health import get_health_status
        return get_health_status()
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/api/v1/delivery-configs", response_model=Dict[str, Any])
async def list_all_delivery_configs(limit: int = 50, last_key: str = None):
    """List all delivery configurations with pagination"""
    try:
        logger.info(f"Listing all delivery configs with limit={limit}, last_key={last_key}")
        
        # Parse last_key if provided (format: "tenant_id#type")
        parsed_last_key = None
        if last_key:
            try:
                tenant_id, delivery_type = last_key.split('#', 1)
                parsed_last_key = {'tenant_id': tenant_id, 'type': delivery_type}
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid last_key format. Expected 'tenant_id#type'")
        
        result = delivery_config_service.list_tenant_configs(limit=limit, last_key=parsed_last_key)
        
        return {"data": result, "status": "success"}
        
    except DynamoDBError as e:
        logger.error(f"DynamoDB error listing delivery configs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list delivery configurations")
    except Exception as e:
        logger.error(f"Unexpected error listing delivery configs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list delivery configurations")


@app.get("/api/v1/tenants/{tenant_id}/delivery-configs", response_model=Dict[str, Any])
async def list_tenant_delivery_configs(tenant_id: str):
    """List all delivery configurations for a tenant"""
    try:
        logger.info(f"Listing delivery configs for tenant: {tenant_id}")
        
        configs = delivery_config_service.get_tenant_configs(tenant_id)
        
        return {"data": {"configurations": configs, "count": len(configs)}, "status": "success"}
        
    except DynamoDBError as e:
        logger.error(f"DynamoDB error listing delivery configs for tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list delivery configurations")
    except Exception as e:
        logger.error(f"Unexpected error listing delivery configs for tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list delivery configurations")


@app.get("/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}")
async def get_tenant_delivery_config(tenant_id: str, delivery_type: str):
    """Get a specific tenant delivery configuration"""
    try:
        logger.info(f"Getting delivery config: {tenant_id}/{delivery_type}")
        
        config_data = delivery_config_service.get_tenant_config(tenant_id, delivery_type)
        return {"data": config_data, "status": "success"}
        
    except TenantNotFoundError as e:
        logger.warning(f"Delivery config not found: {tenant_id}/{delivery_type}")
        raise HTTPException(status_code=404, detail=f"Delivery configuration '{tenant_id}/{delivery_type}' not found")
    except DynamoDBError as e:
        logger.error(f"DynamoDB error getting delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get delivery configuration")
    except Exception as e:
        logger.error(f"Unexpected error getting delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get delivery configuration")


@app.post("/api/v1/tenants/{tenant_id}/delivery-configs")
async def create_tenant_delivery_config(tenant_id: str, config_data: TenantDeliveryConfigCreateRequest):
    """Create a new tenant delivery configuration"""
    try:
        # Ensure tenant_id matches URL parameter
        if config_data.tenant_id != tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id in URL must match tenant_id in request body")
        
        logger.info(f"Creating delivery config: {tenant_id}/{config_data.type}")
        
        # Convert pydantic model to dict for DynamoDB
        config_dict = config_data.model_dump(exclude_none=True)
        
        # Create delivery config in DynamoDB
        created_config = delivery_config_service.create_tenant_config(config_dict)
        
        return JSONResponse(
            status_code=201,
            content={"data": created_config, "status": "success", "message": "Delivery configuration created successfully"}
        )
        
    except DynamoDBError as e:
        logger.error(f"DynamoDB error creating delivery config: {str(e)}")
        if "already exists" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        else:
            raise HTTPException(status_code=500, detail="Failed to create delivery configuration")
    except ValidationError as e:
        logger.warning(f"Validation error creating delivery config: {str(e)}")
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        logger.error(f"Unexpected error creating delivery config: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create delivery configuration")


@app.put("/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}")
async def update_tenant_delivery_config(tenant_id: str, delivery_type: str, config_data: TenantDeliveryConfigUpdateRequest):
    """Update a tenant delivery configuration"""
    try:
        logger.info(f"Updating delivery config: {tenant_id}/{delivery_type}")
        
        # Convert pydantic model to dict, excluding None values
        update_dict = config_data.model_dump(exclude_none=True)
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields provided for update")
        
        # Update delivery config in DynamoDB
        updated_config = delivery_config_service.update_tenant_config(tenant_id, delivery_type, update_dict)
        
        return {"data": updated_config, "status": "success", "message": "Delivery configuration updated successfully"}
        
    except TenantNotFoundError as e:
        logger.warning(f"Delivery config not found for update: {tenant_id}/{delivery_type}")
        raise HTTPException(status_code=404, detail=f"Delivery configuration '{tenant_id}/{delivery_type}' not found")
    except DynamoDBError as e:
        logger.error(f"DynamoDB error updating delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update delivery configuration")
    except ValidationError as e:
        logger.warning(f"Validation error updating delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        logger.error(f"Unexpected error updating delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update delivery configuration")


@app.patch("/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}")
async def patch_tenant_delivery_config(tenant_id: str, delivery_type: str, config_data: TenantDeliveryConfigPatchRequest):
    """Partially update a tenant delivery configuration (e.g., enable/disable)"""
    try:
        logger.info(f"Patching delivery config: {tenant_id}/{delivery_type}")
        
        # Convert pydantic model to dict, excluding None values
        patch_dict = config_data.model_dump(exclude_none=True)
        
        if not patch_dict:
            raise HTTPException(status_code=400, detail="No fields provided for patch")
        
        # Patch delivery config in DynamoDB
        patched_config = delivery_config_service.patch_tenant_config(tenant_id, delivery_type, patch_dict)
        
        return {"data": patched_config, "status": "success", "message": "Delivery configuration patched successfully"}
        
    except TenantNotFoundError as e:
        logger.warning(f"Delivery config not found for patch: {tenant_id}/{delivery_type}")
        raise HTTPException(status_code=404, detail=f"Delivery configuration '{tenant_id}/{delivery_type}' not found")
    except DynamoDBError as e:
        logger.error(f"DynamoDB error patching delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to patch delivery configuration")
    except ValidationError as e:
        logger.warning(f"Validation error patching delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        logger.error(f"Unexpected error patching delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to patch delivery configuration")


@app.delete("/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}")
async def delete_tenant_delivery_config(tenant_id: str, delivery_type: str):
    """Delete a tenant delivery configuration"""
    try:
        logger.info(f"Deleting delivery config: {tenant_id}/{delivery_type}")
        
        # Delete delivery config from DynamoDB
        delivery_config_service.delete_tenant_config(tenant_id, delivery_type)
        
        return {"status": "success", "message": f"Delivery configuration '{tenant_id}/{delivery_type}' deleted successfully"}
        
    except TenantNotFoundError as e:
        logger.warning(f"Delivery config not found for deletion: {tenant_id}/{delivery_type}")
        raise HTTPException(status_code=404, detail=f"Delivery configuration '{tenant_id}/{delivery_type}' not found")
    except DynamoDBError as e:
        logger.error(f"DynamoDB error deleting delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete delivery configuration")
    except Exception as e:
        logger.error(f"Unexpected error deleting delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete delivery configuration")


@app.get("/api/v1/tenants/{tenant_id}/delivery-configs/{delivery_type}/validate")
async def validate_tenant_delivery_config(tenant_id: str, delivery_type: str):
    """Validate a tenant delivery configuration"""
    try:
        logger.info(f"Validating delivery config: {tenant_id}/{delivery_type}")
        
        # Validate delivery configuration
        validation_result = delivery_config_service.validate_tenant_config(tenant_id, delivery_type)
        
        return {"data": validation_result, "status": "success"}
        
    except TenantNotFoundError as e:
        logger.warning(f"Delivery config not found for validation: {tenant_id}/{delivery_type}")
        raise HTTPException(status_code=404, detail=f"Delivery configuration '{tenant_id}/{delivery_type}' not found")
    except DynamoDBError as e:
        logger.error(f"DynamoDB error validating delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to validate delivery configuration")
    except Exception as e:
        logger.error(f"Unexpected error validating delivery config {tenant_id}/{delivery_type}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to validate delivery configuration")


# Lambda handler using Mangum
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    AWS Lambda handler using Mangum to adapt FastAPI to Lambda
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    # Set up Mangum adapter
    handler = Mangum(app, lifespan="off")
    
    try:
        logger.info(f"Processing request: {event.get('httpMethod', 'unknown')} {event.get('path', 'unknown')}")
        return handler(event, context)
    except Exception as e:
        logger.error(f"Unhandled error in Lambda handler: {str(e)}", exc_info=True)
        return error_response("Internal server error", status_code=500)


# For local testing with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)