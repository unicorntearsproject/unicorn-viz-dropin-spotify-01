# spotify-01 Web API Auth Prep

Owner: Drop-in Maintainers
Status: active
Last updated: 2026-06-07

## Goal

Prepare everything needed to use the authenticated Spotify Web API mode inside
`spotify-01`.

## What You Need To Do (Operator / Account Owner)

### 1. Create a Spotify Developer App

- Go to Spotify Developer Dashboard.
- Create an app for Unicorn Viz integration.
- Save the Client ID.
- Do not put a Client Secret into runtime config.

## 2. Configure Redirect URI(s)

Add the local auth callback redirect URI:

- `http://127.0.0.1:43879/callback`

Notes:

- Redirect URI must match exactly in Spotify app settings and runtime config.
- Use `127.0.0.1`, not `localhost`.

## 3. Approve Required Scopes

Minimum for playback/queue intelligence:

- `user-read-playback-state`
- `user-read-currently-playing`
- `playlist-read-private`
- `playlist-read-collaborative`

## 4. Validate Account + Playback Preconditions

- Spotify desktop app installed and signed in.
- Active playback device available during testing.
- Network access available to Spotify API endpoints.

## Initial Runtime Config Sketch

```toml
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
resolve_playlist_context = true
resolve_queue = true
```

## Acceptance Checklist

- [ ] Spotify app created
- [ ] Client ID captured
- [ ] Redirect URI added exactly
- [ ] Scope set approved
- [ ] Test account/device ready