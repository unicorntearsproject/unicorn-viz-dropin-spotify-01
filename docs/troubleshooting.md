# spotify-01 Troubleshooting

Owner: Drop-in Maintainers
Status: active
Last updated: 2026-06-05

## Subsystem Not Loading

- Confirm `[spotify].enabled = true`.
- Verify `playerctl` is installed (`command -v playerctl`).
- Check app logs for `SpotifyController` warnings.

### Windows Note

- `spotify-01` is not currently a Windows-native backend.
- The current implementation shells out to `playerctl`, which expects an
	MPRIS-compatible media player session.
- On Windows, that means there is no single missing package to install and be
	done; the missing piece is a Windows media-session backend implementation.
- For Windows today, prefer `[spotify.web_api]` if authenticated Spotify Web API
	data satisfies the use case.

## Web API Auth Not Ready

- Confirm `[spotify.web_api].enabled = true`.
- Confirm `client_id` is set.
- Confirm the configured redirect URI exactly matches the Spotify app settings.
- Clear the token file and re-run auth if the cached token is stale or revoked.

## No Track Metadata

- Ensure Spotify desktop app is running.
- Confirm MPRIS player name matches `[spotify].player`.
- Try `playerctl --player=spotify metadata` manually.

## Auto VJ Not Reacting To Track Changes

- Confirm Auto VJ is enabled.
- Confirm Spotify status is `playing` (not paused/stopped).
- Check Auto VJ decision logs for `*_SPOTIFY` effect swap markers.

## Features File Ignored

- Ensure path exists and JSON is valid.
- Keys are canonicalized automatically, but the safest form is `spotify:track:<id>`.
- The controller also accepts raw MPRIS ids such as `/com/spotify/track/<id>`.
