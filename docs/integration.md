# spotify-01 Integration

Owner: Drop-in Maintainers
Status: active
Last updated: 2026-05-24

## Runtime Integration Points

- Loaded via `load_dropin_symbol('spotify-01/spotify_controller.py', 'SpotifyController')`
- Registered to app loop as subsystem `spotify`
- Registered to app loop with a legacy compatibility alias for older consumers
- Exposes `snapshot()` payload to other controllers via `vj_api.get_subsystem('spotify')`

The legacy alias exists only to preserve existing consumers while the runtime
finishes migrating to the consolidated subsystem name.

## Auto VJ Interaction

When Auto VJ and Spotify are both enabled:

- Auto VJ can hold automation while Spotify playback is paused
- Auto VJ can trigger a controlled scene change on track changes
- If Spotify is unavailable, Auto VJ behavior remains unchanged

## Independence Contract

- Core runtime has no hard dependency on spotify-01
- Failures in spotify-01 must not prevent app startup
- Auto VJ must continue to function while legacy compatibility lookups are still present
