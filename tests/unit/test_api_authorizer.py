"""
Comprehensive unit tests for the Lambda authorizer with HMAC authentication
"""

import json
import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Setup path for importing API modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api/src'))

# Import the modules we're testing
from src.handlers.authorizer import lambda_handler, generate_policy
from src.utils.auth import (
    get_psk_from_secrets_manager,
    generate_signature,
    compute_body_hash,
    validate_timestamp,
    validate_request_signature,
    extract_auth_headers,
    authenticate_request,
    AuthenticationError
)


class TestGeneratePolicy:
    """Test cases for IAM policy generation"""

    def test_generate_policy_allow(self):
        """Test generating an Allow policy"""
        policy = generate_policy(
            principal_id="test-user",
            effect="Allow",
            resource="arn:aws:execute-api:us-east-1:123456789012:abc123/prod/GET/api/v1/health"
        )

        assert policy["principalId"] == "test-user"
        assert policy["policyDocument"]["Version"] == "2012-10-17"
        assert len(policy["policyDocument"]["Statement"]) == 1

        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Action"] == "execute-api:Invoke"
        assert statement["Effect"] == "Allow"
        assert statement["Resource"] == "arn:aws:execute-api:us-east-1:123456789012:abc123/prod/GET/api/v1/health"

    def test_generate_policy_deny(self):
        """Test generating a Deny policy"""
        policy = generate_policy(
            principal_id="unauthorized",
            effect="Deny",
            resource="*"
        )

        assert policy["principalId"] == "unauthorized"
        statement = policy["policyDocument"]["Statement"][0]
        assert statement["Effect"] == "Deny"
        assert statement["Resource"] == "*"

    def test_generate_policy_with_context(self):
        """Test generating a policy with additional context"""
        context = {
            "authenticated": "true",
            "authMethod": "hmac-sha256"
        }

        policy = generate_policy(
            principal_id="test-user",
            effect="Allow",
            resource="arn:aws:execute-api:us-east-1:123456789012:abc123/prod/*",
            context=context
        )

        assert policy["context"] == context

    def test_generate_policy_without_context(self):
        """Test generating a policy without context"""
        policy = generate_policy(
            principal_id="test-user",
            effect="Allow",
            resource="arn:aws:execute-api:us-east-1:123456789012:abc123/prod/*"
        )

        assert "context" not in policy


class TestGetPskFromSecretsManager:
    """Test cases for PSK retrieval from Secrets Manager"""

    @patch('src.utils.auth.boto3.client')
    def test_get_psk_success(self, mock_boto3):
        """Test successful PSK retrieval"""
        mock_secrets = Mock()
        mock_boto3.return_value = mock_secrets
        mock_secrets.get_secret_value.return_value = {
            'SecretString': 'test-secret-key'
        }

        psk = get_psk_from_secrets_manager('/test/parameter', 'us-east-1')

        assert psk == 'test-secret-key'
        mock_boto3.assert_called_once_with('secretsmanager', region_name='us-east-1')
        mock_secrets.get_secret_value.assert_called_once_with(
            SecretId='/test/parameter'
        )

    @patch('src.utils.auth.boto3.client')
    @patch('src.utils.auth._psk_cache', {})
    def test_get_psk_caching(self, mock_boto3):
        """Test PSK caching functionality"""
        mock_secrets = Mock()
        mock_boto3.return_value = mock_secrets
        mock_secrets.get_secret_value.return_value = {
            'SecretString': 'test-secret-key'
        }

        psk1 = get_psk_from_secrets_manager('/test/parameter', 'us-east-1')
        psk2 = get_psk_from_secrets_manager('/test/parameter', 'us-east-1')

        assert psk1 == psk2 == 'test-secret-key'
        assert mock_secrets.get_secret_value.call_count == 1

    @patch('src.utils.auth.boto3.client')
    @patch('src.utils.auth.time.time')
    @patch('src.utils.auth._psk_cache', {})
    def test_get_psk_cache_expiry(self, mock_time, mock_boto3):
        """Test PSK cache expiry"""
        mock_secrets = Mock()
        mock_boto3.return_value = mock_secrets
        mock_secrets.get_secret_value.return_value = {
            'SecretString': 'test-secret-key'
        }

        mock_time.return_value = 0
        psk1 = get_psk_from_secrets_manager('/test/parameter', 'us-east-1')

        mock_time.return_value = 301
        psk2 = get_psk_from_secrets_manager('/test/parameter', 'us-east-1')

        assert psk1 == psk2 == 'test-secret-key'
        assert mock_secrets.get_secret_value.call_count == 2

    @patch('src.utils.auth.boto3.client')
    def test_get_psk_secrets_error(self, mock_boto3):
        """Test PSK retrieval when Secrets Manager fails"""
        mock_secrets = Mock()
        mock_boto3.return_value = mock_secrets
        mock_secrets.get_secret_value.side_effect = ClientError(
            error_response={'Error': {'Code': 'ResourceNotFoundException'}},
            operation_name='GetSecretValue'
        )

        with pytest.raises(AuthenticationError, match="Failed to retrieve authentication key"):
            get_psk_from_secrets_manager('/nonexistent/parameter', 'us-east-1')


