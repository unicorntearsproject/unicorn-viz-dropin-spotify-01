"""Tests for the Spotify audio feature corpus exporter."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.export_audio_features import (  # noqa: E402
    build_feature_payload,
    canonical_track_id,
    collect_track_ids,
    export_feature_corpus,
    load_existing_corpus,
)


def test_canonical_track_id_matches_controller_rules() -> None:
    assert canonical_track_id('HTTPS://OPEN.SPOTIFY.COM/TRACK/ABC123?si=1') == 'spotify:track:abc123'
    assert canonical_track_id('/com/spotify/track/ABC123') == 'spotify:track:abc123'
    assert canonical_track_id('spotify:track:ABC123') == 'spotify:track:abc123'


def test_collect_track_ids_from_effect_swap_log(tmp_path: Path) -> None:
    log_file = tmp_path / 'autovj-20260618T000000.jsonl'
    log_file.write_text(
        '\n'.join(
            [
                json.dumps({'action': 'detector_tick', 'note': 'ignore'}),
                json.dumps(
                    {
                        'action': 'effect_swap',
                        'track_id': 'spotify:track:ABC123',
                        'track_title': 'Song One',
                    }
                ),
                json.dumps(
                    {
                        'action': 'effect_swap',
                        'track_id': 'spotify:track:abc123',
                        'track_title': 'Song One again',
                    }
                ),
            ]
        ),
        encoding='utf-8',
    )

    assert collect_track_ids([log_file]) == ['spotify:track:abc123']


def test_build_feature_payload_includes_expected_fields() -> None:
    payload = build_feature_payload(
        {
            'acousticness': 0.12,
            'analysis_url': 'https://api.spotify.com/v1/audio-analysis/abc123',
            'danceability': 0.73,
            'duration_ms': 123456,
            'energy': 0.88,
            'instrumentalness': 0.01,
            'key': 5,
            'liveness': 0.09,
            'loudness': -7.5,
            'mode': 1,
            'speechiness': 0.04,
            'tempo': 126.5,
            'time_signature': 4,
            'uri': 'spotify:track:abc123',
            'valence': 0.66,
        }
    )

    assert payload['bpm'] == 126.5
    assert payload['energy'] == 0.88
    assert payload['danceability'] == 0.73
    assert payload['valence'] == 0.66
    assert payload['confidence'] == 1.0
    assert payload['tags'] == []
    assert payload['genres'] == []
    assert payload['source'] == 'spotify_web_api'


def test_export_feature_corpus_merges_existing_data(tmp_path: Path) -> None:
    features_file = tmp_path / 'spotify_features.json'
    features_file.write_text(
        json.dumps({'spotify:track:keepme': {'bpm': 100.0, 'confidence': 0.5}}),
        encoding='utf-8',
    )

    response = {
        'audio_features': [
            {
                'id': 'abc123',
                'uri': 'spotify:track:abc123',
                'tempo': 126.5,
                'energy': 0.88,
                'danceability': 0.73,
                'valence': 0.66,
            }
        ]
    }

    with patch('tools.export_audio_features._audio_features_request', return_value=response):
        corpus = export_feature_corpus(
            ['spotify:track:abc123'],
            access_token='token',
            features_path=features_file,
        )

    saved = load_existing_corpus(features_file)
    assert 'spotify:track:keepme' in saved
    assert 'spotify:track:abc123' in saved
    assert corpus['spotify:track:abc123']['bpm'] == 126.5
    assert saved['spotify:track:abc123']['confidence'] == 1.0