"""Tests for Spotify PKCE authentication and token management."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from spotify_controller import SpotifyController
from tests.conftest import MockApp


class TestPKCEMethods:
    """Test PKCE helper methods."""

    def test_pkce_verifier_length(self, mock_app: MockApp) -> None:
        """Test PKCE verifier is correct length."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            verifier = controller._pkce_verifier()
            # PKCE verifier should be 43-128 characters
            assert 43 <= len(verifier) <= 128  # nosec B101

    def test_pkce_verifier_uniqueness(self, mock_app: MockApp) -> None:
        """Test multiple PKCE verifiers are unique."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            verifiers = {controller._pkce_verifier() for _ in range(10)}
            assert len(verifiers) == 10  # nosec B101

    def test_pkce_challenge_from_verifier(self, mock_app: MockApp) -> None:
        """Test PKCE challenge is generated from verifier."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            verifier = controller._pkce_verifier()
            challenge = controller._pkce_challenge(verifier)
            # Challenge should be base64url encoded
            assert len(challenge) > 0  # nosec B101
            assert all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=' for c in challenge)  # nosec B101

    def test_pkce_challenge_deterministic(self, mock_app: MockApp) -> None:
        """Test same verifier produces same challenge."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            verifier = 'test_verifier_content_here_' * 2
            challenge1 = controller._pkce_challenge(verifier)
            challenge2 = controller._pkce_challenge(verifier)
            assert challenge1 == challenge2  # nosec B101


class TestBuildAuthUrl:
    """Test build_auth_url method."""

    def test_build_auth_url_web_disabled(self, mock_app: MockApp) -> None:
        """Test returns None when web API is disabled."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            url = controller.build_auth_url()
            assert url is None  # nosec B101
            assert controller._auth_status == 'missing_client_id'  # nosec B101

    def test_build_auth_url_missing_client_id(self, mock_app: MockApp) -> None:
        """Test returns None when client ID is missing."""
        cfg = {'web_api': {'enabled': True}}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            url = controller.build_auth_url()
            assert url is None  # nosec B101
            assert controller._auth_status == 'missing_client_id'  # nosec B101

    def test_build_auth_url_valid(self, mock_app: MockApp) -> None:
        """Test valid auth URL construction."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
                'scopes': ['user-read-playback-state'],
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            url = controller.build_auth_url()
            assert url is not None  # nosec B101
            assert 'accounts.spotify.com/authorize' in url  # nosec B101
            assert 'client_id=test_client_id' in url  # nosec B101
            assert 'code_challenge_method=S256' in url  # nosec B101
            assert controller._auth_status == 'awaiting_user_auth'  # nosec B101

    def test_build_auth_url_includes_redirect_uri(self, mock_app: MockApp) -> None:
        """Test auth URL includes redirect URI."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
                'redirect_uri': 'http://127.0.0.1:43879/callback',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            url = controller.build_auth_url()
            assert 'redirect_uri=http' in url  # nosec B101

    def test_build_auth_url_sets_auth_state(self, mock_app: MockApp) -> None:
        """Test auth URL generation sets auth state."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert controller._auth_state == ''  # nosec B101
            controller.build_auth_url()
            assert controller._auth_state != ''  # nosec B101

    def test_build_auth_url_sets_code_verifier(self, mock_app: MockApp) -> None:
        """Test auth URL generation sets code verifier."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert controller._code_verifier == ''  # nosec B101
            controller.build_auth_url()
            assert controller._code_verifier != ''  # nosec B101


