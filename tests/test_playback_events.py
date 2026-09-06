"""Tests for local playback polling and event handling."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from spotify_controller import SpotifyController
from tests.conftest import MockApp


class TestLocalPlaybackPolling:
    """Test local MPRIS/playerctl polling."""

    def test_poll_playerctl_success(self, mock_app: MockApp) -> None:
        """Test successful playerctl metadata polling."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                parts = [
                    'playing',
                    'spotify:track:123',
                    'Test Song',
                    'Test Artist',
                    'Test Album',
                    '180000000',  # 180 seconds in microseconds
                ]
                with patch.object(controller, '_run_playerctl', return_value=parts):
                    controller._poll_playerctl(0.0)
                    assert controller._available is True
                    assert controller._is_playing is True
                    assert controller._track_id == 'spotify:track:123'
                    assert controller._title == 'Test Song'
                    assert controller._duration_s == 180.0

    def test_poll_playerctl_paused(self, mock_app: MockApp) -> None:
        """Test polling shows paused state."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                parts = [
                    'paused',
                    'spotify:track:123',
                    'Test Song',
                    'Test Artist',
                    'Test Album',
                    '180000000',
                ]
                with patch.object(controller, '_run_playerctl', return_value=parts):
                    controller._poll_playerctl(0.0)
                    assert controller._available is True
                    assert controller._is_playing is False
                    assert controller._status == 'paused'

    def test_poll_playerctl_player_unavailable(self, mock_app: MockApp) -> None:
        """Test polling detects unavailable player."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                controller._available = True
                with patch.object(controller, '_run_playerctl', return_value=None):
                    controller._poll_playerctl(0.0)
                    assert controller._available is False
                    assert controller._is_playing is False

    def test_poll_playerctl_invalid_parts(self, mock_app: MockApp) -> None:
        """Test polling with invalid parts count."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                controller._available = True
                with patch.object(controller, '_run_playerctl', return_value=['playing']):
                    controller._poll_playerctl(0.0)
                    assert controller._available is False

    def test_poll_playerctl_track_change_detected(self, mock_app: MockApp) -> None:
        """Test polling detects track changes."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                controller._track_id = 'spotify:track:old'
                controller._title = 'Old Song'
                controller._artist = 'Old Artist'
                old_change_counter = controller._change_counter

                parts = [
                    'playing',
                    'spotify:track:new',
                    'New Song',
                    'New Artist',
                    'New Album',
                    '200000000',
                ]
                with patch.object(controller, '_run_playerctl', return_value=parts):
                    controller._poll_playerctl(0.0)
                    assert controller._track_id == 'spotify:track:new'
                    assert controller._title == 'New Song'
                    assert controller._change_counter > old_change_counter

    def test_poll_playerctl_stores_previous_track(self, mock_app: MockApp) -> None:
        """Test polling stores previous track info."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                controller._track_id = 'spotify:track:old'
                controller._title = 'Old Song'
                controller._artist = 'Old Artist'
                controller._album = 'Old Album'

                parts = [
                    'playing',
                    'spotify:track:new',
                    'New Song',
                    'New Artist',
                    'New Album',
                    '200000000',
                ]
                with patch.object(controller, '_run_playerctl', return_value=parts):
                    controller._poll_playerctl(0.0)
                    assert controller._previous_track_id == 'spotify:track:old'
                    assert controller._previous_title == 'Old Song'
                    assert controller._previous_artist == 'Old Artist'

    def test_poll_playerctl_duration_conversion(self, mock_app: MockApp) -> None:
        """Test duration is converted from microseconds to seconds."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                parts = [
                    'playing',
                    'spotify:track:123',
                    'Song',
                    'Artist',
                    'Album',
                    '3600000000',  # 1 hour in microseconds
                ]
                with patch.object(controller, '_run_playerctl', return_value=parts):
                    controller._poll_playerctl(0.0)
                    assert controller._duration_s == 3600.0

    def test_run_playerctl_success(self, mock_app: MockApp) -> None:
        """Test successful playerctl subprocess call."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0,
                        stdout='line1\tline2\tline3',
                    )
                    result = controller._run_playerctl('metadata', '--format', 'pattern')
                    assert result == ['line1', 'line2', 'line3']

    def test_run_playerctl_failure(self, mock_app: MockApp) -> None:
        """Test failed playerctl call."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = MagicMock(returncode=1, stdout='')
                    result = controller._run_playerctl('metadata')
                    assert result is None

    def test_run_playerctl_timeout(self, mock_app: MockApp) -> None:
        """Test playerctl timeout."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                with patch('subprocess.run', side_effect=TimeoutError):
                    result = controller._run_playerctl('metadata')
                    assert result is None

    def test_poll_playerctl_no_playerctl_installed(self, mock_app: MockApp) -> None:
        """Test _run_playerctl returns None when playerctl not available."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value=None):
                controller = SpotifyController(mock_app, {'enabled': True})
                # Force disable the early check
                controller._playerctl = None
                result = controller._run_playerctl('metadata')
                assert result is None


