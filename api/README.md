# Tenant Management API

REST API service for managing multi-tenant logging delivery configurations in DynamoDB.

## Overview

The Tenant Management API provides a secure, REST-based interface for managing tenant delivery configurations in the multi-tenant logging system. Each tenant can have multiple delivery configurations (CloudWatch Logs and S3) with independent settings and filtering. The API uses HMAC-SHA256 signature authentication with a pre-shared key (PSK) stored in AWS Secrets Manager.

## Architecture

- **API Gateway**: REST API with custom Lambda authorizer
- **Lambda Authorizer**: HMAC-SHA256 signature validation using PSK from Secrets Manager
- **API Service**: FastAPI-based Lambda function for CRUD operations
- **Authentication**: PSK-based request signing (no API keys required)
- **Storage**: DynamoDB with composite key structure (`tenant_id` + `type`)
- **Multi-Delivery Model**: Each tenant can have separate CloudWatch and S3 delivery configurations

## Data Model

### Composite Key Structure
- **Partition Key**: `tenant_id` (string)
- **Sort Key**: `type` (string: `"cloudwatch"` or `"s3"`)

### Delivery Configuration Types

#### CloudWatch Delivery Configuration
```json
{
  "tenant_id": "acme-corp",
  "type": "cloudwatch",
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp",
  "target_region": "us-east-1",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service"],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### S3 Delivery Configuration
```json
{
  "tenant_id": "acme-corp",
  "type": "s3",
  "bucket_name": "acme-corp-logs",
  "bucket_prefix": "ROSA/cluster-logs/",
  "target_region": "us-east-1",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service"],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

## Authentication

### HMAC-SHA256 Request Signing

All API endpoints (except `/health`) require HMAC-SHA256 signature authentication:

```
Authorization: HMAC-SHA256 <signature>
X-API-Timestamp: <ISO-8601-timestamp>
```

### Signature Generation

1. **Create message**: `HTTP_METHOD + URI + TIMESTAMP`
2. **Generate signature**: `HMAC-SHA256(PSK, message)`

**Note**: The signature does not include the request body hash due to API Gateway authorizer limitations. The body is validated by the API service after successful authentication.

### Example (Python)

```python
import hmac
import hashlib
from datetime import datetime, timezone

def sign_request(psk, method, uri):
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    message = f"{method.upper()}{uri}{timestamp}"
    signature = hmac.new(psk.encode(), message.encode(), hashlib.sha256).hexdigest()
    
    return {
        'Authorization': f'HMAC-SHA256 {signature}',
        'X-API-Timestamp': timestamp,
        'Content-Type': 'application/json'
    }

# Usage
headers = sign_request('your-psk', 'GET', '/api/v1/tenants/acme-corp/delivery-configs')
```

### Example (curl)

```bash
#!/bin/bash
PSK="your-pre-shared-key"
METHOD="GET"
URI="/api/v1/tenants/acme-corp/delivery-configs"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
MESSAGE="${METHOD}${URI}${TIMESTAMP}"
SIGNATURE=$(echo -n "$MESSAGE" | openssl dgst -sha256 -hmac "$PSK" | cut -d' ' -f2)

curl -X "$METHOD" "https://api.example.com${URI}" \
  -H "Authorization: HMAC-SHA256 $SIGNATURE" \
  -H "X-API-Timestamp: $TIMESTAMP" \
  -H "Content-Type: application/json"
```

### Example (Go)

```go
package main

import (
    "bytes"
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "time"
)

// CloudWatchDeliveryConfig represents a CloudWatch delivery configuration
type CloudWatchDeliveryConfig struct {
    TenantID               string   `json:"tenant_id"`
    Type                   string   `json:"type"`
    LogDistributionRoleArn string   `json:"log_distribution_role_arn"`
    LogGroupName           string   `json:"log_group_name"`
    TargetRegion           string   `json:"target_region,omitempty"`
    Enabled                *bool    `json:"enabled,omitempty"`
    DesiredLogs            []string `json:"desired_logs,omitempty"`
    TTL                    *int64   `json:"ttl,omitempty"`
    CreatedAt              string   `json:"created_at,omitempty"`
    UpdatedAt              string   `json:"updated_at,omitempty"`
}

// S3DeliveryConfig represents an S3 delivery configuration
type S3DeliveryConfig struct {
    TenantID     string   `json:"tenant_id"`
    Type         string   `json:"type"`
    BucketName   string   `json:"bucket_name"`
    BucketPrefix string   `json:"bucket_prefix,omitempty"`
    TargetRegion string   `json:"target_region,omitempty"`
    Enabled      *bool    `json:"enabled,omitempty"`
    DesiredLogs  []string `json:"desired_logs,omitempty"`
    TTL          *int64   `json:"ttl,omitempty"`
    CreatedAt    string   `json:"created_at,omitempty"`
    UpdatedAt    string   `json:"updated_at,omitempty"`
}

// DeliveryConfigCreateRequest represents a request to create a delivery configuration
type DeliveryConfigCreateRequest struct {
    TenantID     string   `json:"tenant_id"`
    Type         string   `json:"type"` // "cloudwatch" or "s3"
    Enabled      *bool    `json:"enabled,omitempty"`
    DesiredLogs  []string `json:"desired_logs,omitempty"`
    TargetRegion string   `json:"target_region,omitempty"`
    TTL          *int64   `json:"ttl,omitempty"`
    
    // CloudWatch-specific fields
    LogDistributionRoleArn string `json:"log_distribution_role_arn,omitempty"`
    LogGroupName           string `json:"log_group_name,omitempty"`
    
    // S3-specific fields
    BucketName   string `json:"bucket_name,omitempty"`
    BucketPrefix string `json:"bucket_prefix,omitempty"`
}

// APIResponse represents the standard API response format
type APIResponse struct {
    Timestamp string      `json:"timestamp"`
    Status    string      `json:"status"`
    Data      interface{} `json:"data,omitempty"`
    Message   string      `json:"message,omitempty"`
    Error     string      `json:"error,omitempty"`
    Details   interface{} `json:"details,omitempty"`
}

// TenantClient handles authenticated requests to the tenant management API
type TenantClient struct {
    BaseURL    string
    PSK        string
    HTTPClient *http.Client
}

// NewTenantClient creates a new tenant management API client
func NewTenantClient(baseURL, psk string) *TenantClient {
    return &TenantClient{
        BaseURL: baseURL,
        PSK:     psk,
        HTTPClient: &http.Client{
            Timeout: 30 * time.Second,
        },
    }
}

// generateSignature creates HMAC-SHA256 signature for request authentication
func (c *TenantClient) generateSignature(method, uri, timestamp string) string {
    message := method + uri + timestamp
    h := hmac.New(sha256.New, []byte(c.PSK))
    h.Write([]byte(message))
    signature := hex.EncodeToString(h.Sum(nil))
    return signature
}

// signRequest adds authentication headers to the request
func (c *TenantClient) signRequest(req *http.Request, body string) {
    timestamp := time.Now().UTC().Format("2006-01-02T15:04:05Z")
    signature := c.generateSignature(req.Method, req.URL.RequestURI(), timestamp)
    
    req.Header.Set("Authorization", "HMAC-SHA256 "+signature)
    req.Header.Set("X-API-Timestamp", timestamp)
    req.Header.Set("Content-Type", "application/json")
}

// doRequest performs an authenticated HTTP request
func (c *TenantClient) doRequest(method, path, body string) (*APIResponse, error) {
    url := c.BaseURL + path
    
    req, err := http.NewRequest(method, url, bytes.NewBufferString(body))
    if err != nil {
        return nil, fmt.Errorf("failed to create request: %w", err)
    }
    
    // Add authentication headers (skip for health endpoint)
    if path != "/health" {
        c.signRequest(req, body)
    }
    
    resp, err := c.HTTPClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("request failed: %w", err)
    }
    defer resp.Body.Close()
    
    respBody, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, fmt.Errorf("failed to read response: %w", err)
    }
    
    var apiResp APIResponse
    if err := json.Unmarshal(respBody, &apiResp); err != nil {
        return nil, fmt.Errorf("failed to parse response: %w", err)
    }
    
    if resp.StatusCode >= 400 {
        return &apiResp, fmt.Errorf("API error (status %d): %s", resp.StatusCode, apiResp.Error)
    }
    
    return &apiResp, nil
}

// Health checks the API health status (no authentication required)
func (c *TenantClient) Health() (*APIResponse, error) {
    return c.doRequest("GET", "/health", "")
}

// ListAllDeliveryConfigs retrieves a paginated list of all delivery configurations
func (c *TenantClient) ListAllDeliveryConfigs(limit int, lastKey string) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/delivery-configs?limit=%d", limit)
    if lastKey != "" {
        path += "&last_key=" + lastKey
    }
    return c.doRequest("GET", path, "")
}

// ListTenantDeliveryConfigs retrieves all delivery configurations for a specific tenant
func (c *TenantClient) ListTenantDeliveryConfigs(tenantID string) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs", tenantID)
    return c.doRequest("GET", path, "")
}

// GetDeliveryConfig retrieves a specific delivery configuration
func (c *TenantClient) GetDeliveryConfig(tenantID, deliveryType string) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s", tenantID, deliveryType)
    return c.doRequest("GET", path, "")
}

// CreateDeliveryConfig creates a new delivery configuration
func (c *TenantClient) CreateDeliveryConfig(config DeliveryConfigCreateRequest) (*APIResponse, error) {
    body, err := json.Marshal(config)
    if err != nil {
        return nil, fmt.Errorf("failed to marshal config: %w", err)
    }
    path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs", config.TenantID)
    return c.doRequest("POST", path, string(body))
}

// UpdateDeliveryConfig updates an existing delivery configuration
func (c *TenantClient) UpdateDeliveryConfig(tenantID, deliveryType string, config DeliveryConfigCreateRequest) (*APIResponse, error) {
    body, err := json.Marshal(config)
    if err != nil {
        return nil, fmt.Errorf("failed to marshal config: %w", err)
    }
    path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s", tenantID, deliveryType)
    return c.doRequest("PUT", path, string(body))
}

// PatchDeliveryConfig performs a partial update (e.g., enable/disable)
func (c *TenantClient) PatchDeliveryConfig(tenantID, deliveryType string, updates map[string]interface{}) (*APIResponse, error) {
    body, err := json.Marshal(updates)
    if err != nil {
        return nil, fmt.Errorf("failed to marshal updates: %w", err)
    }
    path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s", tenantID, deliveryType)
    return c.doRequest("PATCH", path, string(body))
}

// DeleteDeliveryConfig removes a delivery configuration
func (c *TenantClient) DeleteDeliveryConfig(tenantID, deliveryType string) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s", tenantID, deliveryType)
    return c.doRequest("DELETE", path, "")
}

// ValidateDeliveryConfig validates delivery configuration and IAM permissions
func (c *TenantClient) ValidateDeliveryConfig(tenantID, deliveryType string) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s/validate", tenantID, deliveryType)
    return c.doRequest("GET", path, "")
}

// Example usage
func main() {
    // Initialize client
    client := NewTenantClient(
        "https://abc123.execute-api.us-east-1.amazonaws.com/development",
        "your-pre-shared-key-here",
    )
    
    // Health check (no authentication)
    if health, err := client.Health(); err != nil {
        fmt.Printf("Health check failed: %v\n", err)
    } else {
        fmt.Printf("Health: %s\n", health.Status)
    }
    
    // Create CloudWatch delivery configuration
    enabled := true
    cloudwatchConfig := DeliveryConfigCreateRequest{
        TenantID:               "example-corp",
        Type:                   "cloudwatch",
        LogDistributionRoleArn: "arn:aws:iam::123456789012:role/LogDistributionRole",
        LogGroupName:           "/aws/logs/example-corp",
        TargetRegion:           "us-east-1",
        Enabled:                &enabled,
        DesiredLogs:            []string{"api-service", "payment-service"},
    }
    
    if resp, err := client.CreateDeliveryConfig(cloudwatchConfig); err != nil {
        fmt.Printf("Create CloudWatch config failed: %v\n", err)
    } else {
        fmt.Printf("Created CloudWatch config: %s\n", resp.Message)
    }
    
    // Create S3 delivery configuration
    s3Config := DeliveryConfigCreateRequest{
        TenantID:     "example-corp",
        Type:         "s3",
        BucketName:   "example-corp-logs",
        BucketPrefix: "ROSA/cluster-logs/",
        TargetRegion: "us-east-1",
        Enabled:      &enabled,
        DesiredLogs:  []string{"api-service", "payment-service"},
    }
    
    if resp, err := client.CreateDeliveryConfig(s3Config); err != nil {
        fmt.Printf("Create S3 config failed: %v\n", err)
    } else {
        fmt.Printf("Created S3 config: %s\n", resp.Message)
    }
    
    // Get specific delivery configuration
    if resp, err := client.GetDeliveryConfig("example-corp", "cloudwatch"); err != nil {
        fmt.Printf("Get CloudWatch config failed: %v\n", err)
    } else {
        configData, _ := json.MarshalIndent(resp.Data, "", "  ")
        fmt.Printf("CloudWatch config:\n%s\n", configData)
    }
    
    // List all delivery configurations for a tenant
    if resp, err := client.ListTenantDeliveryConfigs("example-corp"); err != nil {
        fmt.Printf("List tenant configs failed: %v\n", err)
    } else {
        fmt.Printf("Tenant has %d delivery configurations\n", len(resp.Data.(map[string]interface{})["configurations"].([]interface{})))
    }
    
    // Disable CloudWatch delivery
    updates := map[string]interface{}{
        "enabled": false,
    }
    if resp, err := client.PatchDeliveryConfig("example-corp", "cloudwatch", updates); err != nil {
        fmt.Printf("Patch CloudWatch config failed: %v\n", err)
    } else {
        fmt.Printf("CloudWatch config updated: %s\n", resp.Message)
    }
    
    // List all delivery configurations across all tenants
    if resp, err := client.ListAllDeliveryConfigs(50, ""); err != nil {
        fmt.Printf("List all configs failed: %v\n", err)
    } else {
        fmt.Printf("Total configurations retrieved: %d\n", len(resp.Data.(map[string]interface{})["configurations"].([]interface{})))
    }
    
    // Validate delivery configuration
    if resp, err := client.ValidateDeliveryConfig("example-corp", "cloudwatch"); err != nil {
        fmt.Printf("Validate config failed: %v\n", err)
    } else {
        fmt.Printf("Validation result: %s\n", resp.Status)
    }
}
```

#### Go Module Setup

```bash
# Initialize Go module
go mod init tenant-management-client

# Create main.go with the client code above
# No external dependencies required - uses standard library only

# Run the example
go run main.go
```

#### Go Client Features

- **Zero Dependencies**: Uses only Go standard library
- **Proper Authentication**: Implements HMAC-SHA256 signature generation
- **Type Safety**: Strongly typed structs for delivery configurations
- **Multi-Delivery Support**: Handles both CloudWatch and S3 configurations
- **Error Handling**: Comprehensive error handling with detailed messages
- **Timeout Support**: Built-in HTTP client timeouts
- **Flexible Updates**: Support for both full updates (PUT) and partial updates (PATCH)
- **Easy Integration**: Simple interface for all CRUD operations

## API Endpoints

### Base URL
```
https://{api-gateway-id}.execute-api.{region}.amazonaws.com/{stage}/api/v1
```

### Health Check
```http
GET /health
```
- **Authentication**: None required
- **Description**: Service health status

### List All Delivery Configurations
```http
GET /delivery-configs?limit=50&last_key=tenant-id%23type
```
- **Authentication**: Required
- **Parameters**: 
  - `limit` (default: 50): Maximum number of configurations to return
  - `last_key` (optional): Pagination key in format `tenant_id#type`
- **Response**: Paginated list of all delivery configurations across all tenants

### List Tenant Delivery Configurations
```http
GET /tenants/{tenant_id}/delivery-configs
```
- **Authentication**: Required
- **Description**: Retrieve all delivery configurations for a specific tenant

### Get Specific Delivery Configuration
```http
GET /tenants/{tenant_id}/delivery-configs/{delivery_type}
```
- **Authentication**: Required
- **Parameters**: 
  - `tenant_id`: Unique tenant identifier
  - `delivery_type`: `"cloudwatch"` or `"s3"`
- **Description**: Retrieve specific delivery configuration

### Create Delivery Configuration
```http
POST /tenants/{tenant_id}/delivery-configs
Content-Type: application/json

# CloudWatch Configuration
{
  "tenant_id": "acme-corp",
  "type": "cloudwatch",
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp",
  "target_region": "us-east-1",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service"],
}

# S3 Configuration
{
  "tenant_id": "acme-corp",
  "type": "s3",
  "bucket_name": "acme-corp-logs",
  "bucket_prefix": "ROSA/cluster-logs/",
  "target_region": "us-east-1",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service"],
}
```

### Update Delivery Configuration
```http
PUT /tenants/{tenant_id}/delivery-configs/{delivery_type}
Content-Type: application/json

{
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/UpdatedLogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp-updated",
  "target_region": "us-west-2",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service", "api-gateway"],
}
```

### Partial Update (Enable/Disable)
```http
PATCH /tenants/{tenant_id}/delivery-configs/{delivery_type}
Content-Type: application/json

{
  "enabled": false
}
```

### Delete Delivery Configuration
```http
DELETE /tenants/{tenant_id}/delivery-configs/{delivery_type}
```

### Validate Delivery Configuration
```http
GET /tenants/{tenant_id}/delivery-configs/{delivery_type}/validate
```
- **Authentication**: Required
- **Description**: Validate delivery configuration and IAM permissions

## Delivery Configuration Schema

### Common Fields (All Types)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | String | Yes | Unique tenant identifier |
| `type` | String | Yes | Delivery type: `"cloudwatch"` or `"s3"` |
| `enabled` | Boolean | No | Enable/disable processing (default: true) |
| `desired_logs` | Array | No | Application filter list (default: all) |
| `target_region` | String | No | AWS region for delivery (default: processor region) |
| `ttl` | Integer | No | Unix timestamp for DynamoDB TTL expiration |
| `created_at` | String | No | Configuration creation timestamp (ISO 8601) |
| `updated_at` | String | No | Configuration last update timestamp (ISO 8601) |


### CloudWatch-Specific Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `log_distribution_role_arn` | String | Yes | Customer IAM role ARN |
| `log_group_name` | String | Yes | CloudWatch Logs group name |

### S3-Specific Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bucket_name` | String | Yes | Target S3 bucket name |
| `bucket_prefix` | String | No | S3 object prefix (default: "ROSA/cluster-logs/") |

## Response Format

### Success Response
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "status": "success",
  "data": { ... },
  "message": "Operation completed successfully"
}
```

### Error Response
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "status": "error",
  "error": "Error message",
  "details": { ... }
}
```

