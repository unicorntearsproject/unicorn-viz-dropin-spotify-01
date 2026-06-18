# spotify-01

Owner: Drop-in Maintainers
Status: active
Last updated: 2026-05-24

`spotify-01` is an optional runtime subsystem that combines local Spotify
metadata polling with optional authenticated Spotify Web API context.

Current platform note: the local metadata backend is Linux-oriented because it
depends on `playerctl` talking to an MPRIS-exposing desktop player. The Web API
mode is the cross-platform path for queue, playlist, and auth-aware context.

## What It Provides

- Track metadata snapshot (`track_id`, title, artist, album, status)
- Playback timing (`duration_s`, `position_s`, progress)
- Optional per-track feature map (`bpm`, `energy`, `danceability`, `valence`)
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
