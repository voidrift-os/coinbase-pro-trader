"""
Unit tests for the authentication module.

Tests credential loading, validation, request signing, and permission checking.
"""

from __future__ import annotations

import base64
import json
import os
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest

from src import auth as auth_mod
from src.auth import (
    AuthenticationError,
    CoinbaseAuth,
    CoinbaseCredentials,
    PermissionError,
    get_authenticator,
)


class TestCoinbaseCredentials(TestCase):
    """Test CoinbaseCredentials class."""

    def test_valid_credentials(self):
        """Test creating credentials with valid data."""
        creds = CoinbaseCredentials(
            api_key="test_api_key_12345", api_secret="test_api_secret_67890"
        )
        self.assertEqual(creds.api_key, "test_api_key_12345")
        self.assertEqual(creds.api_secret, "test_api_secret_67890")
        self.assertIsNone(creds.api_passphrase)

    def test_credentials_with_passphrase(self):
        """Test creating credentials with passphrase."""
        creds = CoinbaseCredentials(
            api_key="test_api_key_12345",
            api_secret="test_api_secret_67890",
            api_passphrase="test_passphrase",
        )
        self.assertEqual(creds.api_passphrase, "test_passphrase")

    def test_empty_api_key_raises_error(self):
        """Test that empty API key raises AuthenticationError."""
        with self.assertRaises(AuthenticationError) as ctx:
            CoinbaseCredentials(api_key="", api_secret="test_secret")
        self.assertIn("API key cannot be empty", str(ctx.exception))

    def test_empty_api_secret_raises_error(self):
        """Test that empty API secret raises AuthenticationError."""
        with self.assertRaises(AuthenticationError) as ctx:
            CoinbaseCredentials(api_key="test_key", api_secret="")
        self.assertIn("API secret cannot be empty", str(ctx.exception))

    def test_short_api_key_raises_error(self):
        """Test that short API key raises AuthenticationError."""
        with self.assertRaises(AuthenticationError) as ctx:
            CoinbaseCredentials(api_key="short", api_secret="test_secret_67890")
        self.assertIn("API key appears to be invalid", str(ctx.exception))

    def test_short_api_secret_raises_error(self):
        """Test that short API secret raises AuthenticationError."""
        with self.assertRaises(AuthenticationError) as ctx:
            CoinbaseCredentials(api_key="test_key_12345", api_secret="short")
        self.assertIn("API secret appears to be invalid", str(ctx.exception))

    def test_secure_repr(self):
        """Test that __repr__ doesn't expose full credentials."""
        creds = CoinbaseCredentials(
            api_key="test_api_key_12345", api_secret="test_api_secret_67890"
        )
        repr_str = repr(creds)
        self.assertIn("***2345", repr_str)
        self.assertNotIn("test_api_key_12345", repr_str)
        self.assertNotIn("test_api_secret_67890", repr_str)


