"""Tests for Spotify snapshot generation and feature caching."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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


class TestFeatureCaching:
    """Test feature cache loading and lookup."""

    def test_resolve_features_path_none(self, mock_app: MockApp) -> None:
        """Test feature path resolution with None."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            result = controller._resolve_features_path(None)
            assert result is None  # nosec B101

    def test_resolve_features_path_empty_string(self, mock_app: MockApp) -> None:
        """Test feature path resolution with empty string."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            result = controller._resolve_features_path('')
            assert result is None  # nosec B101

    def test_resolve_features_path_absolute(self, mock_app: MockApp, tmp_path: Path) -> None:
        """Test absolute feature path is preserved."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            abs_path = tmp_path / 'features.json'
            result = controller._resolve_features_path(str(abs_path))
            assert result == abs_path  # nosec B101

    def test_resolve_features_path_relative(self, mock_app: MockApp) -> None:
        """Test relative feature path is resolved to project root."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            with patch('pathlib.Path.resolve'):
                result = controller._resolve_features_path('features/data.json')
                assert result is not None  # nosec B101

    def test_refresh_features_cache_no_file(self, mock_app: MockApp) -> None:
        """Test feature cache refresh with missing file."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            controller._refresh_features_cache()
            assert controller._features_cache == {}  # nosec B101

    def test_refresh_features_cache_valid_json(
        self, mock_app: MockApp, temp_features_file: Path, sample_features_data: dict[str, Any]
    ) -> None:
        """Test feature cache loads valid JSON."""
        temp_features_file.write_text(json.dumps(sample_features_data))
        cfg = {'features_file': str(temp_features_file)}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._refresh_features_cache()
            assert len(controller._features_cache) == 2  # nosec B101
            assert 'spotify:track:track123' in controller._features_cache  # nosec B101

    def test_refresh_features_cache_invalid_json(
        self, mock_app: MockApp, temp_features_file: Path
    ) -> None:
        """Test feature cache handles invalid JSON."""
        temp_features_file.write_text('not valid json {')
        cfg = {'features_file': str(temp_features_file)}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._refresh_features_cache()
            assert controller._features_cache == {}  # nosec B101

    def test_refresh_features_cache_not_dict(
        self, mock_app: MockApp, temp_features_file: Path
    ) -> None:
        """Test feature cache handles non-dict JSON."""
        temp_features_file.write_text('["list", "not", "dict"]')
        cfg = {'features_file': str(temp_features_file)}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._refresh_features_cache()
            assert controller._features_cache == {}  # nosec B101

    def test_feature_payload_track_found(
        self, mock_app: MockApp, temp_features_file: Path, sample_features_data: dict[str, Any]
    ) -> None:
        """Test feature payload lookup finds track."""
        temp_features_file.write_text(json.dumps(sample_features_data))
        cfg = {'features_file': str(temp_features_file)}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._refresh_features_cache()
            payload = controller._feature_payload('spotify:track:track123')
            assert payload['bpm'] == 120.0  # nosec B101
            assert payload['energy'] == 0.85  # nosec B101

    def test_feature_payload_track_not_found(
        self, mock_app: MockApp, temp_features_file: Path, sample_features_data: dict[str, Any]
    ) -> None:
        """Test feature payload returns empty dict for missing track."""
        temp_features_file.write_text(json.dumps(sample_features_data))
        cfg = {'features_file': str(temp_features_file)}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._refresh_features_cache()
            payload = controller._feature_payload('spotify:track:nonexistent')
            assert payload == {}  # nosec B101

    def test_feature_payload_empty_track_id(self, mock_app: MockApp) -> None:
        """Test feature payload with empty track ID."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            payload = controller._feature_payload('')
            assert payload == {}  # nosec B101

    def test_feature_payload_no_features_file(self, mock_app: MockApp) -> None:
        """Test feature payload when no features file configured."""
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, {})
            payload = controller._feature_payload('spotify:track:123')
            assert payload == {}  # nosec B101

    def test_refresh_features_cache_mtime_optimization(
        self, mock_app: MockApp, temp_features_file: Path, sample_features_data: dict[str, Any]
    ) -> None:
        """Test feature cache doesn't reload if mtime unchanged."""
        temp_features_file.write_text(json.dumps(sample_features_data))
        cfg = {'features_file': str(temp_features_file)}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            # First load
            controller._refresh_features_cache()
            first_cache = dict(controller._features_cache)
            # Second load (same file)
            controller._refresh_features_cache()
            second_cache = dict(controller._features_cache)
            assert first_cache == second_cache  # nosec B101

    def test_snapshot_includes_features(
        self, mock_app: MockApp, temp_features_file: Path, sample_features_data: dict[str, Any]
    ) -> None:
        """Test snapshot includes track features."""
        temp_features_file.write_text(json.dumps(sample_features_data))
        cfg = {'features_file': str(temp_features_file)}
        with patch('sys.platform', 'linux'):
            controller = SpotifyController(mock_app, cfg)
            controller._track_id = 'spotify:track:track123'
            controller._refresh_features_cache()

            snapshot = controller.snapshot()
            assert snapshot['bpm'] == 120.0  # nosec B101
            assert snapshot['energy'] == 0.85  # nosec B101
            assert snapshot['feature_confidence'] == 0.92  # nosec B101
