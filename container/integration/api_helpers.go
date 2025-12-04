//go:build integration
// +build integration

package integration

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// generateHMACSignature generates HMAC-SHA256 signature for API authentication
// Signature format matches the authorizer: METHODURITIMESTAMP (no separators, no body)
func generateHMACSignature(psk, method, path, timestamp string) string {
	// Signature format: HMAC-SHA256(PSK, "METHODURITIMESTAMP")
	message := fmt.Sprintf("%s%s%s", method, path, timestamp)
	h := hmac.New(sha256.New, []byte(psk))
	h.Write([]byte(message))
	return hex.EncodeToString(h.Sum(nil))
}

// makeAPIRequest makes an authenticated HTTP request to the API
func (h *E2ETestHelper) makeAPIRequest(t *testing.T, method, path string, body interface{}) (*http.Response, error) {
	t.Helper()

	endpoint := h.APIGatewayEndpoint()
	url := endpoint + path

	var bodyBytes []byte
	var err error
	if body != nil {
		bodyBytes, err = json.Marshal(body)
		require.NoError(t, err, "failed to marshal request body")
	}

	req, err := http.NewRequest(method, url, bytes.NewReader(bodyBytes))
	require.NoError(t, err, "failed to create HTTP request")

	// Add HMAC authentication headers
	// Use ISO 8601 timestamp format as expected by authorizer
	timestamp := time.Now().UTC().Format(time.RFC3339)

	signature := generateHMACSignature(h.APIPSK(), method, path, timestamp)

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-API-Timestamp", timestamp)
	req.Header.Set("Authorization", fmt.Sprintf("HMAC-SHA256 %s", signature))

	client := &http.Client{Timeout: 30 * time.Second}
	return client.Do(req)
}

// APIHealthCheck checks the API health endpoint (no auth required)
func (h *E2ETestHelper) APIHealthCheck(t *testing.T) map[string]interface{} {
	t.Helper()

	endpoint := h.APIGatewayEndpoint()
	url := endpoint + "/api/v1/health"

	resp, err := http.Get(url)
	require.NoError(t, err, "failed to make health check request")
	defer resp.Body.Close()

	require.Equal(t, http.StatusOK, resp.StatusCode, "health check should return 200 OK")

	var result map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&result)
	require.NoError(t, err, "failed to decode health check response")

	return result
}

// APICreateDeliveryConfig creates a delivery configuration via API
func (h *E2ETestHelper) APICreateDeliveryConfig(t *testing.T, tenantID string, config map[string]interface{}) map[string]interface{} {
	t.Helper()

	path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs", tenantID)
	resp, err := h.makeAPIRequest(t, "POST", path, config)
	require.NoError(t, err, "failed to create delivery config")
	defer resp.Body.Close()

	require.Equal(t, http.StatusCreated, resp.StatusCode, "create should return 201 Created")

	var wrapper map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&wrapper)
	require.NoError(t, err, "failed to decode create response")

	// Extract the "data" field from the API response
	data, ok := wrapper["data"].(map[string]interface{})
	require.True(t, ok, "response should have 'data' field")

	return data
}

// APIGetDeliveryConfig retrieves a delivery configuration via API
func (h *E2ETestHelper) APIGetDeliveryConfig(t *testing.T, tenantID, configType string) map[string]interface{} {
	t.Helper()

	path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s", tenantID, configType)
	resp, err := h.makeAPIRequest(t, "GET", path, nil)
	require.NoError(t, err, "failed to get delivery config")
	defer resp.Body.Close()

	require.Equal(t, http.StatusOK, resp.StatusCode, "get should return 200 OK")

	var wrapper map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&wrapper)
	require.NoError(t, err, "failed to decode get response")

	// Extract the "data" field from the API response
	data, ok := wrapper["data"].(map[string]interface{})
	require.True(t, ok, "response should have 'data' field")

	return data
}

// APIGetDeliveryConfigRaw retrieves a delivery configuration and returns raw response (for error checking)
func (h *E2ETestHelper) APIGetDeliveryConfigRaw(t *testing.T, tenantID, configType string) (map[string]interface{}, error) {
	t.Helper()

	path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s", tenantID, configType)
	resp, err := h.makeAPIRequest(t, "GET", path, nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("unexpected status %d: %s", resp.StatusCode, string(body))
	}

	var result map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&result)
	return result, err
}

// APIUpdateDeliveryConfig updates a delivery configuration via API
func (h *E2ETestHelper) APIUpdateDeliveryConfig(t *testing.T, tenantID, configType string, updateData map[string]interface{}) map[string]interface{} {
	t.Helper()

	path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s", tenantID, configType)
	resp, err := h.makeAPIRequest(t, "PUT", path, updateData)
	require.NoError(t, err, "failed to update delivery config")
	defer resp.Body.Close()

	require.Equal(t, http.StatusOK, resp.StatusCode, "update should return 200 OK")

	var wrapper map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&wrapper)
	require.NoError(t, err, "failed to decode update response")

	// Extract the "data" field from the API response
	data, ok := wrapper["data"].(map[string]interface{})
	require.True(t, ok, "response should have 'data' field")

	return data
}

// APIDeleteDeliveryConfig deletes a delivery configuration via API
func (h *E2ETestHelper) APIDeleteDeliveryConfig(t *testing.T, tenantID, configType string) {
	t.Helper()

	path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs/%s", tenantID, configType)
	resp, err := h.makeAPIRequest(t, "DELETE", path, nil)
	require.NoError(t, err, "failed to delete delivery config")
	defer resp.Body.Close()

	require.Equal(t, http.StatusOK, resp.StatusCode, "delete should return 200 OK")
}

// APIListTenantConfigs lists all delivery configurations for a tenant via API
func (h *E2ETestHelper) APIListTenantConfigs(t *testing.T, tenantID string) map[string]interface{} {
	t.Helper()

	path := fmt.Sprintf("/api/v1/tenants/%s/delivery-configs", tenantID)
	resp, err := h.makeAPIRequest(t, "GET", path, nil)
	require.NoError(t, err, "failed to list tenant configs")
	defer resp.Body.Close()

	require.Equal(t, http.StatusOK, resp.StatusCode, "list should return 200 OK")

	var wrapper map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&wrapper)
	require.NoError(t, err, "failed to decode list response")

	// Extract the "data" field from the API response
	data, ok := wrapper["data"].(map[string]interface{})
	require.True(t, ok, "response should have 'data' field")

	return data
}
