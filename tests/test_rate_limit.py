"""Regression tests: HTTP 429 handling and token-store permissions.

Pins the CLAUDE.md Spotify rules previously unimplemented: handle 429,
honor Retry-After, back off exponentially instead of tight retry loops —
and the refresh-token store must not be world-readable.
"""
from __future__ import annotations

import io
import json
import stat
import sys
import time
import urllib.error
from email.message import Message
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import spotify_controller as sc  # noqa: E402


def _controller() -> sc.SpotifyController:
    c = sc.SpotifyController.__new__(sc.SpotifyController)
    c._rate_limited_until = 0.0
    c._rate_limit_streak = 0
    c._http_timeout_s = 0.5
    c._last_error = ''
    c._auth_status = 'ready'
    c._auth_headers = lambda: {'Authorization': 'Bearer x'}  # type: ignore[method-assign]
    return c


def _http_429(retry_after: str | None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers['Retry-After'] = retry_after
    return urllib.error.HTTPError(
        'https://api.spotify.com/v1/x', 429, 'Too Many Requests', headers,
        io.BytesIO(b''),
    )


def test_429_honors_retry_after(monkeypatch) -> None:
    c = _controller()

    def _raise(*_a, **_kw):
        raise _http_429('7')

    monkeypatch.setattr(sc.urllib.request, 'urlopen', _raise)
    assert c._api_get('/me/player') is None
    remaining = c._rate_limited_until - time.time()
    assert 5.0 < remaining <= 7.5


def test_429_without_header_backs_off_exponentially(monkeypatch) -> None:
    c = _controller()

    def _raise(*_a, **_kw):
        raise _http_429(None)

    monkeypatch.setattr(sc.urllib.request, 'urlopen', _raise)
    c._api_get('/me/player')
    first = c._rate_limited_until - time.time()
    c._rate_limited_until = 0.0  # force the next call through
    c._api_get('/me/player')
    second = c._rate_limited_until - time.time()
    assert second > first  # streak grows the backoff
    assert second <= 120.5  # capped


def test_rate_limited_window_skips_requests_locally(monkeypatch) -> None:
    c = _controller()
    c._rate_limited_until = time.time() + 60.0
    calls = []
    monkeypatch.setattr(
        sc.urllib.request, 'urlopen', lambda *a, **kw: calls.append(1)
    )
    assert c._api_get('/me/player') is None
    assert calls == []  # no network I/O while rate-limited
    assert 'rate_limited' in c._last_error


def test_success_resets_backoff_streak(monkeypatch) -> None:
    c = _controller()
    c._rate_limit_streak = 5

    class _Resp:
        status = 200

        def read(self):
            return json.dumps({'ok': True}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sc.urllib.request, 'urlopen', lambda *a, **kw: _Resp())
    assert c._api_get('/me/player') == {'ok': True}
    assert c._rate_limit_streak == 0


def test_token_store_written_owner_only(tmp_path) -> None:
    c = sc.SpotifyController.__new__(sc.SpotifyController)
    c._token_store = tmp_path / 'runtime' / 'spotify_token.json'
    c._token = {'refresh_token': 'secret'}
    c._save_token_store()
    mode = stat.S_IMODE(c._token_store.stat().st_mode)
    assert mode == 0o600
