# Tenant Management API

REST API service for managing multi-tenant logging configuration in DynamoDB.

## Overview

The Tenant Management API provides a secure, REST-based interface for managing tenant configurations in the multi-tenant logging system. It uses HMAC-SHA256 signature authentication with a pre-shared key (PSK) stored in AWS SSM Parameter Store.

## Architecture

- **API Gateway**: REST API with custom Lambda authorizer
- **Lambda Authorizer**: HMAC-SHA256 signature validation using PSK from SSM
- **API Service**: FastAPI-based Lambda function for CRUD operations
- **Authentication**: PSK-based request signing (no API keys required)
- **Storage**: DynamoDB for tenant configuration data

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
headers = sign_request('your-psk', 'GET', '/api/v1/tenants')
```

### Example (curl)

```bash
#!/bin/bash
PSK="your-pre-shared-key"
METHOD="GET"
URI="/api/v1/tenants"
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

// TenantConfig represents a tenant configuration
type TenantConfig struct {
    TenantID               string   `json:"tenant_id"`
    LogDistributionRoleArn string   `json:"log_distribution_role_arn"`
    LogGroupName           string   `json:"log_group_name"`
    TargetRegion           string   `json:"target_region"`
    Enabled                *bool    `json:"enabled,omitempty"`
    DesiredLogs            []string `json:"desired_logs,omitempty"`
    AccountID              string   `json:"account_id,omitempty"`
    Status                 string   `json:"status,omitempty"`
    CreatedAt              string   `json:"created_at,omitempty"`
    UpdatedAt              string   `json:"updated_at,omitempty"`
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
    // Create message: METHOD + URI + TIMESTAMP
    message := method + uri + timestamp
    
    // Generate HMAC-SHA256 signature
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

// ListTenants retrieves a paginated list of tenant configurations
func (c *TenantClient) ListTenants(limit, offset int) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/tenants?limit=%d&offset=%d", limit, offset)
    return c.doRequest("GET", path, "")
}

// GetTenant retrieves a specific tenant configuration
func (c *TenantClient) GetTenant(tenantID string) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/tenants/%s", tenantID)
    return c.doRequest("GET", path, "")
}

// CreateTenant creates a new tenant configuration
func (c *TenantClient) CreateTenant(tenant TenantConfig) (*APIResponse, error) {
    body, err := json.Marshal(tenant)
    if err != nil {
        return nil, fmt.Errorf("failed to marshal tenant: %w", err)
    }
    return c.doRequest("POST", "/api/v1/tenants", string(body))
}

// UpdateTenant updates an existing tenant configuration
func (c *TenantClient) UpdateTenant(tenantID string, tenant TenantConfig) (*APIResponse, error) {
    body, err := json.Marshal(tenant)
    if err != nil {
        return nil, fmt.Errorf("failed to marshal tenant: %w", err)
    }
    path := fmt.Sprintf("/api/v1/tenants/%s", tenantID)
    return c.doRequest("PUT", path, string(body))
}

// PatchTenant performs a partial update (e.g., enable/disable)
func (c *TenantClient) PatchTenant(tenantID string, updates map[string]interface{}) (*APIResponse, error) {
    body, err := json.Marshal(updates)
    if err != nil {
        return nil, fmt.Errorf("failed to marshal updates: %w", err)
    }
    path := fmt.Sprintf("/api/v1/tenants/%s", tenantID)
    return c.doRequest("PATCH", path, string(body))
}

// DeleteTenant removes a tenant configuration
func (c *TenantClient) DeleteTenant(tenantID string) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/tenants/%s", tenantID)
    return c.doRequest("DELETE", path, "")
}