class TestTokenManagement:
    """Test token storage and refresh."""

    def test_load_token_store_no_file(self, mock_app: MockApp, temp_token_file: Path) -> None:
        """Test loading token store when file doesn't exist."""
        temp_token_file.unlink()  # Remove the file
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
                'token_store': str(temp_token_file),
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._load_token_store()
            assert controller._auth_ready is False  # nosec B101

    def test_load_token_store_valid_token(
        self, mock_app: MockApp, temp_token_file: Path, sample_token_payload: dict[str, Any]
    ) -> None:
        """Test loading valid token from file."""
        temp_token_file.write_text(json.dumps(sample_token_payload))
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
                'token_store': str(temp_token_file),
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            # Mock time to ensure token is valid
            with patch('time.time', return_value=1000):
                controller._load_token_store()
                # Token should be loaded
                assert controller._token.get('access_token') == sample_token_payload['access_token']  # nosec B101

    def test_token_expired_check(self, mock_app: MockApp) -> None:
        """Test token expiry check."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            # Token not expired
            controller._token_expires_at = time.time() + 3600
            assert controller._token_expired() is False  # nosec B101
            # Token expired
            controller._token_expires_at = time.time() - 1
            assert controller._token_expired() is True  # nosec B101
    def test_persist_token_store(self, mock_app: MockApp, temp_token_file: Path, sample_token_payload: dict[str, Any]) -> None:
        """Test token is persisted to file."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
                'token_store': str(temp_token_file),
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._token = sample_token_payload
            controller._save_token_store()
            # Verify file was written
            assert temp_token_file.exists()  # nosec B101
            saved = json.loads(temp_token_file.read_text())
            assert saved['access_token'] == sample_token_payload['access_token']  # nosec B101

    def test_persist_token_store_creates_directory(self, mock_app: MockApp, tmp_path: Path) -> None:
        """Test token storage creates parent directory if needed."""
        token_file = tmp_path / 'subdir' / 'token.json'
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
                'token_store': str(token_file),
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._token = {'access_token': token_file.stem}
            controller._save_token_store()
            assert token_file.exists()  # nosec B101


class TestBeginAuth:
    """Test authentication flow."""

    def test_begin_auth_async_disabled(self, mock_app: MockApp) -> None:
        """Test async auth fails when web API disabled."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            result = controller.begin_auth_async()
            assert 'disabled' in result.lower()  # nosec B101

    def test_begin_auth_async_no_client_id(self, mock_app: MockApp) -> None:
        """Test async auth fails without client ID."""
        cfg = {'web_api': {'enabled': True}}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            result = controller.begin_auth_async()
            assert 'client id' in result.lower()  # nosec B101

    def test_begin_auth_async_in_progress(self, mock_app: MockApp) -> None:
        """Test async auth fails if already in progress."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            # Mock a thread that's alive
            controller._auth_thread = MagicMock()
            controller._auth_thread.is_alive.return_value = True
            result = controller.begin_auth_async()
            assert 'already in progress' in result.lower()  # nosec B101

    def test_begin_auth_async_starts_thread(self, mock_app: MockApp) -> None:
        """Test async auth starts background thread."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            with patch.object(controller, 'begin_auth', return_value=False):
                result = controller.begin_auth_async(timeout_s=1.0)
                assert 'started' in result.lower()  # nosec B101
                assert controller._auth_thread is not None  # nosec B101


class TestLogout:
    """Test logout flow."""

    def test_logout_clears_state(self, mock_app: MockApp, tmp_path: Path) -> None:
        """Test logout clears all auth state."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
                'token_store': str(tmp_path / 'test_token.json'),
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = True
            controller._token = {'access_token': cfg['web_api']['client_id']}
            controller._queue = [{'id': 'track1'}]
            controller._playlist_context = {'name': 'Playlist'}

            with patch.object(controller, '_token_store', MagicMock(exists=lambda: True)):
                controller._token_store.unlink = MagicMock()
                result = controller.logout()

            assert controller._auth_ready is False  # nosec B101
            assert controller._token == {}  # nosec B101
            assert controller._queue == []  # nosec B101
            assert controller._playlist_context is None  # nosec B101
            assert 'logged out' in result.lower()  # nosec B101

    def test_logout_without_token_file(self, mock_app: MockApp, tmp_path: Path) -> None:
        """Test logout succeeds even if token file doesn't exist."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
                'token_store': str(tmp_path / 'nonexistent_token.json'),
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            result = controller.logout()
            assert 'cleared' in result.lower() or 'logged out' in result.lower()  # nosec B101