class TestCoinbaseAuth(TestCase):
    """Test CoinbaseAuth class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_creds = CoinbaseCredentials(
            api_key="test_api_key_12345",
            api_secret=base64.b64encode(b"test_secret_67890").decode("utf-8"),
        )

    @patch.dict(
        os.environ,
        {
            "COINBASE_API_KEY": "env_api_key_12345",
            "COINBASE_API_SECRET": base64.b64encode(b"env_secret_67890").decode("utf-8"),
        },
    )
    def test_load_from_env(self):
        """Test loading credentials from environment variables."""
        creds = CoinbaseAuth.load_from_env()
        self.assertEqual(creds.api_key, "env_api_key_12345")
        self.assertEqual(creds.api_secret, base64.b64encode(b"env_secret_67890").decode("utf-8"))
        self.assertIsNone(creds.api_passphrase)

    @patch.dict(
        os.environ,
        {
            "COINBASE_API_KEY": "env_api_key_12345",
            "COINBASE_API_SECRET": base64.b64encode(b"env_secret_67890").decode("utf-8"),
            "COINBASE_API_PASSPHRASE": "env_passphrase",
        },
    )
    def test_load_from_env_with_passphrase(self):
        """Test loading credentials with passphrase from environment."""
        creds = CoinbaseAuth.load_from_env()
        self.assertEqual(creds.api_passphrase, "env_passphrase")

    @patch.dict(os.environ, {}, clear=True)
    def test_load_from_env_missing_api_key(self):
        """Test that missing API key raises error."""
        with self.assertRaises(AuthenticationError) as ctx:
            CoinbaseAuth.load_from_env()
        self.assertIn("COINBASE_API_KEY", str(ctx.exception))

    @patch.dict(os.environ, {"COINBASE_API_KEY": "test_key"}, clear=True)
    def test_load_from_env_missing_api_secret(self):
        """Test that missing API secret raises error."""
        with self.assertRaises(AuthenticationError) as ctx:
            CoinbaseAuth.load_from_env()
        self.assertIn("COINBASE_API_SECRET", str(ctx.exception))

    def test_sign_request_get(self):
        """Test signing a GET request."""
        auth = CoinbaseAuth(self.test_creds)

        with patch("time.time", return_value=1234567890):
            headers = auth.sign_request("GET", "/api/v3/brokerage/accounts")

        self.assertEqual(headers["CB-ACCESS-KEY"], "test_api_key_12345")
        self.assertEqual(headers["CB-ACCESS-TIMESTAMP"], "1234567890")
        self.assertIn("CB-ACCESS-SIGN", headers)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertNotIn("CB-ACCESS-PASSPHRASE", headers)

    def test_sign_request_post_with_body(self):
        """Test signing a POST request with body."""
        auth = CoinbaseAuth(self.test_creds)
        body = json.dumps({"size": "0.01", "price": "50000.00"})

        with patch("time.time", return_value=1234567890):
            headers = auth.sign_request("POST", "/api/v3/brokerage/orders", body)

        self.assertEqual(headers["CB-ACCESS-KEY"], "test_api_key_12345")
        self.assertEqual(headers["CB-ACCESS-TIMESTAMP"], "1234567890")
        self.assertIn("CB-ACCESS-SIGN", headers)

    def test_sign_request_with_passphrase(self):
        """Test signing request includes passphrase when present."""
        creds_with_pass = CoinbaseCredentials(
            api_key="test_api_key_12345",
            api_secret=base64.b64encode(b"test_secret_67890").decode("utf-8"),
            api_passphrase="test_passphrase",
        )
        auth = CoinbaseAuth(creds_with_pass)

        headers = auth.sign_request("GET", "/api/v3/brokerage/accounts")
        self.assertEqual(headers["CB-ACCESS-PASSPHRASE"], "test_passphrase")

    def test_generate_signature(self):
        """Test signature generation."""
        auth = CoinbaseAuth(self.test_creds)
        message = "1234567890GET/api/v3/brokerage/accounts"

        signature = auth._generate_signature(message)

        # Signature should be base64 encoded
        try:
            base64.b64decode(signature)
        except Exception:
            self.fail("Signature is not valid base64")

    @patch("requests.get")
    def test_validate_credentials_success(self, mock_get):
        """Test successful credential validation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        auth = CoinbaseAuth(self.test_creds)
        result = auth.validate_credentials()

        self.assertTrue(result)
        self.assertTrue(auth._validated)
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_validate_credentials_invalid(self, mock_get):
        """Test invalid credential validation."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        auth = CoinbaseAuth(self.test_creds)

        with self.assertRaises(AuthenticationError) as ctx:
            auth.validate_credentials()
        self.assertIn("Invalid API credentials", str(ctx.exception))

    @patch("requests.get")
    def test_validate_credentials_permission_error(self, mock_get):
        """Test credential validation with permission error."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        auth = CoinbaseAuth(self.test_creds)

        with self.assertRaises(PermissionError) as ctx:
            auth.validate_credentials()
        self.assertIn("lacks required permissions", str(ctx.exception))

    @patch("requests.get")
    def test_validate_credentials_caches_result(self, mock_get):
        """Test that successful validation is cached."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        auth = CoinbaseAuth(self.test_creds)

        # First call
        result1 = auth.validate_credentials()
        # Second call
        result2 = auth.validate_credentials()

        self.assertTrue(result1)
        self.assertTrue(result2)
        # Should only call API once due to caching
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_check_permissions_success(self, mock_get):
        """Test successful permission check."""
        # Mock validation response
        mock_validation = MagicMock()
        mock_validation.status_code = 200

        # Mock permission fetch response
        mock_permissions = MagicMock()
        mock_permissions.status_code = 200
        mock_permissions.json.return_value = {"data": {"scopes": ["view", "trade"]}}

        mock_get.side_effect = [mock_validation, mock_permissions]

        auth = CoinbaseAuth(self.test_creds)
        result = auth.check_permissions(["view", "trade"])

        self.assertTrue(result)
        self.assertEqual(auth._permissions, {"view", "trade"})

    @patch("requests.get")
    def test_check_permissions_missing(self, mock_get):
        """Test permission check with missing permissions."""
        # Mock validation response
        mock_validation = MagicMock()
        mock_validation.status_code = 200

        # Mock permission fetch response
        mock_permissions = MagicMock()
        mock_permissions.status_code = 200
        mock_permissions.json.return_value = {"data": {"scopes": ["view"]}}

        mock_get.side_effect = [mock_validation, mock_permissions]

        auth = CoinbaseAuth(self.test_creds)

        with self.assertRaises(PermissionError) as ctx:
            auth.check_permissions(["view", "trade", "transfer"])
        self.assertIn("trade", str(ctx.exception))
        self.assertIn("transfer", str(ctx.exception))

    @patch("requests.request")
    def test_make_authenticated_request_with_path(self, mock_request):
        """Test making authenticated request with path."""
        mock_response = MagicMock()
        mock_request.return_value = mock_response

        auth = CoinbaseAuth(self.test_creds)
        response = auth.make_authenticated_request("GET", "/accounts")

        self.assertEqual(response, mock_response)
        mock_request.assert_called_once()

        # Check that headers were added
        call_kwargs = mock_request.call_args[1]
        self.assertIn("headers", call_kwargs)
        self.assertIn("CB-ACCESS-KEY", call_kwargs["headers"])

    @patch("requests.request")
    def test_make_authenticated_request_with_full_url(self, mock_request):
        """Test making authenticated request with full URL."""
        mock_response = MagicMock()
        mock_request.return_value = mock_response

        auth = CoinbaseAuth(self.test_creds)
        response = auth.make_authenticated_request(
            "GET", "https://api.coinbase.com/api/v3/brokerage/accounts"
        )

        self.assertEqual(response, mock_response)
        mock_request.assert_called_once()

    @patch("requests.request")
    def test_make_authenticated_request_with_body(self, mock_request):
        """Test making authenticated request with body."""
        mock_response = MagicMock()
        mock_request.return_value = mock_response

        auth = CoinbaseAuth(self.test_creds)
        body = {"size": "0.01", "price": "50000.00"}
        response = auth.make_authenticated_request("POST", "/orders", body=body)

        self.assertEqual(response, mock_response)
        mock_request.assert_called_once()

        # Check that body was JSON-encoded
        call_kwargs = mock_request.call_args[1]
        self.assertIn("data", call_kwargs)
        self.assertEqual(call_kwargs["data"], json.dumps(body))


class TestHelperFunctions(TestCase):
    """Test helper functions."""

    @patch("src.auth.CoinbaseAuth.validate_credentials")
    @patch("src.auth.CoinbaseAuth.load_from_env")
    def test_get_authenticator_with_validation(self, mock_load, mock_validate):
        """Test get_authenticator with validation."""
        mock_creds = MagicMock()
        mock_load.return_value = mock_creds
        mock_validate.return_value = True

        auth = get_authenticator(validate=True)

        self.assertIsInstance(auth, CoinbaseAuth)
        mock_validate.assert_called_once()

    @patch("src.auth.CoinbaseAuth.validate_credentials")
    @patch("src.auth.CoinbaseAuth.load_from_env")
    def test_get_authenticator_without_validation(self, mock_load, mock_validate):
        """Test get_authenticator without validation."""
        mock_creds = MagicMock()
        mock_load.return_value = mock_creds

        auth = get_authenticator(validate=False)

        self.assertIsInstance(auth, CoinbaseAuth)
        mock_validate.assert_not_called()

    @patch("src.auth.get_authenticator")
    def test_test_connection_success(self, mock_get_auth):
        """Test successful connection test."""
        mock_auth = MagicMock()
        mock_get_auth.return_value = mock_auth

        # test_connection should return True; assert instead of returning a value
        result = auth_mod.test_connection()
        assert result is True
        mock_get_auth.assert_called_once_with(validate=True)

    @patch("src.auth.get_authenticator")
    @patch("builtins.print")
    def test_test_connection_failure(self, mock_print, mock_get_auth):
        """Test failed connection test."""
        mock_get_auth.side_effect = AuthenticationError("Test error")

        result = auth_mod.test_connection()

        self.assertFalse(result)
        mock_print.assert_called_once()
        self.assertIn("Test error", mock_print.call_args[0][0])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
