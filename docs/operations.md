# spotify-01 Operations

Owner: Drop-in Maintainers
Status: active
Last updated: 2026-06-18

## Runtime Behavior

- Polls `playerctl` on a throttled interval (default `0.75s`)
- Polls Spotify Web API when `[spotify.web_api].enabled = true`
- Updates metadata/auth snapshot for other controllers
- Supports `Ctrl+Alt+S` to begin auth and `Ctrl+Alt+Shift+S` to clear local auth
- Can stream live training rows to `[spotify].live_corpus_file` while a set is
	running
- Use `tools/training/` for offline corpus generation and backfills

## Startup Expectations

- If `[spotify].enabled = false`, subsystem is skipped
- If `playerctl` is missing, local metadata mode self-disables gracefully
- If `[spotify.web_api].enabled = true` but no client ID is configured, Web API mode stays disabled gracefully

## Shutdown

- No external process is spawned; shutdown is a no-op