class TestComputeBodyHash:
    """Test cases for body hash computation"""

    def test_compute_body_hash_empty(self):
        """SHA-256 of empty string is stable"""
        assert compute_body_hash("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_compute_body_hash_json(self):
        """Hash of a JSON body is a 64-char hex string"""
        h = compute_body_hash('{"tenant_id": "test"}')
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)

    def test_compute_body_hash_deterministic(self):
        """Same body produces same hash"""
        body = '{"a": 1}'
        assert compute_body_hash(body) == compute_body_hash(body)

    def test_compute_body_hash_different_bodies(self):
        """Different bodies produce different hashes"""
        assert compute_body_hash('{"a": 1}') != compute_body_hash('{"a": 2}')


class TestGenerateSignature:
    """Test cases for HMAC signature generation"""

    def test_generate_signature_with_body_hash(self):
        """Test signature generation including body hash"""
        psk = "secret-key"
        method = "POST"
        uri = "/api/v1/tenants"
        timestamp = "2024-01-15T10:30:00Z"
        body_hash = compute_body_hash('{"tenant_id": "test"}')

        signature = generate_signature(psk, method, uri, timestamp, body_hash)

        assert len(signature) == 64
        assert all(c in '0123456789abcdef' for c in signature)

    def test_generate_signature_empty_body_hash(self):
        """Test signature generation with empty body (GET)"""
        psk = "secret-key"
        method = "GET"
        uri = "/api/v1/tenants"
        timestamp = "2024-01-15T10:30:00Z"

        signature = generate_signature(psk, method, uri, timestamp, compute_body_hash(""))

        assert len(signature) == 64
        assert all(c in '0123456789abcdef' for c in signature)

    def test_generate_signature_consistency(self):
        """Test that same inputs produce same signature"""
        psk = "secret-key"
        method = "GET"
        uri = "/api/v1/health"
        timestamp = "2024-01-15T10:30:00Z"
        body_hash = compute_body_hash("")

        assert generate_signature(psk, method, uri, timestamp, body_hash) == \
               generate_signature(psk, method, uri, timestamp, body_hash)

    def test_generate_signature_different_methods(self):
        """Test that different methods produce different signatures"""
        psk = "secret-key"
        uri = "/api/v1/health"
        timestamp = "2024-01-15T10:30:00Z"
        body_hash = compute_body_hash("")

        assert generate_signature(psk, "GET", uri, timestamp, body_hash) != \
               generate_signature(psk, "POST", uri, timestamp, body_hash)

    def test_generate_signature_different_body_hashes(self):
        """Test that different body hashes produce different signatures"""
        psk = "secret-key"
        uri = "/api/v1/tenants"
        timestamp = "2024-01-15T10:30:00Z"

        sig1 = generate_signature(psk, "POST", uri, timestamp, compute_body_hash('{"a": 1}'))
        sig2 = generate_signature(psk, "POST", uri, timestamp, compute_body_hash('{"a": 2}'))

        assert sig1 != sig2

    def test_generate_signature_case_insensitive_method(self):
        """Test that method is normalized to uppercase"""
        psk = "secret-key"
        uri = "/api/v1/health"
        timestamp = "2024-01-15T10:30:00Z"
        body_hash = compute_body_hash("")

        assert generate_signature(psk, "GET", uri, timestamp, body_hash) == \
               generate_signature(psk, "get", uri, timestamp, body_hash)


