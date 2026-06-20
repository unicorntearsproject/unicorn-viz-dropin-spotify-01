"""Tests for SpotifyController initialization and configuration."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from spotify_controller import SpotifyController
from tests.conftest import MockApp


class TestInitialization:
    """Test SpotifyController initialization."""

    def test_init_with_no_config(self, mock_app: MockApp) -> None:
        """Test initialization with no config."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value=None):
                controller = SpotifyController(mock_app, {})
                assert controller._app is mock_app
                assert controller._cfg == {}
                assert controller.enabled is False
                assert controller._local_enabled is False
                assert controller._web_enabled is False

    def test_init_with_local_config_enabled(self, mock_app: MockApp) -> None:
        """Test initialization with local Spotify enabled."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                cfg = {'enabled': True}
                controller = SpotifyController(mock_app, cfg)
                assert controller._local_enabled is True
                assert controller.enabled is True

    def test_init_with_web_config_enabled(self, mock_app: MockApp) -> None:
        """Test initialization with web API enabled."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert controller._web_enabled is True
            assert controller.enabled is True
            assert controller._client_id == 'test_client_id'

    def test_init_with_both_local_and_web(self, mock_app: MockApp) -> None:
        """Test initialization with both local and web API enabled."""
        cfg = {
            'enabled': True,
            'web_api': {
                'enabled': True,
                'client_id': 'test_client_id',
            }
        }
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, cfg)
                assert controller._local_enabled is True
                assert controller._web_enabled is True
                assert controller.enabled is True

    def test_init_windows_warns_on_local(self, mock_app: MockApp) -> None:
        """Test that Windows platform gets warning for local mode."""
        cfg = {'enabled': True}
        with patch('sys.platform', 'win32'):
            with patch('shutil.which', return_value='playerctl.exe'):
                controller = SpotifyController(mock_app, cfg)
                # Windows logs warning but doesn't disable if playerctl is found
                assert controller._local_enabled is True

    def test_init_playerctl_not_found(self, mock_app: MockApp) -> None:
        """Test initialization when playerctl is not available."""
        cfg = {'enabled': True}
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value=None):
                controller = SpotifyController(mock_app, cfg)
                assert controller._local_enabled is False

    def test_init_poll_interval_validation(self, mock_app: MockApp) -> None:
        """Test that poll intervals are clamped to minimum values."""
        cfg = {'poll_interval_s': 0.01}  # Too low
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert controller._poll_interval_s >= 0.15

    def test_init_command_timeout_validation(self, mock_app: MockApp) -> None:
        """Test that command timeout is clamped to minimum values."""
        cfg = {'command_timeout_s': 0.01}  # Too low
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert controller._command_timeout_s >= 0.05

    def test_init_custom_player_name(self, mock_app: MockApp) -> None:
        """Test initialization with custom player name."""
        cfg = {'enabled': True, 'player': 'mpv'}
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, cfg)
                assert controller._player == 'mpv'

    def test_init_scopes_from_config(self, mock_app: MockApp) -> None:
        """Test that scopes are parsed correctly from config."""
        scopes = ['user-read-playback-state', 'user-read-currently-playing']
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
                'scopes': scopes,
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert controller._scopes == scopes

    def test_init_scopes_from_space_separated_string(self, mock_app: MockApp) -> None:
        """Test that space-separated scopes string is parsed."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
                'scopes': 'user-read-playback-state user-read-currently-playing',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert len(controller._scopes) == 2
            assert 'user-read-playback-state' in controller._scopes

    def test_init_default_scopes(self, mock_app: MockApp) -> None:
        """Test that default scopes are set if none provided."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert len(controller._scopes) > 0
            assert 'user-read-playback-state' in controller._scopes

    def test_init_missing_client_id_sets_status(self, mock_app: MockApp) -> None:
        """Test that missing client ID sets auth status."""
        cfg = {
            'web_api': {
                'enabled': True,
            }
        }
        with patch.dict(os.environ, {}, clear=False):
            with patch('sys.platform', 'linux'):
                controller = SpotifyController(mock_app, cfg)
                assert controller._auth_status == 'missing_client_id'

    def test_init_client_id_from_env(self, mock_app: MockApp) -> None:
        """Test that client ID can be loaded from environment."""
        cfg = {'web_api': {'enabled': True}}
        with patch.dict(os.environ, {'UNICORNVIZ_SPOTIFY_CLIENT_ID': 'env_client_id'}):
            with patch('sys.platform', 'linux'):
                controller = SpotifyController(mock_app, cfg)
                assert controller._client_id == 'env_client_id'

    def test_init_now_playing_banner_defaults(self, mock_app: MockApp) -> None:
        """Test now playing banner configuration."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            assert controller._now_playing_banner_enabled is True
            assert controller._now_playing_banner_hold_s >= 1.0

    def test_init_now_playing_banner_custom(self, mock_app: MockApp) -> None:
        """Test custom now playing banner settings."""
        cfg = {
            'now_playing_banner': False,
            'now_playing_banner_hold_s': 5.0,
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert controller._now_playing_banner_enabled is False
            assert controller._now_playing_banner_hold_s == 5.0


class TestStateInitialization:
    """Test initial state of SpotifyController."""

    def test_initial_metadata_state(self, mock_app: MockApp) -> None:
        """Test that metadata is initialized to empty/zero state."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            assert controller._track_id == ''
            assert controller._title == ''
            assert controller._artist == ''
            assert controller._album == ''
            assert controller._position_s == 0.0
            assert controller._duration_s == 0.0
            assert controller._is_playing is False
            assert controller._available is False

    def test_initial_web_api_state(self, mock_app: MockApp, tmp_path: Path) -> None:
        """Test that web API state is initialized correctly."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
                'token_store': str(tmp_path / 'nonexistent-token.json'),
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            assert controller._playback is None
            assert controller._queue == []
            assert controller._playlist_context is None
            assert controller._token == {}
            assert controller._auth_ready is False

    def test_initial_change_counter(self, mock_app: MockApp) -> None:
        """Test that change counter starts at zero."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            assert controller._change_counter == 0
