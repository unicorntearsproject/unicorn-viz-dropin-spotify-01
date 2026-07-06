"""Tests for live corpus snapshot writing."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from spotify_controller import SpotifyController


def test_record_live_corpus_snapshot_writes_one_row(
    mock_app,
    tmp_path: Path,
) -> None:
    live_corpus_file = tmp_path / 'live-corpus.jsonl'
    pcm = np.sin(np.linspace(0.0, 8.0 * np.pi, 48000, dtype=np.float32)).astype(np.float32)
    mock_app.get_live_audio_window = lambda: (pcm, 48000)
    controller = SpotifyController(
        mock_app,
        {
            'live_corpus_file': str(live_corpus_file),
        },
    )

    controller._available = True
    controller._is_playing = True
    controller._status = 'playing'
    controller._track_id = 'spotify:track:track123'
    controller._title = 'Example Song'
    controller._artist = 'Example Artist'
    controller._album = 'Example Album'
    controller._duration_s = 180.0
    controller._position_s = 45.0
    controller._change_counter = 3
    controller._playback = {
        'device': {
            'id': 'device-123',
            'name': 'Desktop Speakers',
            'type': 'speaker',
            'volume_percent': 77,
        },
        'context': {
            'type': 'playlist',
            'uri': 'spotify:playlist:abc123',
        },
        'shuffle_state': True,
        'repeat_state': 'context',
        'progress_ms': 45000,
        'currently_playing_type': 'track',
    }
    controller._playlist_context = {
        'id': 'abc123',
        'name': 'Live Set',
        'uri': 'spotify:playlist:abc123',
        'total_tracks': 42,
        'owner': 'DJ Test',
    }

    snapshot = controller.snapshot()
    wrote = controller.record_live_corpus_snapshot(
        snapshot,
        {
            'vj_effect': 'Audio Spectrum',
            'vj_audio_source': 'spotify',
            'vj_playlist_index': 2,
            'vj_audio_profile': 'House',
            'vj_audio_fft_peak': 0.93,
            'vj_audio_waveform_peak': 0.81,
        },
    )

    assert wrote is True
    rows = live_corpus_file.read_text(encoding='utf-8').splitlines()
    assert len(rows) == 1
    row = json.loads(rows[0])
    assert row['spotify_track_id'] == 'spotify:track:track123'
    assert row['stream_duration_s'] > 0.0
    assert row['stream_rms'] > 0.0
    assert row['vj_effect'] == 'Audio Spectrum'
    assert row['vj_audio_source'] == 'spotify'
    assert row['vj_playlist_index'] == 2
    assert row['vj_audio_profile'] == 'House'
    assert row['vj_audio_fft_peak'] == 0.93
    assert row['vj_audio_waveform_peak'] == 0.81
    assert 'available' not in row
    assert 'is_playing' not in row
    assert 'status' not in row
    assert 'change_counter' not in row
    assert 'analysis_generated_at' not in row
    assert 'analysis_source' not in row
    assert 'analysis_status' not in row
    assert 'live_bucket' not in row
    assert 'auth_ready' not in row
    assert 'auth_status' not in row
    assert 'token_expires_in_s' not in row
    assert 'web_api_enabled' not in row
    assert 'source' not in row
    assert 'vj_streaming_provider' not in row
    assert 'vj_recording' not in row
    assert 'vj_streaming' not in row
    assert 'vj_paused' not in row
    assert 'vj_fullscreen' not in row
    assert 'spotify_energy' not in row
    assert 'spotify_feature_confidence' not in row
    assert 'spotify_playback_device_name' not in row
    assert 'spotify_playlist_context_name' not in row

    wrote_again = controller.record_live_corpus_snapshot(snapshot, {'vj_effect': 'Audio Spectrum'})
    assert wrote_again is False
    assert len(live_corpus_file.read_text(encoding='utf-8').splitlines()) == 1


def test_record_live_corpus_snapshot_skips_without_live_path(
    mock_app,
    tmp_path: Path,
) -> None:
    pcm = np.sin(np.linspace(0.0, 8.0 * np.pi, 48000, dtype=np.float32)).astype(np.float32)
    mock_app.get_live_audio_window = lambda: (pcm, 48000)
    controller = SpotifyController(
        mock_app,
        {},
    )

    controller._available = True
    controller._is_playing = True
    controller._status = 'playing'
    controller._track_id = 'spotify:track:track123'
    controller._title = 'Example Song'
    controller._artist = 'Example Artist'
    controller._album = 'Example Album'
    controller._duration_s = 180.0
    controller._position_s = 45.0
    controller._change_counter = 3

    snapshot = controller.snapshot()
    wrote = controller.record_live_corpus_snapshot(snapshot, {'vj_effect': 'Audio Spectrum'})

    assert wrote is False
    assert not (tmp_path / 'live-corpus.jsonl').exists()