class TestValidateTimestamp:
    """Test cases for timestamp validation"""

    def test_validate_timestamp_current(self):
        """Test validation of current timestamp"""
        current_time = datetime.now(timezone.utc)
        timestamp_str = current_time.isoformat().replace('+00:00', 'Z')

        assert validate_timestamp(timestamp_str) is True

    def test_validate_timestamp_within_window(self):
        """Test validation of timestamp within acceptable window"""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        timestamp_str = past_time.isoformat().replace('+00:00', 'Z')

        assert validate_timestamp(timestamp_str) is True

    def test_validate_timestamp_expired(self):
        """Test validation of expired timestamp"""
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        timestamp_str = expired_time.isoformat().replace('+00:00', 'Z')

        assert validate_timestamp(timestamp_str) is False

    def test_validate_timestamp_future(self):
        """Test validation of future timestamp"""
        future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        timestamp_str = future_time.isoformat().replace('+00:00', 'Z')

        assert validate_timestamp(timestamp_str) is False

    def test_validate_timestamp_custom_window(self):
        """Test validation with custom time window"""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=8)
        timestamp_str = past_time.isoformat().replace('+00:00', 'Z')

        assert validate_timestamp(timestamp_str) is False
        assert validate_timestamp(timestamp_str, max_age_seconds=600) is True

    def test_validate_timestamp_invalid_format(self):
        """Test validation of malformed timestamp"""
        for invalid_ts in ["not-a-timestamp", "2024-13-45T25:70:80Z", ""]:
            assert validate_timestamp(invalid_ts) is False

    def test_validate_timestamp_no_timezone(self):
        """Test validation of timestamp without timezone (should default to UTC)"""
        current_time = datetime.now(timezone.utc)
        timestamp_str = current_time.strftime('%Y-%m-%dT%H:%M:%S')

        assert validate_timestamp(timestamp_str) is True


class TestValidateRequestSignature:
    """Test cases for request signature validation"""

    def test_validate_signature_success(self):
        """Test successful signature validation using body hash"""
        psk = "secret-key"
        method = "GET"
        uri = "/api/v1/health"
        timestamp = "2024-01-15T10:30:00Z"
        body_hash = compute_body_hash("")

        expected_signature = generate_signature(psk, method, uri, timestamp, body_hash)

        assert validate_request_signature(
            psk, method, uri, timestamp, expected_signature, body_hash
        ) is True

    def test_validate_signature_failure(self):
        """Test signature validation failure"""
        psk = "secret-key"
        method = "GET"
        uri = "/api/v1/health"
        timestamp = "2024-01-15T10:30:00Z"

        wrong_signature = "0123456789abcdef" * 4

        assert validate_request_signature(
            psk, method, uri, timestamp, wrong_signature, compute_body_hash("")
        ) is False

    def test_validate_signature_with_body_hash(self):
        """Test signature validation with non-empty body hash"""
        psk = "secret-key"
        method = "POST"
        uri = "/api/v1/tenants"
        timestamp = "2024-01-15T10:30:00Z"
        body_hash = compute_body_hash('{"tenant_id": "test"}')

        expected_signature = generate_signature(psk, method, uri, timestamp, body_hash)

        assert validate_request_signature(
            psk, method, uri, timestamp, expected_signature, body_hash
        ) is True

    def test_validate_signature_body_tamper_detected(self):
        """Body tampering detected: signature over original hash fails against different hash"""
        psk = "secret-key"
        method = "POST"
        uri = "/api/v1/tenants"
        timestamp = "2024-01-15T10:30:00Z"
        original_hash = compute_body_hash('{"tenant_id": "legit-tenant"}')
        tampered_hash = compute_body_hash('{"tenant_id": "attacker-tenant"}')

        signature = generate_signature(psk, method, uri, timestamp, original_hash)

        assert validate_request_signature(
            psk, method, uri, timestamp, signature, tampered_hash
        ) is False

    def test_validate_signature_wrong_psk(self):
        """Test signature validation with wrong PSK"""
        psk = "secret-key"
        wrong_psk = "wrong-key"
        method = "GET"
        uri = "/api/v1/health"
        timestamp = "2024-01-15T10:30:00Z"
        body_hash = compute_body_hash("")

        signature = generate_signature(psk, method, uri, timestamp, body_hash)

        assert validate_request_signature(
            wrong_psk, method, uri, timestamp, signature, body_hash
        ) is False