// ValidateTenant validates tenant configuration and IAM permissions
func (c *TenantClient) ValidateTenant(tenantID string) (*APIResponse, error) {
    path := fmt.Sprintf("/api/v1/tenants/%s/validate", tenantID)
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
    
    // Create a new tenant
    enabled := true
    newTenant := TenantConfig{
        TenantID:               "example-corp",
        LogDistributionRoleArn: "arn:aws:iam::123456789012:role/LogDistributionRole",
        LogGroupName:           "/aws/logs/example-corp",
        TargetRegion:           "us-east-1",
        Enabled:                &enabled,
        DesiredLogs:            []string{"api-service", "payment-service"},
    }
    
    if resp, err := client.CreateTenant(newTenant); err != nil {
        fmt.Printf("Create tenant failed: %v\n", err)
    } else {
        fmt.Printf("Created tenant: %s\n", resp.Message)
    }
    
    // Get tenant details
    if resp, err := client.GetTenant("example-corp"); err != nil {
        fmt.Printf("Get tenant failed: %v\n", err)
    } else {
        tenantData, _ := json.MarshalIndent(resp.Data, "", "  ")
        fmt.Printf("Tenant details:\n%s\n", tenantData)
    }
    
    // Disable tenant
    updates := map[string]interface{}{
        "enabled": false,
    }
    if resp, err := client.PatchTenant("example-corp", updates); err != nil {
        fmt.Printf("Patch tenant failed: %v\n", err)
    } else {
        fmt.Printf("Tenant updated: %s\n", resp.Message)
    }
    
    // List all tenants
    if resp, err := client.ListTenants(50, 0); err != nil {
        fmt.Printf("List tenants failed: %v\n", err)
    } else {
        fmt.Printf("Total tenants retrieved: %d\n", len(resp.Data.([]interface{})))
    }
    
    // Validate tenant configuration
    if resp, err := client.ValidateTenant("example-corp"); err != nil {
        fmt.Printf("Validate tenant failed: %v\n", err)
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
- **Type Safety**: Strongly typed structs for tenant configurations
- **Error Handling**: Comprehensive error handling with detailed messages
- **Timeout Support**: Built-in HTTP client timeouts
- **Flexible Updates**: Support for both full updates (PUT) and partial updates (PATCH)
- **Easy Integration**: Simple interface for all CRUD operations
```

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

### List Tenants
```http
GET /tenants?limit=50&offset=0
```
- **Authentication**: Required
- **Parameters**: `limit` (default: 50), `offset` (default: 0)
- **Response**: Paginated list of tenant configurations

### Get Tenant
```http
GET /tenants/{tenant_id}
```
- **Authentication**: Required
- **Description**: Retrieve specific tenant configuration

### Create Tenant
```http
POST /tenants
Content-Type: application/json

{
  "tenant_id": "acme-corp",
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp",
  "target_region": "us-east-1",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service"]
}
```

### Update Tenant
```http
PUT /tenants/{tenant_id}
Content-Type: application/json

{
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp",
  "target_region": "us-east-1",
  "enabled": true,
  "desired_logs": ["payment-service", "user-service", "api-gateway"]
}
```

### Partial Update (Enable/Disable)
```http
PATCH /tenants/{tenant_id}
Content-Type: application/json

{
  "enabled": false
}
```

### Delete Tenant
```http
DELETE /tenants/{tenant_id}
```

### Validate Tenant Configuration
```http
GET /tenants/{tenant_id}/validate
```
- **Authentication**: Required
- **Description**: Validate tenant configuration and IAM permissions

## Tenant Configuration Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | String | Yes | Unique tenant identifier |
| `log_distribution_role_arn` | String | Yes | Customer IAM role ARN |
| `log_group_name` | String | Yes | CloudWatch Logs group name |
| `target_region` | String | Yes | AWS region for log delivery |
| `enabled` | Boolean | No | Enable/disable processing (default: true) |
| `desired_logs` | Array | No | Application filter list (default: all) |
| `account_id` | String | No | Customer AWS account ID |
| `status` | String | No | Tenant status |

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
export PSK_PARAMETER_NAME="/logging/api/psk"  # For authorizer only
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
podman run --rm -e PSK_PARAMETER_NAME="/test/psk" logging-authorizer:latest

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
1. **Create SSM Parameter**:
   ```bash
   aws ssm put-parameter \
     --name "/logging/api/psk" \
     --value "your-256-bit-base64-encoded-key" \
     --type "SecureString" \
     --description "PSK for tenant management API authentication"
   ```

2. **Build and Push Containers** (see above)

### Deploy with CloudFormation
```bash
cd cloudformation/
./deploy.sh -t regional -b your-templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abc123 \
  --include-api \
  --api-auth-ssm-parameter "/logging/api/psk" \
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

## Security Considerations

1. **PSK Management**: Store PSK in SSM Parameter Store as SecureString
2. **Timestamp Validation**: Requests older than 5 minutes are rejected
3. **Signature Validation**: Constant-time comparison prevents timing attacks
4. **Least Privilege**: IAM roles have minimal required permissions
5. **Request Validation**: Input validation on all endpoints
6. **CORS**: Configured for specific origins in production

## Monitoring

### CloudWatch Logs
- **API Gateway Logs**: `/aws/apigateway/multi-tenant-logging-{env}-tenant-api`
- **Authorizer Logs**: `/aws/lambda/multi-tenant-logging-{env}-api-authorizer`
- **API Service Logs**: `/aws/lambda/multi-tenant-logging-{env}-api-service`

### Metrics
- API Gateway request/response metrics
- Lambda execution duration and errors
- DynamoDB read/write metrics

### Alarms
- High error rates
- Lambda timeout errors
- DynamoDB throttling

## Troubleshooting

### Authentication Failures
1. Verify PSK in SSM Parameter Store
2. Check timestamp format (ISO 8601 with Z suffix)
3. Ensure signature calculation matches specification
4. Verify request path and method case sensitivity

### API Errors
1. Check CloudWatch logs for detailed error messages
2. Verify DynamoDB table permissions
3. Check IAM role trust policies
4. Validate request body format

### Container Issues
1. Verify ECR image URIs in CloudFormation
2. Check Lambda function environment variables
3. Ensure container health checks pass
4. Review Lambda execution role permissions

## Development Roadmap

### Phase 1 (Current)
- [x] Basic CRUD operations
- [x] HMAC-SHA256 authentication
- [x] CloudFormation integration
- [x] Health check endpoint

### Phase 2 (Planned)
- [ ] Tenant validation endpoint implementation
- [ ] Bulk operations (create/update multiple tenants)
- [ ] Enhanced error handling and validation
- [ ] API usage metrics and monitoring

### Phase 3 (Future)
- [ ] OpenAPI documentation generation
- [ ] Client SDK generation
- [ ] Webhook notifications for tenant changes
- [ ] Advanced filtering and search capabilities