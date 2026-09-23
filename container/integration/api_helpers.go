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
	"net/url"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// generateHMACSignature generates HMAC-SHA256 signature for API authentication.
// Signed message: UPPER(METHOD) + URI + TIMESTAMP + BODY_HASH
// where BODY_HASH is hex SHA-256 of the request body (empty string for bodyless requests).
func generateHMACSignature(psk, method, path, timestamp, bodyHash string) string {
	message := fmt.Sprintf("%s%s%s%s", strings.ToUpper(method), path, timestamp, bodyHash)
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

	// Add HMAC authentication headers.
	// Body hash is sent as X-Body-SHA256 and included in the signed message so
	// the REST API Gateway authorizer can verify body integrity without needing
	// access to the raw request body (which authorizers don't receive).
	timestamp := time.Now().UTC().Format(time.RFC3339)
	bodyHashArr := sha256.Sum256(bodyBytes)
	bodyHash := hex.EncodeToString(bodyHashArr[:])
	signature := generateHMACSignature(h.APIPSK(), method, path, timestamp, bodyHash)

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-API-Timestamp", timestamp)
	req.Header.Set("X-Body-SHA256", bodyHash)
	req.Header.Set("Authorization", fmt.Sprintf("HMAC-SHA256 %s", signature))

	client := &http.Client{Timeout: 30 * time.Second}
	return client.Do(req)
}

// makeAPIRequestWithQuery makes an authenticated request that carries query
// parameters. The signed URI must byte-for-byte match what the API Gateway
// authorizer reconstructs: it takes the (URL-decoded) queryStringParameters map
// and rebuilds "path?k=v&k=v" in query-string order (see api/src/handlers/authorizer.py).
//
// We therefore build two strings from the same ordered slice: the signed URI
// uses raw (decoded) values, while the request URL uses URL-escaped values. This
// matters for last_key, whose value contains a literal '#' that must be escaped
// in the URL (or it would be treated as a fragment) but appears decoded in the
// signed message.
func (h *E2ETestHelper) makeAPIRequestWithQuery(t *testing.T, method, basePath string, query [][2]string, body interface{}) (*http.Response, error) {
	t.Helper()

	signPath := basePath
	requestPath := basePath
	if len(query) > 0 {
		rawPairs := make([]string, 0, len(query))     // k=v with decoded values (signed)
		escapedPairs := make([]string, 0, len(query)) // k=escape(v) (actual URL)
		for _, kv := range query {
			rawPairs = append(rawPairs, fmt.Sprintf("%s=%s", kv[0], kv[1]))
			escapedPairs = append(escapedPairs, fmt.Sprintf("%s=%s", kv[0], url.QueryEscape(kv[1])))
		}
		signPath = basePath + "?" + strings.Join(rawPairs, "&")
		requestPath = basePath + "?" + strings.Join(escapedPairs, "&")
	}

	var bodyBytes []byte
	var err error
	if body != nil {
		bodyBytes, err = json.Marshal(body)
		require.NoError(t, err, "failed to marshal request body")
	}

	req, err := http.NewRequest(method, h.APIGatewayEndpoint()+requestPath, bytes.NewReader(bodyBytes))
	require.NoError(t, err, "failed to create HTTP request")

	timestamp := time.Now().UTC().Format(time.RFC3339)
	bodyHashArr := sha256.Sum256(bodyBytes)
	bodyHash := hex.EncodeToString(bodyHashArr[:])
	signature := generateHMACSignature(h.APIPSK(), method, signPath, timestamp, bodyHash)

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-API-Timestamp", timestamp)
	req.Header.Set("X-Body-SHA256", bodyHash)
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

// APIListAllDeliveryConfigs lists delivery configs across all tenants via the
// paginated list-all endpoint (GET /api/v1/delivery-configs). Pass an empty
// lastKey for the first page; the returned data's "last_key" (present only when
// more pages remain) feeds the next call.
func (h *E2ETestHelper) APIListAllDeliveryConfigs(t *testing.T, limit int, lastKey string) map[string]interface{} {
	t.Helper()

	// Order matters: limit first, then last_key. The authorizer reconstructs the
	// signed URI in query-string order, so the request URL and signed URI (built
	// from this same slice) stay consistent.
	query := [][2]string{{"limit", strconv.Itoa(limit)}}
	if lastKey != "" {
		query = append(query, [2]string{"last_key", lastKey})
	}

	resp, err := h.makeAPIRequestWithQuery(t, "GET", "/api/v1/delivery-configs", query, nil)
	require.NoError(t, err, "failed to list all delivery configs")
	defer resp.Body.Close()

	require.Equal(t, http.StatusOK, resp.StatusCode, "list-all should return 200 OK")

	var wrapper map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&wrapper)
	require.NoError(t, err, "failed to decode list-all response")

	data, ok := wrapper["data"].(map[string]interface{})
	require.True(t, ok, "response should have 'data' field")

	return data
}