class TestExtractAuthHeaders:
    """Test cases for authentication header extraction"""

    def test_extract_auth_headers_success(self):
        """Test successful header extraction including X-Body-SHA256"""
        body_hash = compute_body_hash("")
        headers = {
            "Authorization": "HMAC-SHA256 abcdef1234567890",
            "X-API-Timestamp": "2024-01-15T10:30:00Z",
            "X-Body-SHA256": body_hash,
            "Content-Type": "application/json"
        }

        timestamp, signature, extracted_hash = extract_auth_headers(headers)

        assert timestamp == "2024-01-15T10:30:00Z"
        assert signature == "abcdef1234567890"
        assert extracted_hash == body_hash

    def test_extract_auth_headers_case_insensitive(self):
        """Test header extraction with different cases"""
        body_hash = compute_body_hash("")
        headers = {
            "authorization": "HMAC-SHA256 abcdef1234567890",
            "x-api-timestamp": "2024-01-15T10:30:00Z",
            "x-body-sha256": body_hash,
        }

        timestamp, signature, extracted_hash = extract_auth_headers(headers)

        assert timestamp == "2024-01-15T10:30:00Z"
        assert signature == "abcdef1234567890"
        assert extracted_hash == body_hash

    def test_extract_auth_headers_missing_body_hash(self):
        """Missing X-Body-SHA256 returns None for body_hash"""
        headers = {
            "Authorization": "HMAC-SHA256 abcdef1234567890",
            "X-API-Timestamp": "2024-01-15T10:30:00Z"
        }

        timestamp, signature, body_hash = extract_auth_headers(headers)

        assert timestamp == "2024-01-15T10:30:00Z"
        assert signature == "abcdef1234567890"
        assert body_hash is None

    def test_extract_auth_headers_missing_authorization(self):
        """Test header extraction with missing Authorization header"""
        headers = {
            "X-API-Timestamp": "2024-01-15T10:30:00Z",
            "X-Body-SHA256": compute_body_hash(""),
        }

        timestamp, signature, body_hash = extract_auth_headers(headers)

        assert timestamp == "2024-01-15T10:30:00Z"
        assert signature is None

    def test_extract_auth_headers_wrong_auth_format(self):
        """Test header extraction with wrong Authorization format"""
        headers = {
            "Authorization": "Bearer some-jwt-token",
            "X-API-Timestamp": "2024-01-15T10:30:00Z",
            "X-Body-SHA256": compute_body_hash(""),
        }

        timestamp, signature, body_hash = extract_auth_headers(headers)

        assert timestamp == "2024-01-15T10:30:00Z"
        assert signature is None

    def test_extract_auth_headers_empty(self):
        """Test header extraction with empty headers"""
        timestamp, signature, body_hash = extract_auth_headers({})

        assert timestamp is None
        assert signature is None
        assert body_hash is None


