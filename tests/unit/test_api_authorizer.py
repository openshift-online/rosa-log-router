"""
Comprehensive unit tests for the Lambda authorizer with HMAC authentication
"""

import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../api/src'))

from src.handlers.authorizer import lambda_handler, generate_policy
from src.utils.auth import (
    get_psk_from_secrets_manager, generate_signature, compute_body_hash,
    validate_timestamp, validate_request_signature, extract_auth_headers,
    authenticate_request, AuthenticationError
)


class TestGeneratePolicy:
    def test_generate_policy_allow(self):
        policy = generate_policy("test-user", "Allow",
            "arn:aws:execute-api:us-east-1:123456789012:abc123/prod/GET/api/v1/health")
        assert policy["principalId"] == "test-user"
        assert policy["policyDocument"]["Statement"][0]["Effect"] == "Allow"

    def test_generate_policy_deny(self):
        policy = generate_policy("unauthorized", "Deny", "*")
        assert policy["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_generate_policy_with_context(self):
        ctx = {"authenticated": "true"}
        policy = generate_policy("test-user", "Allow", "*", context=ctx)
        assert policy["context"] == ctx

    def test_generate_policy_without_context(self):
        policy = generate_policy("test-user", "Allow", "*")
        assert "context" not in policy


class TestGetPskFromSecretsManager:
    @patch('src.utils.auth.boto3.client')
    def test_get_psk_success(self, mock_boto3):
        mock_secrets = Mock()
        mock_boto3.return_value = mock_secrets
        mock_secrets.get_secret_value.return_value = {'SecretString': 'test-secret-key'}
        assert get_psk_from_secrets_manager('/test/parameter', 'us-east-1') == 'test-secret-key'

    @patch('src.utils.auth.boto3.client')
    @patch('src.utils.auth._psk_cache', {})
    def test_get_psk_caching(self, mock_boto3):
        mock_secrets = Mock()
        mock_boto3.return_value = mock_secrets
        mock_secrets.get_secret_value.return_value = {'SecretString': 'test-secret-key'}
        get_psk_from_secrets_manager('/test/parameter', 'us-east-1')
        get_psk_from_secrets_manager('/test/parameter', 'us-east-1')
        assert mock_secrets.get_secret_value.call_count == 1

    @patch('src.utils.auth.boto3.client')
    @patch('src.utils.auth.time.time')
    @patch('src.utils.auth._psk_cache', {})
    def test_get_psk_cache_expiry(self, mock_time, mock_boto3):
        mock_secrets = Mock()
        mock_boto3.return_value = mock_secrets
        mock_secrets.get_secret_value.return_value = {'SecretString': 'test-secret-key'}
        mock_time.return_value = 0
        get_psk_from_secrets_manager('/test/parameter', 'us-east-1')
        mock_time.return_value = 301
        get_psk_from_secrets_manager('/test/parameter', 'us-east-1')
        assert mock_secrets.get_secret_value.call_count == 2

    @patch('src.utils.auth.boto3.client')
    def test_get_psk_secrets_error(self, mock_boto3):
        mock_secrets = Mock()
        mock_boto3.return_value = mock_secrets
        mock_secrets.get_secret_value.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}}, 'GetSecretValue')
        with pytest.raises(AuthenticationError):
            get_psk_from_secrets_manager('/nonexistent/parameter', 'us-east-1')


class TestComputeBodyHash:
    def test_empty_body(self):
        assert compute_body_hash("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_deterministic(self):
        assert compute_body_hash('{"a":1}') == compute_body_hash('{"a":1}')

    def test_different_bodies(self):
        assert compute_body_hash('{"a":1}') != compute_body_hash('{"a":2}')

    def test_hex_format(self):
        h = compute_body_hash('{"tenant_id":"test"}')
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)


