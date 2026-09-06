"""Shared pytest fixtures for Spotify controller tests."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class MockApp:
    """Mock app for testing SpotifyController."""

    def __init__(self) -> None:
        self.vj_api = MagicMock()
        self.subsystems: dict[str, Any] = {}

    def get_subsystem(self, name: str) -> Any | None:
        return self.subsystems.get(name)


@pytest.fixture
def mock_app() -> MockApp:
    """Provide a mock app instance."""
    return MockApp()


@pytest.fixture
def temp_token_file() -> Path:
    """Provide a temporary token storage file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def sample_token_payload() -> dict[str, Any]:
    """Provide a sample Spotify token response."""
    return {
        'access_token': 'BQC_...sample...',
        'token_type': 'Bearer',
        'expires_in': 3600,
        'refresh_token': 'AQC_...sample...',
        'scope': 'user-read-playback-state user-read-currently-playing',
    }


@pytest.fixture
def sample_playback_payload() -> dict[str, Any]:
    """Provide a sample Spotify /me/player response."""
    return {
        'timestamp': 1718721600000,
        'progress_ms': 45000,
        'is_playing': True,
        'item': {
            'id': 'track123',
            'name': 'Example Song',
            'uri': 'spotify:track:track123',
            'duration_ms': 180000,
            'artists': [{'name': 'Example Artist'}],
            'album': {'name': 'Example Album'},
        },
        'device': {
            'id': 'device123',
            'is_active': True,
            'name': 'Desktop',
            'type': 'Computer',
            'volume_percent': 75,
        },
        'context': {
            'type': 'playlist',
            'uri': 'spotify:playlist:pl123',
            'external_urls': {'spotify': 'https://open.spotify.com/playlist/pl123'},
        },
    }


@pytest.fixture
def sample_queue_payload() -> dict[str, Any]:
    """Provide a sample Spotify /me/player/queue response."""
    return {
        'currently_playing': {
            'id': 'track123',
            'name': 'Example Song',
            'uri': 'spotify:track:track123',
        },
        'queue': [
            {
                'id': 'track456',
                'name': 'Next Song',
                'uri': 'spotify:track:track456',
            },
            {
                'id': 'track789',
                'name': 'Song After That',
                'uri': 'spotify:track:track789',
            },
        ],
    }


@pytest.fixture
def sample_playlist_payload() -> dict[str, Any]:
    """Provide a sample Spotify /playlists/{id} response."""
    return {
        'id': 'pl123',
        'name': 'My Playlist',
        'uri': 'spotify:playlist:pl123',
        'external_urls': {'spotify': 'https://open.spotify.com/playlist/pl123'},
        'tracks': {'total': 42, 'href': 'https://api.spotify.com/v1/playlists/pl123/tracks'},
        'owner': {'display_name': 'example_user'},
    }