class TestAuthenticateRequest:
    """Test cases for complete authentication workflow"""

    @patch('src.utils.auth.get_psk_from_secrets_manager')
    @patch('src.utils.auth.validate_timestamp')
    @patch('src.utils.auth.validate_request_signature')
    def test_authenticate_request_success(self, mock_validate_sig, mock_validate_ts, mock_get_psk):
        """Test successful request authentication"""
        mock_get_psk.return_value = "secret-key"
        mock_validate_ts.return_value = True
        mock_validate_sig.return_value = True

        body_hash = compute_body_hash("")
        headers = {
            "Authorization": "HMAC-SHA256 abcdef1234567890",
            "X-API-Timestamp": "2024-01-15T10:30:00Z",
            "X-Body-SHA256": body_hash,
        }

        result = authenticate_request(
            headers=headers, method="GET", uri="/api/v1/health",
            body="", psk_secret_name="/test/psk", region="us-east-1"
        )

        assert result is True
        mock_validate_sig.assert_called_once_with(
            "secret-key", "GET", "/api/v1/health", "2024-01-15T10:30:00Z",
            "abcdef1234567890", body_hash
        )

    def test_authenticate_request_missing_body_hash_header(self):
        """Missing X-Body-SHA256 header is rejected"""
        headers = {
            "Authorization": "HMAC-SHA256 abcdef1234567890",
            "X-API-Timestamp": "2024-01-15T10:30:00Z",
        }

        result = authenticate_request(
            headers=headers, method="GET", uri="/api/v1/health",
            body="", psk_secret_name="/test/psk", region="us-east-1"
        )

        assert result is False

    def test_authenticate_request_missing_headers(self):
        """Test authentication with missing auth headers"""
        result = authenticate_request(
            headers={"Content-Type": "application/json"},
            method="GET", uri="/api/v1/health",
            body="", psk_secret_name="/test/psk", region="us-east-1"
        )

        assert result is False

    @patch('src.utils.auth.get_psk_from_secrets_manager')
    @patch('src.utils.auth.validate_timestamp')
    def test_authenticate_request_invalid_timestamp(self, mock_validate_ts, mock_get_psk):
        """Test authentication with invalid timestamp"""
        mock_validate_ts.return_value = False

        headers = {
            "Authorization": "HMAC-SHA256 abcdef1234567890",
            "X-API-Timestamp": "2024-01-15T10:30:00Z",
            "X-Body-SHA256": compute_body_hash(""),
        }

        result = authenticate_request(
            headers=headers, method="GET", uri="/api/v1/health",
            body="", psk_secret_name="/test/psk", region="us-east-1"
        )

        assert result is False
        mock_get_psk.assert_not_called()

    @patch('src.utils.auth.get_psk_from_secrets_manager')
    @patch('src.utils.auth.validate_timestamp')
    def test_authenticate_request_psk_error(self, mock_validate_ts, mock_get_psk):
        """Test authentication when PSK retrieval fails"""
        mock_validate_ts.return_value = True
        mock_get_psk.side_effect = AuthenticationError("Failed to retrieve PSK")

        headers = {
            "Authorization": "HMAC-SHA256 abcdef1234567890",
            "X-API-Timestamp": "2024-01-15T10:30:00Z",
            "X-Body-SHA256": compute_body_hash(""),
        }

        with pytest.raises(AuthenticationError, match="Failed to retrieve PSK"):
            authenticate_request(
                headers=headers, method="GET", uri="/api/v1/health",
                body="", psk_secret_name="/test/psk", region="us-east-1"
            )