### List Response
```json
{
  "data": {
    "configurations": [
      {
        "tenant_id": "acme-corp",
        "type": "cloudwatch",
        "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
        "log_group_name": "/aws/logs/acme-corp",
        "enabled": true,
        "created_at": "2024-01-15T10:30:00Z"
      }
    ],
    "count": 1,
    "limit": 50,
    "last_key": "acme-corp#cloudwatch"
  },
  "status": "success"
}
```

## Local Development

### Prerequisites
- Python 3.13+
- AWS CLI configured
- Docker/Podman for container testing

### Setup
```bash
cd api/
pip install -r requirements.txt
```

### Run Locally
```bash
# Direct Python execution
python -m src.app

# Or with uvicorn
cd src/
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### Environment Variables
```bash
export TENANT_CONFIG_TABLE="multi-tenant-logging-development-tenant-configs"
export AWS_REGION="us-east-1"
export LOG_LEVEL="INFO"
export PSK_SECRET_NAME="logging/api/psk"  # For authorizer only
```

## Container Development

### Build Containers
```bash
# Build authorizer container
podman build -f Containerfile.authorizer -t logging-authorizer:latest .

# Build API service container
podman build -f Containerfile.api -t logging-api:latest .
```

### Test Containers Locally
```bash
# Test authorizer
podman run --rm -e PSK_SECRET_NAME="test/psk" logging-authorizer:latest

