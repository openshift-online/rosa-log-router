"""
Main API handler for the tenant management service
"""

import json
import logging
import os
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

# Import our utilities
from src.models.responses import success_response, error_response, not_found_response
from src.utils.logger import setup_logging

# Set up logging
logger = setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Tenant Management API",
    description="REST API for managing multi-tenant logging configuration",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
TENANT_CONFIG_TABLE = os.environ.get('TENANT_CONFIG_TABLE', 'tenant-configurations')
AWS_REGION = os.environ.get('AWS_REGION')

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint - no authentication required"""
    try:
        from src.handlers.health import get_health_status
        return get_health_status()
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/api/v1/tenants")
async def list_tenants(limit: int = 50, offset: int = 0):
    """List all tenants with pagination"""
    try:
        # TODO: Implement tenant listing from DynamoDB
        logger.info(f"Listing tenants with limit={limit}, offset={offset}")
        
        # Placeholder response
        return {
            "tenants": [],
            "total": 0,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Failed to list tenants: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list tenants")


@app.get("/api/v1/tenants/{tenant_id}")
async def get_tenant(tenant_id: str):
    """Get a specific tenant configuration"""
    try:
        # TODO: Implement tenant retrieval from DynamoDB
        logger.info(f"Getting tenant: {tenant_id}")
        
        # Placeholder response
        return {
            "tenant_id": tenant_id,
            "message": "Tenant retrieval not yet implemented"
        }
    except Exception as e:
        logger.error(f"Failed to get tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get tenant")


@app.post("/api/v1/tenants")
async def create_tenant(request: Request):
    """Create a new tenant"""
    try:
        body = await request.json()
        logger.info(f"Creating tenant with data: {body}")
        
        # TODO: Implement tenant creation in DynamoDB
        # TODO: Add validation using pydantic models
        
        # Placeholder response
        return {"message": "Tenant creation not yet implemented"}
    except Exception as e:
        logger.error(f"Failed to create tenant: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create tenant")


@app.put("/api/v1/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, request: Request):
    """Update a tenant configuration"""
    try:
        body = await request.json()
        logger.info(f"Updating tenant {tenant_id} with data: {body}")
        
        # TODO: Implement tenant update in DynamoDB
        # TODO: Add validation using pydantic models
        
        # Placeholder response
        return {"message": f"Tenant {tenant_id} update not yet implemented"}
    except Exception as e:
        logger.error(f"Failed to update tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update tenant")


@app.patch("/api/v1/tenants/{tenant_id}")
async def patch_tenant(tenant_id: str, request: Request):
    """Partially update a tenant (e.g., enable/disable)"""
    try:
        body = await request.json()
        logger.info(f"Patching tenant {tenant_id} with data: {body}")
        
        # TODO: Implement partial tenant update in DynamoDB
        # TODO: Add validation for partial updates
        
        # Placeholder response
        return {"message": f"Tenant {tenant_id} patch not yet implemented"}
    except Exception as e:
        logger.error(f"Failed to patch tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to patch tenant")


@app.delete("/api/v1/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str):
    """Delete a tenant configuration"""
    try:
        logger.info(f"Deleting tenant: {tenant_id}")
        
        # TODO: Implement tenant deletion from DynamoDB
        # TODO: Add confirmation/safety checks
        
        # Placeholder response
        return {"message": f"Tenant {tenant_id} deletion not yet implemented"}
    except Exception as e:
        logger.error(f"Failed to delete tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete tenant")


@app.get("/api/v1/tenants/{tenant_id}/validate")
async def validate_tenant(tenant_id: str):
    """Validate a tenant configuration"""
    try:
        logger.info(f"Validating tenant: {tenant_id}")
        
        # TODO: Implement tenant configuration validation
        # TODO: Check role ARNs, regions, permissions
        
        # Placeholder response
        return {
            "tenant_id": tenant_id,
            "valid": True,
            "checks": []
        }
    except Exception as e:
        logger.error(f"Failed to validate tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to validate tenant")


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