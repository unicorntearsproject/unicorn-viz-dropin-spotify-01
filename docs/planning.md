# spotify-01 Planning

Owner: Drop-in Maintainers
Status: active
Last updated: 2026-06-07

## Purpose

Track the current scope of the consolidated `spotify-01` subsystem and the
remaining follow-up work now that local metadata and authenticated Web API
context live in one drop-in.

## Current State

`spotify-01` now provides two optional data paths:

- Local now-playing metadata via `playerctl` / MPRIS
- Authenticated Spotify Web API context via PKCE + loopback callback

Current runtime surface includes:

- Track title/artist/album/status/progress
- Optional local per-track feature metadata from a JSON file
- Auth status and token health
- Current playback payload from `/me/player`
- Optional queue data from `/me/player/queue`
- Optional playlist-context resolution for playlist playback
- Compatibility registration for legacy consumers

## Design Constraints

- Local metadata mode must remain live-safe and optional
- Web API mode must remain optional and degrade gracefully
- Auto VJ and other consumers must not need simultaneous migration work
- Queue and playlist lookups must be treated as enhancements, not hard startup requirements

## Near-Term Follow-Up

### 1. Consumer migration

- Move remaining runtime consumers to the consolidated `spotify` naming
- Remove compatibility aliases once all consumers are migrated intentionally

### 2. UI consolidation

- Rename remaining HUD/internal status labels that still reflect the legacy split
- Decide whether queue and playlist context should appear in Control Room directly

### 3. Windows strategy

- Keep Web API mode as the primary cross-platform path
- Add a real Windows media-session backend later if local desktop metadata remains important there

### 4. API hardening

- Handle rate limits more explicitly in operator-facing status
- Refine token-health and retry messaging
- Consider a narrower, normalized snapshot for downstream automation consumers

## Data Model Direction

The consolidated snapshot should continue to expose lightweight local metadata
plus optional auth-aware extensions:

- `available`
- `is_playing`
- `status`
- `track_id`
- `title`
- `artist`
- `album`
- `duration_s`
- `position_s`
- `progress`
- local features/tags
- `web_api_enabled`
- `auth_ready`
- `auth_status`
- `token_expires_in_s`
- `playback`
- `queue`
- `queue_len`
- `playlist_context`

## Product Notes

- Queue answers what is likely to play soon.
- Playlist context answers what broader source is active.
- Auto VJ should prefer queue data over playlist order whenever both exist.

See also: `web-api-auth-prep.md` for operator/developer setup prerequisites.
