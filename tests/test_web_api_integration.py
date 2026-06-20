"""Tests for Spotify Web API integration."""
from __future__ import annotations

import json
import sys
import urllib.error
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from spotify_controller import SpotifyController
from tests.conftest import MockApp


class TestWebAPIPolling:
    """Test web API polling."""

    def test_api_get_success(self, mock_app: MockApp) -> None:
        """Test successful API GET request."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = True
            controller._token = {'access_token': 'test_token'}

            response_data = {'id': 'track123', 'name': 'Test Track'}
            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(response_data).encode()
                mock_urlopen.return_value.__enter__.return_value = mock_response

                result = controller._api_get('/me/player')
                assert result == response_data

    def test_api_get_without_auth(self, mock_app: MockApp) -> None:
        """Test API GET without auth returns None."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = False
            result = controller._api_get('/me/player')
            assert result is None

    def test_api_get_http_error(self, mock_app: MockApp) -> None:
        """Test API GET with HTTP error."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = True
            controller._token = {'access_token': 'test_token'}

            with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('', 401, 'Unauthorized', {}, None)):
                result = controller._api_get('/me/player')
                assert result is None
                assert 'api_get_failed' in controller._last_error

    def test_api_get_with_query_params(self, mock_app: MockApp) -> None:
        """Test API GET with query parameters."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = True
            controller._token = {'access_token': 'test_token'}

            response_data = {'id': 'pl123', 'name': 'Playlist'}
            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(response_data).encode()
                mock_urlopen.return_value.__enter__.return_value = mock_response

                result = controller._api_get('/playlists/123', query={'fields': 'id,name'})
                assert result == response_data
                # Verify URL was constructed with query params
                call_args = mock_urlopen.call_args
                request = call_args[0][0]
                # Request.full_url has the query string
                assert 'fields=' in str(request.full_url)