class TestLambdaHandler:
    """Test cases for the Lambda authorizer handler"""

    def _make_event(self, method="POST", path="/api/v1/tenants", body=None, sig="abcdef1234567890",
                    ts="2024-01-15T10:30:00Z", body_hash=None):
        if body_hash is None:
            body_hash = compute_body_hash(body or "")
        return {
            "type": "REQUEST",
            "methodArn": f"arn:aws:execute-api:us-east-1:123456789012:abc123/prod/{method}{path}",
            "resource": path, "path": path,
            "httpMethod": method,
            "headers": {
                "Authorization": f"HMAC-SHA256 {sig}",
                "X-API-Timestamp": ts,
                "X-Body-SHA256": body_hash,
            },
            "queryStringParameters": None,
            "body": body,
            "requestContext": {"httpMethod": method, "stage": "prod"},
        }

    @patch('src.handlers.authorizer.authenticate_request')
    def test_lambda_handler_success(self, mock_authenticate):
        """Test successful authorization"""
        mock_authenticate.return_value = True

        result = lambda_handler(self._make_event(), None)

        assert result["principalId"] == "authenticated-user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert result["context"]["authenticated"] == "true"

    @patch('src.handlers.authorizer.authenticate_request')
    def test_lambda_handler_failure(self, mock_authenticate):
        """Test failed authorization"""
        mock_authenticate.return_value = False

        result = lambda_handler(self._make_event(sig="wrongsignature"), None)

        assert result["principalId"] == "unauthenticated"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    @patch('src.handlers.authorizer.authenticate_request')
    def test_lambda_handler_auth_error(self, mock_authenticate):
        """Test authorization with authentication system error"""
        mock_authenticate.side_effect = Exception("SM connection failed")

        result = lambda_handler(self._make_event(), None)

        assert result["principalId"] == "auth-error"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    @patch('src.handlers.authorizer.authenticate_request')
    def test_lambda_handler_with_body(self, mock_authenticate):
        """Handler passes body hash from X-Body-SHA256 header"""
        mock_authenticate.return_value = True
        body = '{"tenant_id": "test-tenant"}'
        body_hash = compute_body_hash(body)

        result = lambda_handler(
            self._make_event(method="POST", body=body, body_hash=body_hash), None
        )

        assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        call_headers = mock_authenticate.call_args[1]["headers"]
        # Authorizer must forward X-Body-SHA256 so authenticate_request can use it
        assert call_headers.get("X-Body-SHA256") == body_hash or \
               call_headers.get("x-body-sha256") == body_hash

    def test_lambda_handler_unexpected_error(self):
        """Test handler with unexpected error"""
        result = lambda_handler({"httpMethod": "GET"}, None)

        assert result["principalId"] == "error"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"
        assert result["policyDocument"]["Statement"][0]["Resource"] == "*"

    @patch('src.handlers.authorizer.authenticate_request')
    def test_lambda_handler_method_normalization(self, mock_authenticate):
        """Handler properly normalizes HTTP method from request context"""
        mock_authenticate.return_value = True

        event = self._make_event(method="ANY")
        event["requestContext"] = {"httpMethod": "GET", "stage": "prod"}

        result = lambda_handler(event, None)

        assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        call_args = mock_authenticate.call_args
        assert call_args[1]["method"] == "GET"


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_signature(self):
        """Test handling of empty signature"""
        assert validate_request_signature(
            psk="secret-key",
            method="GET",
            uri="/api/v1/health",
            timestamp="2024-01-15T10:30:00Z",
            provided_signature="",
            body_hash=compute_body_hash(""),
        ) is False

    def test_malformed_signature_header(self):
        """Test handling of malformed Authorization header"""
        headers = {
            "Authorization": "InvalidFormat",
            "X-API-Timestamp": "2024-01-15T10:30:00Z",
            "X-Body-SHA256": compute_body_hash(""),
        }

        timestamp, signature, body_hash = extract_auth_headers(headers)
        assert signature is None

    def test_unicode_in_body_hash(self):
        """Body hash computed from unicode content validates correctly"""
        psk = "secret-key"
        method = "POST"
        uri = "/api/v1/tenants"
        timestamp = "2024-01-15T10:30:00Z"
        body = '{"tenant_id": "café-tenant", "description": "Tëst"}'
        body_hash = compute_body_hash(body)

        signature = generate_signature(psk, method, uri, timestamp, body_hash)
        assert validate_request_signature(psk, method, uri, timestamp, signature, body_hash) is True

    def test_very_long_uri(self):
        """Test handling of very long URIs"""
        psk = "secret-key"
        long_uri = "/api/v1/tenants?" + "&".join([f"param{i}=value{i}" for i in range(100)])
        timestamp = "2024-01-15T10:30:00Z"

        signature = generate_signature(psk, "GET", long_uri, timestamp, compute_body_hash(""))
        assert len(signature) == 64

    @patch('src.utils.auth.logger')
    def test_logging_on_validation_failure(self, mock_logger):
        """Test that validation failures are properly logged"""
        authenticate_request(
            headers={},
            method="GET", uri="/api/v1/health",
            body="", psk_secret_name="/test/psk", region="us-east-1"
        )

        mock_logger.warning.assert_called_with("Missing authentication headers")
