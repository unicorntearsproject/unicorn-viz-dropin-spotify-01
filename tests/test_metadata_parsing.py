"""Tests for metadata parsing and canonicalization."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from spotify_controller import SpotifyController


class TestTrackIdCanonical:
    """Test _canonical_track_id method."""

    def test_canonical_empty_string(self) -> None:
        """Test empty track ID returns empty string."""
        assert SpotifyController._canonical_track_id('') == ''

    def test_canonical_none(self) -> None:
        """Test None track ID returns empty string."""
        assert SpotifyController._canonical_track_id(None) == ''

    def test_canonical_spotify_uri(self) -> None:
        """Test spotify: URI format is preserved."""
        track_id = 'spotify:track:6rqhFgbbKwnb9MLmUQDvDm'
        result = SpotifyController._canonical_track_id(track_id)
        assert result == track_id.lower()

    def test_canonical_spotify_uri_uppercase(self) -> None:
        """Test uppercase spotify: URI is lowercased."""
        track_id = 'SPOTIFY:TRACK:6rqhFgbbKwnb9MLmUQDvDm'
        result = SpotifyController._canonical_track_id(track_id)
        assert result == track_id.lower()

    def test_canonical_mpris_path(self) -> None:
        """Test MPRIS /com/spotify/track/ path is converted."""
        track_id = '/com/spotify/track/6rqhFgbbKwnb9MLmUQDvDm'
        result = SpotifyController._canonical_track_id(track_id)
        assert result == 'spotify:track:6rqhfgbbkwnb9mlmuqdvdm'

    def test_canonical_mpris_path_with_separator(self) -> None:
        """Test MPRIS path with trailing separator."""
        track_id = '/com/spotify/track/6rqhFgbbKwnb9MLmUQDvDm/'
        result = SpotifyController._canonical_track_id(track_id)
        # Trailing slash makes suffix empty, so original path is returned lowercased
        assert result == track_id.lower()

    def test_canonical_web_url(self) -> None:
        """Test web.spotify.com URL is converted."""
        track_id = 'https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDvDm'
        result = SpotifyController._canonical_track_id(track_id)
        assert result == 'spotify:track:6rqhfgbbkwnb9mlmuqdvdm'

    def test_canonical_web_url_with_query_params(self) -> None:
        """Test web URL with query params is handled."""
        track_id = 'https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDvDm?si=123'
        result = SpotifyController._canonical_track_id(track_id)
        assert result == 'spotify:track:6rqhfgbbkwnb9mlmuqdvdm'

    def test_canonical_web_url_uppercase(self) -> None:
        """Test web URL with uppercase letters."""
        track_id = 'HTTPS://OPEN.SPOTIFY.COM/TRACK/6rqhFgbbKwnb9MLmUQDvDm'
        result = SpotifyController._canonical_track_id(track_id)
        assert result == 'spotify:track:6rqhfgbbkwnb9mlmuqdvdm'

    def test_canonical_short_id_passthrough(self) -> None:
        """Test short ID without recognized prefix is lowercased."""
        track_id = 'SomeTrackId123'
        result = SpotifyController._canonical_track_id(track_id)
        assert result == track_id.lower()


class TestTrackKey:
    """Test _track_key method."""

    def test_track_key_from_id(self) -> None:
        """Test track key prefers track ID if available."""
        track_id = 'spotify:track:123'
        title = 'Song Title'
        artist = 'Artist Name'
        key = SpotifyController._track_key(track_id, title, artist)
        assert key == track_id.lower()

    def test_track_key_fallback_to_artist_title(self) -> None:
        """Test track key uses artist::title if ID is empty."""
        track_id = ''
        title = 'Song Title'
        artist = 'Artist Name'
        key = SpotifyController._track_key(track_id, title, artist)
        assert key == 'artist name::song title'

    def test_track_key_with_empty_strings(self) -> None:
        """Test track key with empty artist and title."""
        track_id = ''
        title = ''
        artist = ''
        key = SpotifyController._track_key(track_id, title, artist)
        # combo is '::'.strip(':') which returns empty string
        assert key == ''

    def test_track_key_with_whitespace(self) -> None:
        """Test track key strips whitespace."""
        track_id = ''
        title = '  Song Title  '
        artist = '  Artist Name  '
        key = SpotifyController._track_key(track_id, title, artist)
        assert key == 'artist name::song title'


class TestNormalizeTags:
    """Test _normalize_tags method."""

    def test_normalize_tags_empty_list(self) -> None:
        """Test empty list returns empty result."""
        result = SpotifyController._normalize_tags([])
        assert result == []

    def test_normalize_tags_none(self) -> None:
        """Test None returns empty result."""
        result = SpotifyController._normalize_tags(None)
        assert result == []

    def test_normalize_tags_list_of_strings(self) -> None:
        """Test list of strings is preserved and deduplicated."""
        tags = ['electronic', 'dance', 'electronic']
        result = SpotifyController._normalize_tags(tags)
        assert result == ['electronic', 'dance']

    def test_normalize_tags_string_comma_separated(self) -> None:
        """Test comma-separated string is split."""
        tags = 'electronic,dance,house'
        result = SpotifyController._normalize_tags(tags)
        assert len(result) == 3
        assert 'electronic' in result

    def test_normalize_tags_string_pipe_separated(self) -> None:
        """Test pipe-separated string is split."""
        tags = 'electronic|dance|house'
        result = SpotifyController._normalize_tags(tags)
        assert len(result) == 3
        assert 'electronic' in result

    def test_normalize_tags_mixed_separators(self) -> None:
        """Test mixed comma and pipe separators."""
        tags = 'electronic,dance|house'
        result = SpotifyController._normalize_tags(tags)
        assert len(result) == 3

    def test_normalize_tags_deduplication_case_insensitive(self) -> None:
        """Test deduplication is case-insensitive."""
        tags = ['Electronic', 'electronic', 'ELECTRONIC']
        result = SpotifyController._normalize_tags(tags)
        assert result == ['electronic']

    def test_normalize_tags_with_whitespace(self) -> None:
        """Test whitespace is stripped."""
        tags = ['  electronic  ', '  dance  ', '  house  ']
        result = SpotifyController._normalize_tags(tags)
        assert result == ['electronic', 'dance', 'house']

    def test_normalize_tags_filters_empty(self) -> None:
        """Test empty strings are filtered out."""
        tags = 'electronic, , dance, , house'
        result = SpotifyController._normalize_tags(tags)
        assert '' not in result
        assert len(result) == 3


class TestSafeFloat:
    """Test _safe_float method."""

    def test_safe_float_valid_int(self) -> None:
        """Test conversion from int."""
        result = SpotifyController._safe_float(42)
        assert result == 42.0

    def test_safe_float_valid_float(self) -> None:
        """Test conversion from float."""
        result = SpotifyController._safe_float(3.14)
        assert result == 3.14

    def test_safe_float_valid_string(self) -> None:
        """Test conversion from numeric string."""
        result = SpotifyController._safe_float('3.14')
        assert result == 3.14

    def test_safe_float_invalid_string(self) -> None:
        """Test invalid string returns 0.0."""
        result = SpotifyController._safe_float('not_a_number')
        assert result == 0.0

    def test_safe_float_none(self) -> None:
        """Test None returns 0.0."""
        result = SpotifyController._safe_float(None)
        assert result == 0.0

    def test_safe_float_empty_string(self) -> None:
        """Test empty string returns 0.0."""
        result = SpotifyController._safe_float('')
        assert result == 0.0

    def test_safe_float_negative(self) -> None:
        """Test negative numbers are handled."""
        result = SpotifyController._safe_float(-42.5)
        assert result == -42.5


class TestContextPlaylistId:
    """Test _context_playlist_id method."""

    def test_context_playlist_id_valid(self) -> None:
        """Test extraction of playlist ID from playback context."""
        playback = {
            'context': {
                'type': 'playlist',
                'uri': 'spotify:playlist:37i9dQZF1DXcBWIGoYsBA7',
            }
        }
        result = SpotifyController._context_playlist_id(playback)
        assert result == '37i9dQZF1DXcBWIGoYsBA7'

    def test_context_playlist_id_none_playback(self) -> None:
        """Test None playback returns empty string."""
        result = SpotifyController._context_playlist_id(None)
        assert result == ''

    def test_context_playlist_id_non_playlist_context(self) -> None:
        """Test non-playlist context type returns empty string."""
        playback = {
            'context': {
                'type': 'album',
                'uri': 'spotify:album:123',
            }
        }
        result = SpotifyController._context_playlist_id(playback)
        assert result == ''

    def test_context_playlist_id_missing_context(self) -> None:
        """Test missing context returns empty string."""
        playback = {'item': {'name': 'Track'}}
        result = SpotifyController._context_playlist_id(playback)
        assert result == ''

    def test_context_playlist_id_invalid_uri_format(self) -> None:
        """Test invalid URI format returns empty string."""
        playback = {
            'context': {
                'type': 'playlist',
                'uri': 'invalid:uri:format',
            }
        }
        result = SpotifyController._context_playlist_id(playback)
        assert result == ''

    def test_context_playlist_id_case_insensitive(self) -> None:
        """Test context type is case-insensitive."""
        playback = {
            'context': {
                'type': 'PLAYLIST',
                'uri': 'spotify:playlist:37i9dQZF1DXcBWIGoYsBA7',
            }
        }
        result = SpotifyController._context_playlist_id(playback)
        assert result == '37i9dQZF1DXcBWIGoYsBA7'