class TestTokenRefresh:
    """Test token refresh flow."""

    def test_exchange_code_for_token_success(self, mock_app: MockApp) -> None:
        """Test successful code-to-token exchange."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client',
                'redirect_uri': 'http://127.0.0.1:43879/callback',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._code_verifier = 'test_verifier_' * 4

            response_data = {
                'access_token': 'new_token',
                'token_type': 'Bearer',
                'expires_in': 3600,
                'refresh_token': 'refresh_token',
            }

            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(response_data).encode()
                mock_urlopen.return_value.__enter__.return_value = mock_response

                with patch.object(controller, '_save_token_store'):
                    result = controller._exchange_code_for_token('auth_code')
                    assert result is True
                    assert controller._auth_ready is True
                    assert controller._token['access_token'] == 'new_token'

    def test_refresh_access_token_success(self, mock_app: MockApp) -> None:
        """Test successful token refresh."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._token = {'refresh_token': 'old_refresh_token'}

            response_data = {
                'access_token': 'new_token',
                'token_type': 'Bearer',
                'expires_in': 3600,
            }

            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(response_data).encode()
                mock_urlopen.return_value.__enter__.return_value = mock_response

                with patch.object(controller, '_save_token_store'):
                    result = controller._refresh_access_token()
                    assert result is True
                    assert controller._token['access_token'] == 'new_token'

    def test_refresh_access_token_failure(self, mock_app: MockApp) -> None:
        """Test token refresh failure."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._token = {'refresh_token': 'old_refresh_token'}

            with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('', 400, 'Bad Request', {}, None)):
                result = controller._refresh_access_token()
                assert result is False
                assert 'refresh_failed' in controller._auth_status


class TestRefreshRemoteState:
    """Test remote state refresh."""

    def test_refresh_remote_state_playback(
        self, mock_app: MockApp, sample_playback_payload: dict[str, Any]
    ) -> None:
        """Test playback state refresh."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = True
            controller._token = {'access_token': 'test'}
            controller._token_expires_at = time.time() + 3600

            with patch.object(controller, '_api_get', return_value=sample_playback_payload):
                controller._refresh_remote_state(do_queue=False, do_playlist_context=False)
                assert controller._playback == sample_playback_payload

    def test_refresh_remote_state_with_queue(
        self,
        mock_app: MockApp,
        sample_playback_payload: dict[str, Any],
        sample_queue_payload: dict[str, Any],
    ) -> None:
        """Test playback and queue refresh."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
                'resolve_queue': True,
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = True
            controller._token = {'access_token': 'test', 'expires_at': time.time() + 3600}

            def mock_api_get(path: str, **kwargs: Any) -> dict[str, Any] | None:  # noqa: ARG001
                if 'queue' in path:
                    return sample_queue_payload
                return sample_playback_payload

            with patch.object(controller, '_api_get', side_effect=mock_api_get):
                controller._refresh_remote_state(do_queue=True, do_playlist_context=False)
                assert controller._playback == sample_playback_payload
                assert len(controller._queue) == 2

    def test_refresh_remote_state_with_playlist_context(
        self,
        mock_app: MockApp,
        sample_playback_payload: dict[str, Any],
        sample_playlist_payload: dict[str, Any],
    ) -> None:
        """Test playback and playlist context refresh."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
                'resolve_playlist_context': True,
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = True
            controller._token = {'access_token': 'test'}

            def mock_api_get(path: str, **kwargs: Any) -> dict[str, Any] | None:  # noqa: ARG001
                if 'playlists' in path:
                    return sample_playlist_payload
                return sample_playback_payload

            with patch.object(controller, '_api_get', side_effect=mock_api_get):
                controller._refresh_remote_state(do_queue=False, do_playlist_context=True)
                assert controller._playlist_context is not None
                assert controller._playlist_context['id'] == 'pl123'

    def test_refresh_remote_state_no_playback(self, mock_app: MockApp) -> None:
        """Test refresh when no playback available."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._auth_ready = True
            controller._token = {'access_token': 'test'}

            with patch.object(controller, '_api_get', return_value=None):
                controller._refresh_remote_state(do_queue=False, do_playlist_context=False)
                assert controller._playback is None


class TestPollWorker:
    """Test background poll worker thread."""

    def test_poll_worker_auth_check(self, mock_app: MockApp) -> None:
        """Test poll worker checks auth status."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': '',  # Missing client ID
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            with patch.object(controller, '_load_token_store'):
                controller._poll_worker(do_queue=False, do_playlist_context=False)
                assert controller._auth_status == 'missing_client_id'
                assert controller._web_poll_inflight is False

    def test_poll_worker_refresh_state(self, mock_app: MockApp) -> None:
        """Test poll worker refreshes state."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            # _poll_worker checks if client_id, auth_ready, and token not expired
            # Set up all preconditions
            controller._client_id = 'test'
            controller._auth_ready = True
            controller._token = {'access_token': 'test'}
            controller._token_expires_at = time.time() + 3600  # Not expired

            with patch.object(controller, '_refresh_remote_state') as mock_refresh:
                # Call should proceed without error
                controller._poll_worker(do_queue=True, do_playlist_context=True)
                mock_refresh.assert_called_once()

    def test_poll_worker_clears_inflight_flag(self, mock_app: MockApp) -> None:
        """Test poll worker clears inflight flag on completion."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._web_poll_inflight = True
            controller._auth_ready = True
            controller._token = {'access_token': 'test'}

            with patch.object(controller, '_refresh_remote_state'):
                controller._poll_worker(do_queue=False, do_playlist_context=False)
                assert controller._web_poll_inflight is False


class TestErrorHandling:
    """Test error handling and recovery."""

    def test_last_error_tracking(self, mock_app: MockApp) -> None:
        """Test last error is tracked."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            assert controller._last_error == ''
            controller._last_error = 'test_error'
            assert controller._last_error == 'test_error'

    def test_error_in_snapshot(self, mock_app: MockApp) -> None:
        """Test last error is included in snapshot."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            controller._last_error = 'api_error'
            snapshot = controller.snapshot()
            assert snapshot['last_error'] == 'api_error'

    def test_auth_status_error_states(self, mock_app: MockApp, tmp_path: Path) -> None:
        """Test various auth error states."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
                'token_store': str(tmp_path / 'nonexistent-token.json'),
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            # When web_api is enabled but no token loaded yet, auth_status is 'needs_auth'
            assert controller._auth_status == 'needs_auth'

            controller._auth_status = 'missing_client_id'
            snapshot = controller.snapshot()
            assert snapshot['auth_status'] == 'missing_client_id'
            assert snapshot['needs_auth'] is True