# Test API service
podman run --rm -p 8080:8080 \
  -e TENANT_CONFIG_TABLE="test-table" \
  -e AWS_REGION="us-east-1" \
  logging-api:latest
```

### Push to ECR
```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  podman login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
podman tag logging-authorizer:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/logging-authorizer:latest
podman push 123456789012.dkr.ecr.us-east-1.amazonaws.com/logging-authorizer:latest

podman tag logging-api:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/logging-api:latest
podman push 123456789012.dkr.ecr.us-east-1.amazonaws.com/logging-api:latest
```

## Deployment

### Prerequisites
1. **Create Secrets Manager Secret**:
   ```bash
   aws secretsmanager create-secret \
     --name "logging/api/psk" \
     --secret-string "your-256-bit-base64-encoded-key" \
     --description "PSK for tenant management API authentication"
   ```

2. **Build and Push Containers** (see above)

### Deploy with CloudFormation
```bash
cd cloudformation/
./deploy.sh -t regional -b your-templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abc123 \
  --include-api \
  --api-auth-secret-name "logging/api/psk" \
  --authorizer-image-uri 123456789012.dkr.ecr.us-east-1.amazonaws.com/logging-authorizer:latest \
  --api-image-uri 123456789012.dkr.ecr.us-east-1.amazonaws.com/logging-api:latest