class TestGenerateSignature:
    def test_consistency(self):
        bh = compute_body_hash("")
        s1 = generate_signature("psk", "GET", "/api/v1/health", "2024-01-15T10:30:00Z", bh)
        s2 = generate_signature("psk", "GET", "/api/v1/health", "2024-01-15T10:30:00Z", bh)
        assert s1 == s2

    def test_different_methods(self):
        bh = compute_body_hash("")
        assert (generate_signature("psk", "GET", "/api", "ts", bh) !=
                generate_signature("psk", "POST", "/api", "ts", bh))

    def test_different_body_hashes(self):
        assert (generate_signature("psk", "POST", "/api", "ts", compute_body_hash('{"a":1}')) !=
                generate_signature("psk", "POST", "/api", "ts", compute_body_hash('{"a":2}')))

    def test_method_uppercase_normalisation(self):
        bh = compute_body_hash("")
        assert (generate_signature("psk", "GET", "/api", "ts", bh) ==
                generate_signature("psk", "get", "/api", "ts", bh))


class TestValidateTimestamp:
    def test_current(self):
        assert validate_timestamp(datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))

    def test_within_window(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat().replace('+00:00', 'Z')
        assert validate_timestamp(ts) is True

    def test_expired(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat().replace('+00:00', 'Z')
        assert validate_timestamp(ts) is False

    def test_future(self):
        ts = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace('+00:00', 'Z')
        assert validate_timestamp(ts) is False

    def test_invalid_format(self):
        for bad in ["not-a-ts", "2024-13-45T25:70:80Z", ""]:
            assert validate_timestamp(bad) is False


class TestValidateRequestSignature:
    def test_success(self):
        psk, method, uri, ts = "secret", "GET", "/api/v1/health", "2024-01-15T10:30:00Z"
        bh = compute_body_hash("")
        assert validate_request_signature(psk, method, uri, ts, generate_signature(psk, method, uri, ts, bh), bh)

    def test_failure(self):
        assert validate_request_signature(
            "secret", "GET", "/api", "ts", "0123456789abcdef" * 4, compute_body_hash("")) is False

    def test_body_tamper_detected(self):
        psk, method, uri, ts = "secret", "POST", "/api/v1/tenants", "2024-01-15T10:30:00Z"
        original_hash = compute_body_hash('{"tenant_id": "legit"}')
        tampered_hash = compute_body_hash('{"tenant_id": "attacker"}')
        sig = generate_signature(psk, method, uri, ts, original_hash)
        assert validate_request_signature(psk, method, uri, ts, sig, tampered_hash) is False

    def test_wrong_psk(self):
        bh = compute_body_hash("")
        sig = generate_signature("correct-psk", "GET", "/api", "ts", bh)
        assert validate_request_signature("wrong-psk", "GET", "/api", "ts", sig, bh) is False


class TestExtractAuthHeaders:
    def test_success(self):
        bh = compute_body_hash("")
        ts, sig, body_hash = extract_auth_headers({
            "Authorization": "HMAC-SHA256 abc123", "X-API-Timestamp": "ts", "X-Body-SHA256": bh})
        assert ts == "ts" and sig == "abc123" and body_hash == bh

    def test_case_insensitive(self):
        bh = compute_body_hash("")
        ts, sig, body_hash = extract_auth_headers({
            "authorization": "HMAC-SHA256 abc123", "x-api-timestamp": "ts", "x-body-sha256": bh})
        assert ts == "ts" and sig == "abc123" and body_hash == bh

    def test_missing_body_hash(self):
        _, _, body_hash = extract_auth_headers({
            "Authorization": "HMAC-SHA256 abc", "X-API-Timestamp": "ts"})
        assert body_hash is None

    def test_empty_headers(self):
        ts, sig, bh = extract_auth_headers({})
        assert ts is None and sig is None and bh is None

    def test_wrong_auth_format(self):
        _, sig, _ = extract_auth_headers({"Authorization": "Bearer jwt", "X-API-Timestamp": "ts",
                                           "X-Body-SHA256": compute_body_hash("")})
        assert sig is None


class TestAuthenticateRequest:
    @patch('src.utils.auth.get_psk_from_secrets_manager')
    @patch('src.utils.auth.validate_timestamp')
    @patch('src.utils.auth.validate_request_signature')
    def test_success(self, mock_sig, mock_ts, mock_psk):
        mock_psk.return_value = "psk"; mock_ts.return_value = True; mock_sig.return_value = True
        bh = compute_body_hash("")
        result = authenticate_request(
            headers={"Authorization": "HMAC-SHA256 abc", "X-API-Timestamp": "ts", "X-Body-SHA256": bh},
            method="GET", uri="/api/v1/health", body="", psk_secret_name="/test/psk", region="us-east-1")
        assert result is True

    def test_missing_body_hash_header(self):
        result = authenticate_request(
            headers={"Authorization": "HMAC-SHA256 abc", "X-API-Timestamp": "ts"},
            method="GET", uri="/api", body="", psk_secret_name="/test/psk", region="us-east-1")
        assert result is False

    def test_missing_headers(self):
        assert authenticate_request(headers={}, method="GET", uri="/api",
                                    body="", psk_secret_name="/test/psk", region="us-east-1") is False

    @patch('src.utils.auth.get_psk_from_secrets_manager')
    @patch('src.utils.auth.validate_timestamp')
    def test_invalid_timestamp(self, mock_ts, mock_psk):
        mock_ts.return_value = False
        result = authenticate_request(
            headers={"Authorization": "HMAC-SHA256 abc", "X-API-Timestamp": "ts",
                     "X-Body-SHA256": compute_body_hash("")},
            method="GET", uri="/api", body="", psk_secret_name="/test/psk", region="us-east-1")
        assert result is False
        mock_psk.assert_not_called()


class TestLambdaHandler:
    def _event(self, method="POST", path="/api/v1/tenants", body=None,
                sig="abcdef1234567890", ts="2024-01-15T10:30:00Z", bh=None):
        return {
            "type": "REQUEST",
            "methodArn": f"arn:aws:execute-api:us-east-1:123456789012:x/prod/{method}{path}",
            "resource": path, "path": path, "httpMethod": method,
            "headers": {"Authorization": f"HMAC-SHA256 {sig}", "X-API-Timestamp": ts,
                        "X-Body-SHA256": bh or compute_body_hash(body or "")},
            "queryStringParameters": None, "body": body,
            "requestContext": {"httpMethod": method, "stage": "prod"},
        }

    @patch('src.handlers.authorizer.authenticate_request')
    def test_success(self, mock_auth):
        mock_auth.return_value = True
        result = lambda_handler(self._event(), None)
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert result["context"]["authenticated"] == "true"

    @patch('src.handlers.authorizer.authenticate_request')
    def test_failure(self, mock_auth):
        mock_auth.return_value = False
        assert lambda_handler(self._event(), None)["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    @patch('src.handlers.authorizer.authenticate_request')
    def test_auth_error(self, mock_auth):
        mock_auth.side_effect = Exception("SM failed")
        result = lambda_handler(self._event(), None)
        assert result["principalId"] == "auth-error"

    def test_unexpected_error(self):
        result = lambda_handler({"httpMethod": "GET"}, None)
        assert result["principalId"] == "error"
        assert result["policyDocument"]["Statement"][0]["Resource"] == "*"

    @patch('src.handlers.authorizer.authenticate_request')
    def test_method_normalization(self, mock_auth):
        mock_auth.return_value = True
        event = self._event(method="ANY")
        event["requestContext"] = {"httpMethod": "GET", "stage": "prod"}
        lambda_handler(event, None)
        assert mock_auth.call_args[1]["method"] == "GET"


class TestEdgeCases:
    def test_empty_signature(self):
        assert validate_request_signature("psk", "GET", "/api", "ts", "", compute_body_hash("")) is False

    def test_unicode_body_hash(self):
        bh = compute_body_hash('{"tenant_id": "café"}')
        sig = generate_signature("psk", "POST", "/api", "ts", bh)
        assert validate_request_signature("psk", "POST", "/api", "ts", sig, bh) is True

    def test_very_long_uri(self):
        long_uri = "/api?" + "&".join([f"p{i}=v{i}" for i in range(100)])
        sig = generate_signature("psk", "GET", long_uri, "ts", compute_body_hash(""))
        assert len(sig) == 64

    @patch('src.utils.auth.logger')
    def test_logging_on_missing_headers(self, mock_logger):
        authenticate_request(headers={}, method="GET", uri="/api",
                             body="", psk_secret_name="/test/psk", region="us-east-1")
        mock_logger.warning.assert_called_with("Missing authentication headers")
