"""Tests for Spotify snapshot generation and corpus path resolution."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from spotify_controller import SpotifyController
from tests.conftest import MockApp


class TestSnapshot:
    """Test snapshot generation."""

    def test_snapshot_basic_structure(self, mock_app: MockApp) -> None:
        """Test snapshot includes all required fields."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            snapshot = controller.snapshot()
            assert 'available' in snapshot  # nosec B101
            assert 'is_playing' in snapshot  # nosec B101
            assert 'status' in snapshot  # nosec B101
            assert 'track_id' in snapshot  # nosec B101
            assert 'title' in snapshot  # nosec B101
            assert 'artist' in snapshot  # nosec B101
            assert 'duration_s' in snapshot  # nosec B101
            assert 'position_s' in snapshot  # nosec B101
            assert 'change_counter' in snapshot  # nosec B101

    def test_snapshot_with_no_playback(self, mock_app: MockApp) -> None:
        """Test snapshot with no active playback."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            snapshot = controller.snapshot()
            assert snapshot['available'] is False  # nosec B101
            assert snapshot['is_playing'] is False  # nosec B101
            assert snapshot['track_id'] == ''  # nosec B101
            assert snapshot['status'] == 'stopped'  # nosec B101

    def test_snapshot_with_playing_track(self, mock_app: MockApp) -> None:
        """Test snapshot with active track."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            controller._available = True
            controller._is_playing = True
            controller._status = 'playing'
            controller._track_id = 'spotify:track:123'
            controller._title = 'Test Song'
            controller._artist = 'Test Artist'
            controller._album = 'Test Album'
            controller._duration_s = 180.0
            controller._position_s = 90.0

            snapshot = controller.snapshot()
            assert snapshot['available'] is True  # nosec B101
            assert snapshot['is_playing'] is True  # nosec B101
            assert snapshot['track_id'] == 'spotify:track:123'  # nosec B101
            assert snapshot['title'] == 'Test Song'  # nosec B101
            assert snapshot['artist'] == 'Test Artist'  # nosec B101
            assert snapshot['duration_s'] == 180.0  # nosec B101
            assert snapshot['position_s'] == 90.0  # nosec B101
            assert snapshot['progress'] == 0.5  # nosec B101

    def test_snapshot_progress_calculation(self, mock_app: MockApp) -> None:
        """Test progress is correctly calculated."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            controller._duration_s = 100.0
            controller._position_s = 50.0
            snapshot = controller.snapshot()
            assert snapshot['progress'] == 0.5  # nosec B101

    def test_snapshot_progress_zero_duration(self, mock_app: MockApp) -> None:
        """Test progress with zero duration."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            controller._duration_s = 0.0
            controller._position_s = 50.0
            snapshot = controller.snapshot()
            assert snapshot['progress'] == 0.0  # nosec B101

    def test_snapshot_progress_clamped(self, mock_app: MockApp) -> None:
        """Test progress is clamped to [0, 1]."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            controller._duration_s = 100.0
            controller._position_s = 150.0  # Beyond duration
            snapshot = controller.snapshot()
            assert snapshot['progress'] == 1.0  # nosec B101

    def test_snapshot_source_local_only(self, mock_app: MockApp) -> None:
        """Test source is 'playerctl' when only local enabled."""
        cfg = {'enabled': True, 'web_api': {'enabled': False}}
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, cfg)
                snapshot = controller.snapshot()
                assert snapshot['source'] == 'playerctl'  # nosec B101

    def test_snapshot_source_webapi_only(self, mock_app: MockApp) -> None:
        """Test source is 'webapi' when only web API enabled."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            snapshot = controller.snapshot()
            assert snapshot['source'] == 'webapi'  # nosec B101

    def test_snapshot_source_both(self, mock_app: MockApp) -> None:
        """Test source is 'playerctl+webapi' when both enabled."""
        cfg = {
            'enabled': True,
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            with patch('shutil.which', return_value='/usr/bin/playerctl'):
                controller = SpotifyController(mock_app, cfg)
                snapshot = controller.snapshot()
                assert snapshot['source'] == 'playerctl+webapi'  # nosec B101

    def test_snapshot_auth_status_fields(self, mock_app: MockApp) -> None:
        """Test auth status fields in snapshot."""
        cfg = {
            'web_api': {
                'enabled': True,
                'client_id': 'test',
            }
        }
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            snapshot = controller.snapshot()
            assert 'auth_ready' in snapshot  # nosec B101
            assert 'auth_status' in snapshot  # nosec B101
            assert 'needs_auth' in snapshot  # nosec B101

    def test_snapshot_previous_track_tracking(self, mock_app: MockApp) -> None:
        """Test snapshot includes previous track info."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            controller._previous_track_id = 'spotify:track:old'
            controller._previous_title = 'Old Song'
            controller._previous_artist = 'Old Artist'
            controller._previous_album = 'Old Album'

            snapshot = controller.snapshot()
            assert snapshot['previous_track_id'] == 'spotify:track:old'  # nosec B101
            assert snapshot['previous_title'] == 'Old Song'  # nosec B101
            assert snapshot['previous_artist'] == 'Old Artist'  # nosec B101

    def test_snapshot_change_counter(self, mock_app: MockApp) -> None:
        """Test change counter is tracked."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            assert controller.snapshot()['change_counter'] == 0  # nosec B101
            controller._change_counter = 5
            assert controller.snapshot()['change_counter'] == 5  # nosec B101


class TestResolveCorpusPath:
    """Test _resolve_features_path (used for live_corpus_file path resolution)."""

    def test_resolve_features_path_none(self, mock_app: MockApp) -> None:
        """Test path resolution with None."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            result = controller._resolve_features_path(None)
            assert result is None  # nosec B101

    def test_resolve_features_path_empty_string(self, mock_app: MockApp) -> None:
        """Test path resolution with empty string."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            result = controller._resolve_features_path('')
            assert result is None  # nosec B101

    def test_resolve_features_path_absolute(self, mock_app: MockApp, tmp_path: Path) -> None:
        """Test absolute path is preserved."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            abs_path = tmp_path / 'corpus.jsonl'
            result = controller._resolve_features_path(str(abs_path))
            assert result == abs_path  # nosec B101

    def test_resolve_features_path_relative(self, mock_app: MockApp) -> None:
        """Test relative path is resolved to project root."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            with patch('pathlib.Path.resolve'):
                result = controller._resolve_features_path('corpus/live.jsonl')
                assert result is not None  # nosec B101