```

### Get API Endpoint
```bash
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-development \
  --query 'Stacks[0].Outputs[?OutputKey==`APIEndpoint`].OutputValue' \
  --output text
```

## Usage Examples

### Managing Multiple Delivery Types

```bash
# Create CloudWatch delivery configuration
curl -X POST "https://api.example.com/api/v1/tenants/acme-corp/delivery-configs" \
  -H "Authorization: HMAC-SHA256 $SIGNATURE" \
  -H "X-API-Timestamp: $TIMESTAMP" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "acme-corp",
    "type": "cloudwatch",
    "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
    "log_group_name": "/aws/logs/acme-corp",
    "target_region": "us-east-1",
    "enabled": true,
    "desired_logs": ["payment-service", "user-service"],
  }'

# Create S3 delivery configuration for the same tenant
curl -X POST "https://api.example.com/api/v1/tenants/acme-corp/delivery-configs" \
  -H "Authorization: HMAC-SHA256 $SIGNATURE" \
  -H "X-API-Timestamp: $TIMESTAMP" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "acme-corp", 
    "type": "s3",
    "bucket_name": "acme-corp-logs",
    "bucket_prefix": "ROSA/cluster-logs/",
    "target_region": "us-east-1",
    "enabled": true,
    "desired_logs": ["payment-service", "user-service"],
  }'

