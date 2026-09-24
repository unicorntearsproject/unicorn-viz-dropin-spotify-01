# spotify-01 Configuration

Owner: Drop-in Maintainers
Status: active
Last updated: 2026-09-24

```toml
[spotify]
enabled = false
player = "spotify"
poll_interval_s = 0.75
command_timeout_s = 0.25
now_playing_banner = true
now_playing_banner_hold_s = 10.0
[spotify.web_api]
enabled = false
client_id = ""
redirect_uri = "http://127.0.0.1:43879/callback"
scopes = [
  "user-read-playback-state",
  "user-read-currently-playing",
  "playlist-read-private",
  "playlist-read-collaborative",
]
token_store = "runtime/spotify-token.json"
poll_interval_s = 1.0
http_timeout_s = 2.0
queue_poll_every_n = 2
playlist_poll_every_n = 4
resolve_queue = true
resolve_playlist_context = true
```

## Keys

- `enabled`: Master toggle for subsystem startup.
- `player`: MPRIS player name passed to `playerctl --player=<name>`.
- `poll_interval_s`: Metadata poll cadence in seconds.
- `command_timeout_s`: Per-command timeout guard in seconds.
- `now_playing_banner`: Enables the top-pinned track-change banner.
- `now_playing_banner_hold_s`: Time in seconds before the banner slides out.

## Web API Keys

- `web_api.enabled`: Enables authenticated Spotify Web API polling.
- `web_api.client_id`: Spotify app client ID used for PKCE auth.
- `web_api.redirect_uri`: Loopback callback URI. Use `127.0.0.1`, not `localhost`.
- `web_api.scopes`: Spotify scopes to request during auth.
- `web_api.token_store`: Local token cache path.
- `web_api.poll_interval_s`: Web API poll cadence in seconds.
- `web_api.http_timeout_s`: Per-request timeout guard.
- `web_api.queue_poll_every_n`: Queue refresh divisor relative to the main Web API poll.
- `web_api.playlist_poll_every_n`: Playlist-context refresh divisor.
- `web_api.resolve_queue`: Enables `/me/player/queue` polling.
- `web_api.resolve_playlist_context`: Enables playlist detail lookups.

Spotify carries nothing training-related: live training capture belongs to
Auto VJ's own corpus writers (see training-kit-01), configured on the config
editor's Logging tab.

The live Spotify runtime no longer depends on Spotify's deprecated audio-
features endpoints.