class TestUpdateCycle:
    """Test update/polling cycle."""

    def test_update_disabled_does_nothing(self, mock_app: MockApp) -> None:
        """Test update does nothing when disabled."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            with patch.object(controller, '_update_local') as mock_local:
                with patch.object(controller, '_update_web_api') as mock_web:
                    controller.update(0.016, MagicMock())
                    mock_local.assert_not_called()
                    mock_web.assert_not_called()

    def test_update_calls_local_when_enabled(self, mock_app: MockApp) -> None:
        """Test update calls local polling when enabled."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True})
                with patch.object(controller, '_update_local') as mock_local:
                    with patch.object(controller, '_poll_playerctl'):
                        controller.update(0.016, MagicMock())
                        mock_local.assert_called_once()

    def test_update_calls_web_api_when_enabled(self, mock_app: MockApp) -> None:
        """Test update calls web API polling when enabled."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            with patch.object(controller, '_update_web_api') as mock_web:
                controller.update(0.016, MagicMock())
                mock_web.assert_called_once()

    def test_update_respects_poll_interval(self, mock_app: MockApp) -> None:
        """Test update respects poll interval."""
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, {'enabled': True, 'poll_interval_s': 1.0})
                with patch('time.monotonic') as mock_time:
                    # Set initial poll time to -1000 to trigger first poll
                    controller._last_poll_t = 0.0
                    mock_time.return_value = 0.1  # Only 0.1s elapsed, < 1.0s interval
                    with patch.object(controller, '_poll_playerctl') as mock_poll:
                        controller.update(0.016, MagicMock())
                        mock_poll.assert_not_called()


class TestKeyHandling:
    """Test keyboard input handling."""

    def test_handle_key_ctrl_alt_s_auth(self, mock_app: MockApp) -> None:
        """Test Ctrl+Alt+S triggers auth."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            with patch('sdl2.KMOD_CTRL', 2):
                with patch('sdl2.KMOD_ALT', 256):
                    with patch('sdl2.KMOD_SHIFT', 1):
                        with patch('sdl2.SDLK_s', 115):
                            with patch.object(controller, 'begin_auth_async') as mock_auth:
                                mock_auth.return_value = 'started'
                                result = controller.handle_key(115, 2 | 256)
                                assert result == 'started'

    def test_handle_key_ctrl_alt_shift_s_logout(self, mock_app: MockApp) -> None:
        """Test Ctrl+Alt+Shift+S triggers logout."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            with patch('sdl2.KMOD_CTRL', 2):
                with patch('sdl2.KMOD_ALT', 256):
                    with patch('sdl2.KMOD_SHIFT', 1):
                        with patch('sdl2.SDLK_s', 115):
                            with patch.object(controller, 'logout') as mock_logout:
                                mock_logout.return_value = 'logged out'
                                result = controller.handle_key(115, 2 | 256 | 1)
                                assert result == 'logged out'

    def test_handle_key_other_key_returns_false(self, mock_app: MockApp) -> None:
        """Test unrelated key returns False."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            result = controller.handle_key(ord('A'), 0)
            assert result is False

    def test_handle_key_ctrl_alt_d_returns_false(self, mock_app: MockApp) -> None:
        """Test different key with Ctrl+Alt returns False."""
        with patch('sys.platform', 'linux'):
            with patch('sdl2.KMOD_CTRL', 2):
                with patch('sdl2.KMOD_ALT', 256):
                    with patch('sdl2.SDLK_d', 100):
                        controller = SpotifyController(mock_app, {})
                        result = controller.handle_key(100, 2 | 256)
                        assert result is False


class TestShutdown:
    """Test shutdown handling."""

    def test_shutdown_noop(self, mock_app: MockApp) -> None:
        """Test shutdown is a no-op."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            # Should not raise
            controller.shutdown()