# List all configurations for a tenant
curl -X GET "https://api.example.com/api/v1/tenants/acme-corp/delivery-configs" \
  -H "Authorization: HMAC-SHA256 $SIGNATURE" \
  -H "X-API-Timestamp: $TIMESTAMP"

# Get specific configuration
curl -X GET "https://api.example.com/api/v1/tenants/acme-corp/delivery-configs/cloudwatch" \
  -H "Authorization: HMAC-SHA256 $SIGNATURE" \
  -H "X-API-Timestamp: $TIMESTAMP"

# Disable S3 delivery while keeping CloudWatch enabled
curl -X PATCH "https://api.example.com/api/v1/tenants/acme-corp/delivery-configs/s3" \
  -H "Authorization: HMAC-SHA256 $SIGNATURE" \
  -H "X-API-Timestamp: $TIMESTAMP" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

## Security Considerations

1. **PSK Management**: Store PSK in AWS Secrets Manager with automatic encryption
2. **Timestamp Validation**: Requests older than 5 minutes are rejected
3. **Signature Validation**: Constant-time comparison prevents timing attacks
4. **Least Privilege**: IAM roles have minimal required permissions
5. **Request Validation**: Input validation on all endpoints
6. **CORS**: Configured for specific origins in production
7. **Multi-Delivery Isolation**: Each delivery type can be managed independently

