# spotify-01

Owner: Drop-in Maintainers
Version: 1.0.0-rc.12
Status: active
Last updated: 2026-09-24

`spotify-01` is an optional runtime subsystem that combines local Spotify
metadata polling with optional authenticated Spotify Web API context.

Current platform note: the local metadata backend is Linux-oriented because it
depends on `playerctl` talking to an MPRIS-exposing desktop player. The Web API
mode is the cross-platform path for queue, playlist, and auth-aware context.

## What It Provides

- Track metadata snapshot (`track_id`, title, artist, album, status)
- Playback timing (`duration_s`, `position_s`, progress)
- Top-pinned now-playing banner for new tracks when enabled in config
- Optional PKCE auth, playback context, queue, and playlist metadata via
	Spotify Web API

## Dependencies

- `playerctl` must be installed and available on `PATH` for local metadata mode
- Spotify desktop client (or compatible MPRIS player name) for local metadata mode
- Spotify Developer app + Client ID for Web API mode

## Installer

This drop-in ships a bundle installer script at `install.sh`.

```bash
bash install.sh --root ~/.local/share/unicorn-viz
```

The installer copies the bundle into `~/.local/share/unicorn-viz/drop-ins/spotify-01`
and refuses to run if `playerctl` is missing. Use `--uninstall` to remove the
bundle again.

## Configuration

See `docs/configuration.md`.

## Integration

- Registers as subsystem name `spotify` via `vj_api.register_subsystem`
- Auto VJ can consume this subsystem when both are enabled

## Planning

See `docs/planning.md` for the current roadmap of the consolidated subsystem.

For operator setup prerequisites, see `docs/web-api-auth-prep.md`.

## Troubleshooting

See `docs/troubleshooting.md`.

## Changelog

- **1.0.0-rc.12** — The **Web API client ID** row moves to the config editor's new **System** tab (off Performance).
- **1.0.0-rc.11** — Everything training-related is gone: the **live corpus file** row and its `[spotify] live_corpus_file` key, the corpus writer (`record_live_corpus_snapshot`, retired since Auto VJ's sequence writer took over), its audio-feature extractor, and helpers left over from the July feature-map removal. Live training capture is Auto VJ's alone.
- **1.0.0-rc.10** — The live corpus file row moves to the config editor's **Logging** tab.
- **1.0.0-rc.9** — Config editor rows for the Web API **client ID** (masked, with SHOW) and the **live corpus file** path; both apply on the next launch and move a value set in config.toml into the menu (core 1.0.0-beta.172).
- **1.0.0-rc.8** — Local poll, Web API poll, Web API fallback and HTTP timeout join the core config editor's Performance tab (live, remembered across runs by core).
- **1.0.0-rc.7** — The "player unavailable" branch of the local poll commits its state under the same lock as the live branch (2026-09-05 audit O5); unused test imports removed.
- **1.0.0-rc.6** — The local playerctl poll (two subprocess spawns every
  0.75 s: metadata + position) runs on a `spotify-playerctl` worker instead
  of the render thread; the poll's results are committed under the state
  lock so `snapshot()` never reads a half-updated track.
- **1.0.0-rc.5** — Control Room panel moves to the shared `sources` page (owner decision, 2026-09-05) and is unregistered in `shutdown()` so a mid-session stop never leaves a dead panel behind.
- **1.0.0-rc.4** — **Control Room panel, P2 of
  `docs/planning/control-room-panel-registry-plan-2026-09-04.md`.**
  Registers a declarative `Spotify` panel via `vj_api.register_operator_panel()`
  (guarded, degrades to no panel on an older core), replacing Control
  Room's hardcoded panel, which reached in via
  `vj_api.get_subsystem('spotify')` + `getattr` duck typing. The panel
  shows status/track/auth plus a playback-progress meter, all read
  through `snapshot()` like every other integration; AUTH and LOGOUT
  buttons call `begin_auth_async()`/`logout()` directly. 7 new tests.
- **1.0.0-rc.3** — HTTP 429 handling per the Spotify API rules: honor `Retry-After`, exponential backoff (capped 120 s) when absent, and skip requests locally while rate-limited; token store now written 0600 (refresh token was world-readable). 5 regression tests.
- **1.0.0-rc.2** — Register with the core **now-playing announcement hub**
  (`vj_api.register_now_playing`, priority 10, ambient) instead of being
  hard-wired in `app.py`; the same banner/HUD machinery now serves Spotify,
  the media player, and the DJ mixer.  Guarded no-op on older cores.

- **1.0.0-rc.1** — initial versioned release.
