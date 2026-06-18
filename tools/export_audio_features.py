"""Export Spotify audio features into the optional training corpus.

This helper reads Auto VJ JSONL logs or explicit track IDs, fetches Spotify
audio features through the authenticated Web API, and writes the merged corpus
consumed by ``spotify-01``.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_API_BASE_URL = 'https://api.spotify.com/v1'
_DEFAULT_FEATURES_PATH = Path('assets/audio/spotify_features.json')
_DEFAULT_TOKEN_STORE = Path('runtime/spotify-token.json')


def canonical_track_id(track_id: Any) -> str:
    """Return a canonical Spotify track ID string."""
    raw = str(track_id or '').strip()
    if not raw:
        return ''
    lowered = raw.lower()
    if lowered.startswith('spotify:track:'):
        return lowered
    if lowered.startswith('/com/spotify/track/'):
        suffix = lowered.rsplit('/', 1)[-1]
        return f'spotify:track:{suffix}' if suffix else lowered
    if lowered.startswith('https://open.spotify.com/track/'):
        tail = lowered.split('/track/', 1)[-1].split('?', 1)[0].split('/', 1)[0]
        return f'spotify:track:{tail}' if tail else lowered
    return lowered


def _iter_jsonl_entries(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    try:
        with path.open('r', encoding='utf-8') as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
    except FileNotFoundError:
        log.warning('Skipping missing log file %s', path)
    return entries


def _track_id_from_entry(entry: dict[str, Any]) -> str:
    for key in ('track_id', 'spotify_track_id', 'raw_track_id'):
        track_id = canonical_track_id(entry.get(key))
        if track_id:
            return track_id
    return ''


def collect_track_ids(paths: list[Path]) -> list[str]:
    """Collect canonical track IDs from one or more log files or directories."""
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        candidates = [path]
        if path.is_dir():
            candidates = sorted(path.rglob('autovj-*.jsonl'))
        for candidate in candidates:
            for entry in _iter_jsonl_entries(candidate):
                track_id = _track_id_from_entry(entry)
                if track_id and track_id not in seen:
                    seen.add(track_id)
                    ordered.append(track_id)
    return ordered


def load_existing_corpus(path: Path) -> dict[str, dict[str, Any]]:
    """Load an existing corpus file if it is present and valid."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise RuntimeError(f'Failed to read corpus file {path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'Corpus file {path} must contain a JSON object')
    corpus: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, dict):
            corpus[canonical_track_id(key)] = value
    return corpus


def _load_access_token(token_store: Path) -> str:
    try:
        payload = json.loads(token_store.read_text(encoding='utf-8'))
    except Exception as exc:
        raise RuntimeError(f'Failed to read token store {token_store}: {exc}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'Token store {token_store} must contain a JSON object')
    token = str(payload.get('access_token', '') or '').strip()
    if not token:
        raise RuntimeError(f'Token store {token_store} does not contain an access token')
    return token


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _audio_features_request(access_token: str, track_ids: list[str], timeout_s: float) -> dict[str, Any]:
    query = urllib.parse.urlencode({'ids': ','.join(track_ids)})
    url = f'{_API_BASE_URL}/audio-features?{query}'
    request = urllib.request.Request(
        url,
        method='GET',
        headers={'Authorization': f'Bearer {access_token}'},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # nosec B310
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Spotify audio features request failed with HTTP {exc.code}') from exc
    except Exception as exc:
        raise RuntimeError(f'Spotify audio features request failed: {exc}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError('Spotify audio features response was not a JSON object')
    return payload


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def build_feature_payload(api_row: dict[str, Any]) -> dict[str, Any]:
    """Convert a Spotify audio-features row into the corpus payload shape."""
    payload = {
        'acousticness': _coerce_float(api_row.get('acousticness')),
        'analysis_url': str(api_row.get('analysis_url', '') or ''),
        'bpm': _coerce_float(api_row.get('tempo')),
        'danceability': _coerce_float(api_row.get('danceability')),
        'duration_ms': int(_coerce_float(api_row.get('duration_ms'))),
        'energy': _coerce_float(api_row.get('energy')),
        'instrumentalness': _coerce_float(api_row.get('instrumentalness')),
        'key': int(_coerce_float(api_row.get('key'))),
        'liveness': _coerce_float(api_row.get('liveness')),
        'loudness': _coerce_float(api_row.get('loudness')),
        'mode': int(_coerce_float(api_row.get('mode'))),
        'speechiness': _coerce_float(api_row.get('speechiness')),
        'tempo': _coerce_float(api_row.get('tempo')),
        'time_signature': int(_coerce_float(api_row.get('time_signature'))),
        'uri': str(api_row.get('uri', '') or ''),
        'valence': _coerce_float(api_row.get('valence')),
        'confidence': 1.0,
        'tag_confidence': 0.0,
        'tags': [],
        'genres': [],
        'source': 'spotify_web_api',
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    return payload


def export_feature_corpus(
    track_ids: list[str],
    *,
    access_token: str,
    features_path: Path,
    timeout_s: float = 10.0,
) -> dict[str, dict[str, Any]]:
    """Fetch audio features for tracks and merge them into a corpus."""
    corpus = load_existing_corpus(features_path)
    unique_track_ids = [track_id for track_id in dict.fromkeys(track_ids) if track_id]
    for batch in _chunked(unique_track_ids, 100):
        payload = _audio_features_request(access_token, batch, timeout_s)
        rows = payload.get('audio_features', [])
        if not isinstance(rows, list):
            raise RuntimeError('Spotify audio features response did not contain a list')
        for row in rows:
            if not isinstance(row, dict):
                continue
            track_id = canonical_track_id(row.get('uri') or row.get('id'))
            if not track_id:
                continue
            corpus[track_id] = build_feature_payload(row)
    features_path.parent.mkdir(parents=True, exist_ok=True)
    features_path.write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    return corpus


def _collect_inputs(track_ids: list[str], log_paths: list[Path]) -> list[str]:
    ordered = [canonical_track_id(track_id) for track_id in track_ids]
    ordered.extend(collect_track_ids(log_paths))
    return [track_id for track_id in dict.fromkeys(ordered) if track_id]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Export Spotify audio features into assets/audio/spotify_features.json.',
    )
    parser.add_argument(
        'paths',
        nargs='*',
        type=Path,
        help='Auto VJ log files or directories containing autovj-*.jsonl files.',
    )
    parser.add_argument(
        '--track-id',
        action='append',
        default=[],
        help='Explicit Spotify track ID to export. Can be repeated.',
    )
    parser.add_argument(
        '--features-file',
        type=Path,
        default=_DEFAULT_FEATURES_PATH,
        help='Corpus file to write (default: assets/audio/spotify_features.json).',
    )
    parser.add_argument(
        '--token-store',
        type=Path,
        default=_DEFAULT_TOKEN_STORE,
        help='Spotify token store containing an access token.',
    )
    parser.add_argument(
        '--timeout-s',
        type=float,
        default=10.0,
        help='Per-request timeout for Spotify API calls.',
    )
    return parser


def main() -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()
    log_paths = [path for path in args.paths if path.exists()]
    track_ids = _collect_inputs(args.track_id, log_paths)
    if not track_ids:
        parser.error('no track IDs found in the provided inputs')

    access_token = _load_access_token(args.token_store)
    corpus = export_feature_corpus(
        track_ids,
        access_token=access_token,
        features_path=args.features_file,
        timeout_s=float(args.timeout_s),
    )
    print(f'Exported {len(track_ids)} tracks into {args.features_file}')
    print(f'Corpus now contains {len(corpus)} entries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())