## Monitoring

### CloudWatch Logs
- **API Gateway Logs**: `/aws/apigateway/multi-tenant-logging-{env}-tenant-api`
- **Authorizer Logs**: `/aws/lambda/multi-tenant-logging-{env}-api-authorizer`
- **API Service Logs**: `/aws/lambda/multi-tenant-logging-{env}-api-service`

### Metrics
- API Gateway request/response metrics
- Lambda execution duration and errors
- DynamoDB read/write metrics
- Delivery configuration creation/update rates

### Alarms
- High error rates
- Lambda timeout errors
- DynamoDB throttling
- Authentication failures

## Troubleshooting

### Authentication Failures
1. Verify PSK in AWS Secrets Manager
2. Check timestamp format (ISO 8601 with Z suffix)
3. Ensure signature calculation matches specification
4. Verify request path and method case sensitivity

### API Errors
1. Check CloudWatch logs for detailed error messages
2. Verify DynamoDB table permissions
3. Check IAM role trust policies
4. Validate request body format and required fields

### Delivery Configuration Issues
1. Verify delivery type (`"cloudwatch"` or `"s3"`)
2. Check type-specific required fields
3. Validate IAM role ARNs and S3 bucket names
4. Ensure target regions are valid

### Container Issues
1. Verify ECR image URIs in CloudFormation
2. Check Lambda function environment variables
3. Ensure container health checks pass
4. Review Lambda execution role permissions

