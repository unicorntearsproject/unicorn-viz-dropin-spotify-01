"""Spotify runtime subsystem for unicorn-viz.

This consolidated drop-in provides both local now-playing metadata (playerctl/
MPRIS) and optional authenticated Spotify Web API context for queue and
playlist-awareness.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

import numpy as np

log = logging.getLogger(__name__)

_AUTH_BASE_URL = 'https://accounts.spotify.com/authorize'
_TOKEN_URL = 'https://accounts.spotify.com/api/token'
_API_BASE_URL = 'https://api.spotify.com/v1'


class _AuthCaptureHandler(BaseHTTPRequestHandler):
    """One-shot loopback callback handler for Spotify PKCE auth."""

    server: '_AuthCaptureServer'

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        self.server.auth_payload = {
            'path': parsed.path,
            'code': str((params.get('code') or [''])[0]),
            'state': str((params.get('state') or [''])[0]),
            'error': str((params.get('error') or [''])[0]),
        }
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(
            (
                '<html><body><h1>Spotify auth received</h1>'
                '<p>You can return to Unicorn Viz.</p></body></html>'
            ).encode('utf-8')
        )
        self.server.auth_event.set()

    def log_message(self, fmt: str, *args: object) -> None:
        return


class _AuthCaptureServer(ThreadingHTTPServer):
    """HTTP server wrapper that stores auth callback payload."""

    def __init__(self, server_address: tuple[str, int]) -> None:
        super().__init__(server_address, _AuthCaptureHandler)
        self.auth_event = threading.Event()
        self.auth_payload: dict[str, str] = {}


class SpotifyController:
    """Optional Spotify metadata subsystem.

    Thread-safety: this controller is updated on the app's main thread only.
    """

    def __init__(self, app: Any, cfg: dict[str, Any] | None = None) -> None:
        self._app = app
        self._cfg = dict(cfg or {})
        self._local_enabled = bool(self._cfg.get('enabled', False))
        self._player = str(self._cfg.get('player', 'spotify') or 'spotify').strip()
        self._poll_interval_s = max(0.15, float(self._cfg.get('poll_interval_s', 0.75) or 0.75))
        self._command_timeout_s = max(
            0.05,
            float(self._cfg.get('command_timeout_s', 0.25) or 0.25),
        )
        self._now_playing_banner_enabled = bool(self._cfg.get('now_playing_banner', True))
        self._now_playing_banner_hold_s = max(
            1.0,
            float(self._cfg.get('now_playing_banner_hold_s', 10.0) or 10.0),
        )
        # Delay before the now-playing banner fires after a track change, to
        # absorb extended DJ transitions where the incoming track is briefly
        # detected before the mix fully lands.
        self._now_playing_banner_delay_s = max(
            0.0,
            float(self._cfg.get('now_playing_banner_delay_s', 15.0) or 15.0),
        )
        self._banner_exposed_change_counter: int = 0
        self._banner_promote_at: float = 0.0

        self._playerctl = shutil.which('playerctl')
        if self._local_enabled and sys.platform == 'win32':
            log.warning(
                'SpotifyController uses a playerctl/MPRIS backend and is not currently supported on Windows; '
                'enable [spotify.web_api] or add a Windows media-session backend'
            )
        if self._local_enabled and self._playerctl is None:
            self._local_enabled = False
            log.warning('SpotifyController disabled: playerctl not found in PATH')

        web_cfg = self._cfg.get('web_api', {}) if hasattr(self._cfg, 'get') else {}
        if not isinstance(web_cfg, dict):
            web_cfg = {}
        if not web_cfg:
            legacy_keys = (
                'enabled',
                'client_id',
                'redirect_uri',
                'scopes',
                'token_store',
                'http_timeout_s',
                'queue_poll_every_n',
                'playlist_poll_every_n',
                'resolve_queue',
                'resolve_playlist_context',
                'poll_interval_s',
            )
            if any(key in self._cfg for key in legacy_keys):
                web_cfg = {key: self._cfg.get(key) for key in legacy_keys if key in self._cfg}
        self._web_cfg = web_cfg
        self._web_enabled = bool(self._web_cfg.get('enabled', False))

        self.enabled = self._local_enabled or self._web_enabled

        self._live_corpus_path = self._resolve_features_path(self._cfg.get('live_corpus_file'))
        self._live_corpus_last_signature = ''

        self._last_poll_t: float = -1e9
        self._available: bool = False
        self._is_playing: bool = False
        self._status: str = 'stopped'

        self._track_id: str = ''
        self._title: str = ''
        self._artist: str = ''
        self._album: str = ''
        self._previous_track_id: str = ''
        self._previous_title: str = ''
        self._previous_artist: str = ''
        self._previous_album: str = ''

        self._duration_s: float = 0.0
        self._position_s: float = 0.0
        self._track_started_t: float = 0.0

        self._change_counter: int = 0

        # When playerctl is active it detects track changes locally, so web API
        # polls are event-driven (triggered by track change) rather than timed.
        # The timed fallback is used when playerctl is unavailable (Windows) so
        # the web API becomes the primary track-change detector.
        # poll_interval_s: used as the timed interval on Windows-only setups AND
        #   as the slow health-check fallback when playerctl is active.
        self._web_poll_interval_s = max(
            1.5,
            float(self._web_cfg.get('poll_interval_s', 3.0) or 3.0),
        )
        # Slow health-check fallback when event-driven (playerctl active): fires
        # every N seconds just to catch any missed events or auth expiry.
        self._web_poll_fallback_s = max(
            30.0,
            float(self._web_cfg.get('poll_fallback_s', 60.0) or 60.0),
        )
        self._web_last_poll_t = -1e9
        self._web_refresh_pending: bool = False
        self._http_timeout_s = max(
            0.2,
            float(self._web_cfg.get('http_timeout_s', 2.0) or 2.0),
        )
        # Queue polling: original use case (pre-fetching BPM for transitions) is
        # removed. Disabled by default; enable in config if you want queue length
        # for display purposes.
        self._resolve_queue = bool(self._web_cfg.get('resolve_queue', False))
        self._resolve_playlist_context = bool(
            self._web_cfg.get('resolve_playlist_context', True)
        )

        self._web_poll_counter = 0
        self._web_poll_inflight = False
        self._state_lock = threading.Lock()

        self._client_id = str(
            self._web_cfg.get('client_id', '')
            or os.environ.get('UNICORNVIZ_SPOTIFY_CLIENT_ID', '')
            or os.environ.get('SPOTIFY_CLIENT_ID', '')
        ).strip()
        self._redirect_uri = str(
            self._web_cfg.get('redirect_uri', 'http://127.0.0.1:43879/callback')
            or 'http://127.0.0.1:43879/callback'
        ).strip()
        raw_scopes = self._web_cfg.get('scopes', []) or []
        if isinstance(raw_scopes, str):
            self._scopes = [s.strip() for s in raw_scopes.split() if s.strip()]
        else:
            self._scopes = [str(s).strip() for s in raw_scopes if str(s).strip()]
        if not self._scopes:
            self._scopes = [
                'user-read-playback-state',
                'user-read-currently-playing',
                'playlist-read-private',
                'playlist-read-collaborative',
            ]
        self._token_store = self._resolve_token_path(
            self._web_cfg.get('token_store', 'runtime/spotify-token.json')
        )

        self._auth_ready = False
        self._auth_status = 'disabled' if not self._web_enabled else 'not_configured'
        self._last_error = ''
        self._token: dict[str, Any] = {}
        self._token_expires_at = 0.0
        self._auth_state = ''
        self._code_verifier = ''
        self._playback: dict[str, Any] | None = None
        self._queue: list[dict[str, Any]] = []
        self._playlist_context: dict[str, Any] | None = None
        self._display_name: str = ''
        self._auth_thread: threading.Thread | None = None

        if self._web_enabled and self._client_id:
            self._load_token_store()
        elif self._web_enabled:
            self._auth_status = 'missing_client_id'

    def handle_key(self, sym: int, mod: int) -> 'str | None | bool':
        """Handle Ctrl+Alt+S (auth) and Ctrl+Alt+Shift+S (logout)."""
        import sdl2  # noqa: PLC0415

        if (mod & sdl2.KMOD_CTRL) and (mod & sdl2.KMOD_ALT) and sym == sdl2.SDLK_s:
            if mod & sdl2.KMOD_SHIFT:
                return self.logout()
            return self.begin_auth_async()
        return False

    def update(self, dt: float, audio: Any) -> None:  # noqa: ARG002
        """Poll Spotify state on a throttled cadence."""
        if not self.enabled:
            return
        if self._local_enabled:
            self._update_local(dt)
        if self._web_enabled:
            self._update_web_api()
        # Live corpus capture moved to Auto VJ's per-beat sequence writer.
        # The append-per-5s bucket logic here is replaced by musical-time
        # heartbeat + event keyframes. See training-capture-strategy.md.
        # if self._live_corpus_path is not None:
        #     runtime_sample_fn = getattr(self._app, 'build_live_corpus_sample', None)
        #     runtime_fields: Mapping[str, Any] | None = None
        #     if callable(runtime_sample_fn):
        #         try:
        #             runtime_fields = runtime_sample_fn()
        #         except Exception:
        #             runtime_fields = None
        #     try:
        #         self.record_live_corpus_snapshot(self.snapshot(), runtime_fields)
        #     except Exception:
        #         log.exception('Spotify live corpus write failed')

    def _update_local(self, dt: float) -> None:
        """Refresh local MPRIS/playerctl metadata."""
        now = time.monotonic()
        if (now - self._last_poll_t) < self._poll_interval_s:
            if self._is_playing and self._track_started_t > 0.0:
                self._position_s = max(0.0, self._position_s + max(0.0, float(dt)))
        else:
            self._last_poll_t = now
            self._poll_playerctl(now)
        # Promote the banner change counter once the transition delay has elapsed.
        if self._banner_promote_at > 0.0 and now >= self._banner_promote_at:
            self._banner_exposed_change_counter = self._change_counter
            self._banner_promote_at = 0.0

    def _update_web_api(self) -> None:
        """Refresh authenticated Spotify Web API payloads.

        When playerctl is active, polls are event-driven: a track change sets
        _web_refresh_pending and this method fires immediately on the next frame.
        A slow fallback timer (poll_fallback_s, default 60 s) catches any missed
        events and performs auth health checks.

        When playerctl is NOT available (Windows), the web API is the primary
        track detector and polls on the regular poll_interval_s cadence.
        """
        now = time.monotonic()

        pending = False
        with self._state_lock:
            if self._web_refresh_pending:
                pending = True
                self._web_refresh_pending = False

        if not pending:
            # Choose interval based on whether local detection is handling track changes.
            interval = (
                self._web_poll_fallback_s
                if self._local_enabled
                else self._web_poll_interval_s
            )
            if (now - self._web_last_poll_t) < interval:
                return

        self._web_last_poll_t = now

        with self._state_lock:
            if self._web_poll_inflight:
                return
            self._web_poll_inflight = True

        self._web_poll_counter += 1
        do_queue = self._resolve_queue  # queue disabled by default; honour config
        do_playlist_context = pending or (self._web_poll_counter % 10 == 0)
        thread = threading.Thread(
            target=self._poll_worker,
            kwargs={
                'do_queue': do_queue,
                'do_playlist_context': do_playlist_context,
            },
            daemon=True,
            name='spotify-webapi-poll',
        )
        thread.start()

    def shutdown(self) -> None:
        """Shutdown hook for the app subsystem manager."""
        return

    def snapshot(self) -> dict[str, Any]:
        """Return the current Spotify metadata snapshot for integrations."""
        canonical_track_id = self._canonical_track_id(self._track_id)
        duration = max(0.0, float(self._duration_s))
        position = max(0.0, float(self._position_s))
        progress = min(1.0, position / duration) if duration > 0.0 else 0.0

        source = 'playerctl'
        if self._web_enabled and self._local_enabled:
            source = 'playerctl+webapi'
        elif self._web_enabled:
            source = 'webapi'

        expires_in_s = (
            max(0.0, float(self._token_expires_at - time.time()))
            if self._token_expires_at > 0.0
            else 0.0
        )
        with self._state_lock:
            playback = dict(self._playback) if isinstance(self._playback, dict) else None
            queue = list(self._queue)
            queue_len = len(self._queue)
            playlist_context = (
                dict(self._playlist_context)
                if isinstance(self._playlist_context, dict)
                else None
            )
            poll_inflight = bool(self._web_poll_inflight)

        return {
            'available': self._available,
            'is_playing': self._is_playing,
            'status': self._status,
            'track_id': canonical_track_id,
            'raw_track_id': self._track_id,
            'title': self._title,
            'artist': self._artist,
            'album': self._album,
            'previous_track_id': self._previous_track_id,
            'previous_title': self._previous_title,
            'previous_artist': self._previous_artist,
            'previous_album': self._previous_album,
            'duration_s': duration,
            'position_s': position,
            'progress': progress,
            'change_counter': self._change_counter,
            'banner_change_counter': self._banner_exposed_change_counter,
            'now_playing_banner_enabled': self._now_playing_banner_enabled,
            'now_playing_banner_hold_s': self._now_playing_banner_hold_s,
            'tags': [],
            'genres': [],
            'tag_confidence': 0.0,
            'web_api_enabled': bool(self._web_enabled),
            'auth_ready': bool(self._auth_ready),
            'auth_status': str(self._auth_status),
            'display_name': str(self._display_name),
            'needs_auth': str(self._auth_status)
            in {
                'needs_auth',
                'missing_client_id',
                'auth_timeout',
                'auth_denied',
                'token_exchange_failed',
                'refresh_failed',
                'token_error',
                'token_invalid',
            },
            'token_expires_in_s': expires_in_s,
            'last_error': str(self._last_error),
            'playback': playback,
            'queue': queue,
            'queue_len': queue_len,
            'playlist_context': playlist_context,
            'poll_inflight': poll_inflight,
            'source': source,
        }

    def begin_auth_async(self, timeout_s: float = 180.0) -> str:
        """Start PKCE auth in a background thread and return immediately."""
        if not self._web_enabled:
            return 'Spotify web auth disabled'
        if not self._client_id:
            self._auth_status = 'missing_client_id'
            return 'Spotify missing client ID'
        if self._auth_thread is not None and self._auth_thread.is_alive():
            return 'Spotify auth already in progress'

        def _worker() -> None:
            ok = self.begin_auth(timeout_s=timeout_s, open_browser=True)
            if ok:
                log.info('Spotify auth complete')
            else:
                log.warning('Spotify auth failed: %s', self._auth_status)

        self._auth_thread = threading.Thread(
            target=_worker,
            daemon=True,
            name='spotify-auth',
        )
        self._auth_thread.start()
        return 'Spotify auth started'

    def begin_auth(self, timeout_s: float = 180.0, open_browser: bool = True) -> bool:
        """Run loopback PKCE auth bootstrap and persist tokens on success."""
        auth_url = self.build_auth_url()
        if not auth_url:
            return False

        parsed = urllib.parse.urlparse(self._redirect_uri)
        host = parsed.hostname or '127.0.0.1'
        port = int(parsed.port or 80)
        path = parsed.path or '/callback'
        server = _AuthCaptureServer((host, port))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            if open_browser:
                webbrowser.open(auth_url, new=1, autoraise=True)
            if not server.auth_event.wait(timeout=max(10.0, float(timeout_s))):
                self._auth_status = 'auth_timeout'
                return False
        finally:
            server.shutdown()
            server.server_close()

        payload = dict(server.auth_payload)
        if payload.get('path') != path:
            self._auth_status = 'auth_path_mismatch'
            return False
        if payload.get('error'):
            self._last_error = str(payload.get('error'))
            self._auth_status = 'auth_denied'
            return False
        if payload.get('state') != self._auth_state:
            self._auth_status = 'auth_state_mismatch'
            return False
        code = str(payload.get('code', '') or '').strip()
        if not code:
            self._auth_status = 'auth_code_missing'
            return False
        return self._exchange_code_for_token(code)

    def build_auth_url(self) -> str | None:
        """Return the browser auth URL for Spotify PKCE auth."""
        if not self._web_enabled or not self._client_id:
            self._auth_status = 'missing_client_id'
            return None
        self._auth_state = secrets.token_urlsafe(24)
        self._code_verifier = self._pkce_verifier()
        params = {
            'client_id': self._client_id,
            'response_type': 'code',
            'redirect_uri': self._redirect_uri,
            'code_challenge_method': 'S256',
            'code_challenge': self._pkce_challenge(self._code_verifier),
            'state': self._auth_state,
            'scope': ' '.join(self._scopes),
        }
        self._auth_status = 'awaiting_user_auth'
        return _AUTH_BASE_URL + '?' + urllib.parse.urlencode(params)

    def logout(self) -> str:
        """Clear local Spotify auth state and delete persisted token file."""
        deleted = False
        try:
            if self._token_store.exists():
                self._token_store.unlink()
                deleted = True
        except Exception as exc:
            self._last_error = f'token_delete_failed: {exc}'
            self._auth_status = 'token_delete_failed'
            self._auth_ready = False
            self._token = {}
            self._token_expires_at = 0.0
            self._queue = []
            self._playlist_context = None
            self._playback = None
            return 'Spotify logout failed'

        self._auth_ready = False
        self._token = {}
        self._token_expires_at = 0.0
        self._queue = []
        self._playlist_context = None
        self._playback = None
        self._display_name = ''
        self._auth_status = 'logged_out'
        self._last_error = ''
        return 'Spotify logged out' if deleted else 'Spotify session cleared'

    def _poll_playerctl(self, now: float) -> None:
        parts = self._run_playerctl(
            'metadata',
            '--format',
            '{{status}}\t{{mpris:trackid}}\t{{xesam:title}}\t{{xesam:artist}}\t{{xesam:album}}\t{{mpris:length}}',
        )
        if parts is None or len(parts) < 6:
            if self._available:
                log.info('SpotifyController: player unavailable')
            self._available = False
            self._is_playing = False
            self._status = 'stopped'
            return

        status = str(parts[0] or '').strip().lower()
        track_id = str(parts[1] or '').strip()
        title = str(parts[2] or '').strip()
        artist = str(parts[3] or '').strip()
        album = str(parts[4] or '').strip()

        length_us = self._safe_float(parts[5])
        duration_s = max(0.0, length_us / 1_000_000.0)

        old_track_key = self._track_key(self._track_id, self._title, self._artist)
        new_track_key = self._track_key(track_id, title, artist)

        self._available = True
        self._status = status or 'stopped'
        self._is_playing = self._status == 'playing'
        self._duration_s = duration_s

        if new_track_key and new_track_key != old_track_key:
            self._previous_track_id = self._track_id
            self._previous_title = self._title
            self._previous_artist = self._artist
            self._previous_album = self._album
            self._track_id = track_id
            self._title = title
            self._artist = artist
            self._album = album
            self._change_counter += 1
            # Arm the banner promotion timer; the new counter is withheld from
            # the banner until the delay elapses so transient mid-mix detections
            # do not flash the overlay prematurely.
            self._banner_promote_at = now + self._now_playing_banner_delay_s
            self._position_s = 0.0
            self._track_started_t = now
            log.info('Spotify track: %s - %s', self._artist or 'Unknown artist', self._title or 'Unknown title')
            # Signal web API to refresh playlist context immediately on the next
            # update() call rather than waiting for the slow fallback timer.
            with self._state_lock:
                self._web_refresh_pending = True
        elif track_id:
            self._track_id = track_id
            self._title = title
            self._artist = artist
            self._album = album

        pos_parts = self._run_playerctl('position')
        if pos_parts and pos_parts[0]:
            self._position_s = max(0.0, self._safe_float(pos_parts[0]))
            self._track_started_t = now
        elif self._is_playing and self._track_started_t > 0.0:
            elapsed = max(0.0, now - self._track_started_t)
            self._position_s = max(self._position_s, elapsed)

    def _run_playerctl(self, *args: str) -> list[str] | None:
        if self._playerctl is None:
            return None
        cmd = [self._playerctl, f'--player={self._player}', *args]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._command_timeout_s,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None
        line = (proc.stdout or '').strip()
        if not line:
            return None
        return line.split('\t')

    def _resolve_token_path(self, raw_path: Any) -> Path:
        raw = str(raw_path or '').strip() or 'runtime/spotify-token.json'
        path = Path(raw)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[2] / path

    def _load_token_store(self) -> None:
        try:
            with self._token_store.open('r', encoding='utf-8') as f:
                payload = json.load(f)
        except FileNotFoundError:
            self._auth_status = 'needs_auth'
            return
        except Exception as exc:
            self._last_error = f'token_load_failed: {exc}'
            self._auth_status = 'token_error'
            return
        if not isinstance(payload, dict):
            self._auth_status = 'token_error'
            return
        self._token = payload
        self._token_expires_at = float(payload.get('expires_at', 0.0) or 0.0)
        self._auth_ready = bool(payload.get('access_token'))
        self._auth_status = 'ready' if self._auth_ready else 'needs_auth'

    def _save_token_store(self) -> None:
        self._token_store.parent.mkdir(parents=True, exist_ok=True)
        with self._token_store.open('w', encoding='utf-8') as f:
            json.dump(self._token, f, indent=2, sort_keys=True)

    def _token_expired(self, skew_s: float = 30.0) -> bool:
        return time.time() >= (self._token_expires_at - skew_s)

    @staticmethod
    def _pkce_verifier() -> str:
        return secrets.token_urlsafe(64)

    @staticmethod
    def _pkce_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')

    def _exchange_code_for_token(self, code: str) -> bool:
        data = urllib.parse.urlencode({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self._redirect_uri,
            'client_id': self._client_id,
            'code_verifier': self._code_verifier,
        }).encode('utf-8')
        request = urllib.request.Request(
            _TOKEN_URL,
            data=data,
            method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        try:
            with urllib.request.urlopen(request, timeout=15.0) as response:  # nosec B310
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            self._last_error = f'token_exchange_failed: {exc}'
            self._auth_status = 'token_exchange_failed'
            return False
        return self._apply_token_payload(payload)

    def _refresh_access_token(self) -> bool:
        refresh_token = str(self._token.get('refresh_token', '') or '').strip()
        if not refresh_token:
            self._auth_status = 'needs_auth'
            self._auth_ready = False
            return False
        data = urllib.parse.urlencode({
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self._client_id,
        }).encode('utf-8')
        request = urllib.request.Request(
            _TOKEN_URL,
            data=data,
            method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        try:
            with urllib.request.urlopen(request, timeout=15.0) as response:  # nosec B310
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            self._last_error = f'token_refresh_failed: {exc}'
            self._auth_status = 'refresh_failed'
            return False
        if 'refresh_token' not in payload:
            payload['refresh_token'] = refresh_token
        return self._apply_token_payload(payload)

    def _apply_token_payload(self, payload: dict[str, Any]) -> bool:
        access_token = str(payload.get('access_token', '') or '').strip()
        if not access_token:
            self._auth_status = 'token_invalid'
            return False
        expires_in = max(1.0, float(payload.get('expires_in', 3600.0) or 3600.0))
        self._token = {
            'access_token': access_token,
            'refresh_token': str(
                payload.get('refresh_token', self._token.get('refresh_token', '')) or ''
            ),
            'token_type': str(payload.get('token_type', 'Bearer') or 'Bearer'),
            'scope': str(payload.get('scope', ' '.join(self._scopes)) or ' '.join(self._scopes)),
            'expires_at': float(time.time() + expires_in),
        }
        self._token_expires_at = float(self._token['expires_at'])
        self._auth_ready = True
        self._auth_status = 'ready'
        self._last_error = ''
        try:
            self._save_token_store()
        except Exception as exc:
            self._last_error = f'token_save_failed: {exc}'
            self._auth_status = 'token_save_failed'
            return False
        return True

    def _auth_headers(self) -> dict[str, str] | None:
        token = str(self._token.get('access_token', '') or '').strip()
        if not token:
            return None
        return {'Authorization': f'Bearer {token}'}

    def _api_get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any] | None:
        headers = self._auth_headers()
        if headers is None:
            return None
        url = _API_BASE_URL + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            if clean:
                url += '?' + urllib.parse.urlencode(clean, doseq=True)
        request = urllib.request.Request(url, headers=headers, method='GET')
        try:
            with urllib.request.urlopen(request, timeout=self._http_timeout_s) as response:  # nosec B310
                if response.status == 204:
                    return {}
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                self._auth_status = 'token_expired'
            self._last_error = f'api_get_failed:{path}:{exc.code}'
            return None
        except Exception as exc:
            self._last_error = f'api_get_failed:{path}:{exc}'
            return None

    @staticmethod
    def _context_playlist_id(playback: dict[str, Any] | None) -> str:
        if not isinstance(playback, dict):
            return ''
        context = playback.get('context')
        if not isinstance(context, dict):
            return ''
        if str(context.get('type', '') or '').strip().lower() != 'playlist':
            return ''
        uri = str(context.get('uri', '') or '').strip()
        prefix = 'spotify:playlist:'
        if uri.startswith(prefix):
            return uri[len(prefix):].strip()
        return ''

    def _refresh_remote_state(self, *, do_queue: bool, do_playlist_context: bool) -> None:
        playback = self._api_get('/me/player')
        if playback is None:
            return

        # Always refresh playlist context when the track changes so auto_vj sees
        # the playlist name on the same poll cycle as the track change event.
        new_item_id = ''
        new_item = playback.get('item')
        if isinstance(new_item, dict):
            new_item_id = str(new_item.get('id', '') or '')
        with self._state_lock:
            old_playback = self._playback
        old_item_id = ''
        if isinstance(old_playback, dict):
            old_item = old_playback.get('item')
            if isinstance(old_item, dict):
                old_item_id = str(old_item.get('id', '') or '')
        if new_item_id and new_item_id != old_item_id:
            do_playlist_context = True

        queue_items: list[dict[str, Any]] | None = None
        playlist_context_out: dict[str, Any] | None = None
        if self._resolve_queue and do_queue:
            queue_payload = self._api_get('/me/player/queue')
            if isinstance(queue_payload, dict):
                raw_queue = queue_payload.get('queue', [])
                if isinstance(raw_queue, list):
                    queue_items = [item for item in raw_queue if isinstance(item, dict)]
        if self._resolve_playlist_context and do_playlist_context:
            playlist_id = self._context_playlist_id(playback)
            if playlist_id:
                meta = self._api_get(
                    f'/playlists/{playlist_id}',
                    query={'fields': 'id,name,uri,tracks(total),owner(display_name)'},
                )
                if isinstance(meta, dict):
                    tracks = meta.get('tracks') if isinstance(meta.get('tracks'), dict) else {}
                    owner = meta.get('owner') if isinstance(meta.get('owner'), dict) else {}
                    playlist_context_out = {
                        'id': str(meta.get('id', '') or ''),
                        'name': str(meta.get('name', '') or ''),
                        'uri': str(meta.get('uri', '') or ''),
                        'total_tracks': int(tracks.get('total', 0) or 0),
                        'owner': str(owner.get('display_name', '') or ''),
                    }

        with self._state_lock:
            self._playback = playback
            if queue_items is not None:
                self._queue = queue_items
            if isinstance(playlist_context_out, dict):
                self._playlist_context = playlist_context_out

    def _poll_worker(self, *, do_queue: bool, do_playlist_context: bool) -> None:
        try:
            if not self._client_id:
                self._auth_status = 'missing_client_id'
                return
            if not self._auth_ready:
                self._load_token_store()
                if not self._auth_ready:
                    return
            if self._token_expired():
                if not self._refresh_access_token():
                    return
            if not self._display_name:
                self._fetch_display_name()
            self._refresh_remote_state(
                do_queue=do_queue,
                do_playlist_context=do_playlist_context,
            )
        finally:
            with self._state_lock:
                self._web_poll_inflight = False

    def _fetch_display_name(self) -> None:
        """Fetch the authenticated user's display name from /me (once per session)."""
        me = self._api_get('/me')
        if isinstance(me, dict):
            name = str(me.get('display_name', '') or '').strip()
            if not name:
                name = str(me.get('id', '') or '').strip()
            with self._state_lock:
                self._display_name = name

    def _resolve_features_path(self, configured: Any) -> Path | None:
        if not configured:
            return None
        raw = str(configured).strip()
        if not raw:
            return None
        path = Path(raw)
        if path.is_absolute():
            return path
        project_root = Path(__file__).resolve().parents[2]
        return project_root / path

    def record_live_corpus_snapshot(
        self,
        snapshot: Mapping[str, Any],
        runtime_fields: Mapping[str, Any] | None = None,
    ) -> bool:
        """Append a live merged Spotify/VJ/stream sample to the configured corpus file."""

        path = self._live_corpus_path
        if path is None or not isinstance(snapshot, Mapping):
            return False

        track_id = self._canonical_track_id(str(snapshot.get('track_id', '') or ''))
        if not track_id:
            return False

        position_s = max(0.0, float(snapshot.get('position_s', 0.0) or 0.0))
        change_counter = int(snapshot.get('change_counter', 0) or 0)
        bucket_s = 5.0
        bucket = int(position_s // bucket_s)
        effect_name = ''
        if runtime_fields is not None:
            effect_name = str(runtime_fields.get('vj_effect', '') or '').strip().lower()
        signature = f'{track_id}:{change_counter}:{bucket}:{effect_name}'
        if signature == self._live_corpus_last_signature:
            return False

        stream_window = None
        stream_rate = 0
        stream_features: dict[str, Any] = {}
        live_audio_fn = getattr(self._app, 'get_live_audio_window', None)
        if callable(live_audio_fn):
            try:
                stream_window = live_audio_fn()
            except Exception:
                stream_window = None
        if isinstance(stream_window, tuple) and len(stream_window) == 2:
            pcm, stream_rate = stream_window
            if isinstance(pcm, np.ndarray) and pcm.size > 0 and stream_rate > 0:
                stream_features = self._extract_live_audio_features(pcm, int(stream_rate))

        row: dict[str, Any] = {}
        for key in (
            'track_id',
            'title',
            'artist',
            'album',
            'duration_s',
            'position_s',
            'progress',
        ):
            value = snapshot.get(key)
            if value is not None:
                row[key] = value

        if stream_features:
            row.update(stream_features)

        if runtime_fields:
            runtime_keys = {
                'vj_effect',
                'vj_previous_effect',
                'vj_effect_label',
                'vj_playlist_mode',
                'vj_playlist_index',
                'vj_playlist_size',
                'vj_fps',
                'vj_frame_ms',
                'vj_audio_source',
                'vj_audio_profile',
                'vj_audio_bass',
                'vj_audio_mid',
                'vj_audio_treble',
                'vj_audio_rms',
                'vj_audio_bpm',
                'vj_audio_beat',
                'vj_audio_bass_flux',
                'vj_audio_mid_flux',
                'vj_audio_fft_peak',
                'vj_audio_fft_mean',
                'vj_audio_fft_peak_bin',
                'vj_audio_waveform_peak',
                'vj_audio_waveform_rms',
                'vj_audio_waveform_mean_abs',
            }
            for key, value in runtime_fields.items():
                if value is None:
                    continue
                if key not in runtime_keys:
                    continue
                row[str(key)] = value
        row['spotify_track_id'] = track_id

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str))
            handle.write('\n')

        self._live_corpus_last_signature = signature
        return True

    @staticmethod
    def _extract_live_audio_features(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
        """Extract Essentia or fallback summary features from live PCM samples."""

        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return {}

        rms = float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
        peak = float(np.max(np.abs(samples)))
        crest_factor = float(peak / rms) if rms > 0.0 else 0.0
        duration_s = float(samples.size / max(1, sample_rate))
        bpm = 0.0
        bpm_confidence = 0.0
        beat_count = 0
        beat_density = 0.0
        danceability = 0.0
        loudness = 0.0
        key_name = 'unknown'
        scale_name = 'unknown'
        key_strength = 0.0

        try:
            import essentia.standard as es
        except Exception:
            es = None

        if es is not None:
            try:
                bpm, beats, bpm_confidence, _, _ = es.RhythmExtractor2013()(samples)
                beat_count = int(len(beats))
                beat_density = float(beat_count / duration_s) if duration_s > 0.0 else 0.0
            except Exception:
                pass
            try:
                danceability, _ = es.Danceability()(samples)
                # Clamp to [0,1] range - essentia sometimes returns values > 1.0
                danceability = float(np.clip(danceability, 0.0, 1.0))
            except Exception:
                pass
            try:
                loudness = float(es.Loudness()(samples))
            except Exception:
                pass
            try:
                key_name, scale_name, key_strength = es.KeyExtractor()(samples)
            except Exception:
                pass
        else:
            danceability = float(min(1.0, rms * 3.0))
            loudness = float(20.0 * np.log10(max(rms, 1e-6)))

        key_index = -1
        key_sin = 0.0
        key_cos = 1.0
        is_minor = 0
        key_map = {
            'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4,
            'F': 5, 'F#': 6, 'GB': 6, 'G': 7, 'G#': 8, 'AB': 8, 'A': 9,
            'A#': 10, 'BB': 10, 'B': 11,
        }
        key_index = key_map.get(str(key_name).strip().upper(), -1)
        if key_index >= 0:
            angle = (2.0 * np.pi * key_index / 12.0)
            key_sin = float(np.sin(angle))
            key_cos = float(np.cos(angle))
        if str(scale_name).strip().lower().startswith('minor'):
            is_minor = 1

        return {
            'stream_duration_s': duration_s,
            'stream_rms': rms,
            'stream_peak_amplitude': peak,
            'stream_crest_factor': crest_factor,
            'stream_loudness': loudness,
            'stream_bpm': float(bpm),
            'stream_bpm_confidence': float(bpm_confidence),
            'stream_beat_count': beat_count,
            'stream_beat_density': beat_density,
            'stream_danceability': float(danceability),
            'stream_key': key_name,
            'stream_scale': scale_name,
            'stream_key_index': key_index,
            'stream_key_sin': key_sin,
            'stream_key_cos': key_cos,
            'stream_is_minor': is_minor,
            'stream_key_strength': float(key_strength),
        }

    @staticmethod
    def _flatten_prefixed(value: Mapping[str, Any], prefix: str) -> dict[str, Any]:
        """Flatten a nested mapping into a JSON-friendly prefixed key set."""

        flattened: dict[str, Any] = {}

        def _walk(node: Mapping[str, Any], path: tuple[str, ...]) -> None:
            for key, item in node.items():
                key_text = str(key).strip().lower()
                if not key_text:
                    continue
                next_path = path + (key_text,)
                if isinstance(item, Mapping):
                    _walk(item, next_path)
                elif isinstance(item, list):
                    if not item:
                        flattened[f'{prefix}_' + '_'.join(next_path)] = []
                    elif all(not isinstance(entry, (dict, list)) for entry in item):
                        flattened[f'{prefix}_' + '_'.join(next_path)] = item
                elif item is not None:
                    flattened[f'{prefix}_' + '_'.join(next_path)] = item

        _walk(value, ())
        return flattened

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    @staticmethod
    def _track_key(track_id: str, title: str, artist: str) -> str:
        if track_id:
            return SpotifyController._canonical_track_id(track_id)
        combo = f'{artist.strip()}::{title.strip()}'.strip(':')
        return combo.lower()

    @staticmethod
    def _canonical_track_id(track_id: str) -> str:
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

    @staticmethod
    def _normalize_tags(value: Any) -> list[str]:
        items: list[str] = []
        if isinstance(value, str):
            raw = [part.strip() for part in value.replace('|', ',').split(',')]
            items = [part for part in raw if part]
        elif isinstance(value, list):
            items = [str(part).strip() for part in value if str(part).strip()]
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out