## Migration from v1 API

### Key Changes
- **Composite Key**: Now uses `tenant_id` + `type` instead of single `tenant_id`
- **Multiple Configurations**: Each tenant can have multiple delivery types
- **New Endpoints**: Delivery-type-specific endpoints for management
- **Enhanced Validation**: Type-specific field validation

### Migration Steps
1. **List existing tenant configurations** using old API
2. **Create new CloudWatch configurations** for each tenant
3. **Create new S3 configurations** if needed
4. **Update client applications** to use new endpoints
5. **Test delivery configurations** independently
6. **Decommission old API** after validation

## Development Roadmap

### Phase 1 (Current)
- [x] Multi-delivery configuration model
- [x] CloudWatch and S3 delivery types
- [x] HMAC-SHA256 authentication
- [x] Composite key DynamoDB structure
- [x] Type-specific validation

### Phase 2 (Planned)
- [ ] Tenant validation endpoint implementation
- [ ] Bulk operations (create/update multiple configurations)
- [ ] Enhanced error handling and validation
- [ ] API usage metrics and monitoring
- [ ] Configuration history tracking

### Phase 3 (Future)
- [ ] OpenAPI documentation generation
- [ ] Client SDK generation
- [ ] Webhook notifications for configuration changes
- [ ] Advanced filtering and search capabilities
- [ ] Configuration templates and inheritance