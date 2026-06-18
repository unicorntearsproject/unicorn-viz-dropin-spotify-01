# Spotify Drop-in — Security & Token Threat Model

Owner: Studio Documentation
Status: active
Last updated: 2026-06-18

---

## Auth flow

The drop-in uses **Authorization Code with PKCE** (RFC 7636).  No Client
Secret is ever required or stored.  Only a `client_id` is needed — sourced
from `config.toml [spotify.web] client_id`, or the environment variables
`UNICORNVIZ_SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_ID` as fallbacks.

```
User presses Ctrl+Alt+S
  → SpotifyController.begin_auth_async()
  → generates 64-byte PKCE verifier (secrets.token_urlsafe)
  → derives SHA-256 code_challenge
  → opens browser to accounts.spotify.com/authorize?code_challenge=...
  → starts one-shot loopback HTTP server on 127.0.0.1:<port>
  → Spotify redirects to http://127.0.0.1:<port>/callback?code=...
  → server extracts code, shuts itself down
  → exchanges code + verifier for access_token + refresh_token (PKCE)
  → persists token JSON to runtime/spotify-token.json
```

---

## Token storage

| Property | Detail |
|----------|--------|
| Default path | `runtime/spotify-token.json` (relative to repo root) |
| Configurable | `[spotify.web] token_store = /path/to/file` |
| Absolute paths | Accepted as-is |
| Relative paths | Resolved relative to the repo root (not CWD) |
| File mode | Created by Python `open('w')` — inherits umask (typically `0o644`) |
| Contents | `access_token`, `refresh_token`, `expires_at` (Unix epoch float) |
| Gitignore | `runtime/` is gitignored; token file must never be committed |

**Recommended hardening:** set `0o600` manually or via operator setup script:

```bash
chmod 600 runtime/spotify-token.json
```

The controller does not currently call `chmod` itself — this is a known gap
(see Gaps section below).

---

## Refresh logic

- Expiry checked with a 30-second skew (`_token_expired(skew_s=30.0)`).
- `_refresh_access_token()` is called automatically before each API request
  when the token is within 30 s of expiry.
- On 401 from the API, one refresh attempt is made before surfacing the error.
- On refresh failure the controller transitions to `auth_status = 'needs_auth'`
  and surfaces a flash message; it does not loop or hammer the token endpoint.

---

## Redirect URI

The loopback redirect URI is `http://127.0.0.1:<dynamic_port>/callback`.
A random available port is selected at auth-start time.  The Spotify app
dashboard must list `http://127.0.0.1` as an allowed redirect URI (wildcard
port) — see `operations.md` for dashboard setup instructions.

`http://localhost` is **not used** (avoids DNS rebinding edge cases on some
systems).  Wildcard redirect URIs are **not used**.

---

## Scopes

Requested scopes are minimal:

| Scope | Why |
|-------|-----|
| `user-read-playback-state` | Current track, playback status |
| `user-read-currently-playing` | Now-playing metadata for HUD |

No write scopes, no library modification scopes, no social scopes.

---

## Rate limiting

- HTTP 429 is handled: `Retry-After` header is honoured; the controller backs
  off and does not retry in a tight loop.
- Polling interval is config-driven (`[spotify.web] poll_interval_s`, default
  5 s) so operators can reduce API pressure on slow connections.

---

## Threat model

### T1 — Token file readable by other local users  
**Likelihood:** Low on a single-user workstation.  
**Impact:** An attacker with local access could read `access_token` /
`refresh_token` and call the Spotify API as the owner.  
**Mitigations:** gitignore prevents accidental commit; operator should
`chmod 600 runtime/spotify-token.json`.  Future improvement: auto-chmod on
write (see Gaps).

### T2 — PKCE verifier in memory during auth  
**Likelihood:** Negligible (verifier lives only for the duration of the
loopback server thread, then is discarded).  
**Impact:** If process memory were dumped mid-auth, the verifier could be
extracted.  
**Mitigation:** Standard PKCE risk; accepted.

### T3 — Loopback server window  
**Likelihood:** Very low on a desktop workstation.  
**Impact:** Another local process could race to hit the loopback callback URL
before Spotify redirects.  
**Mitigation:** The server is one-shot and shuts down immediately after
receiving one request; the PKCE code_verifier is still required to exchange
the code, so stealing the code alone is insufficient.

### T4 — Client ID exposed in config.toml  
**Likelihood:** Low (config.toml is gitignored for local overrides; the
public TOML in the repo has no real credentials).  
**Impact:** A leaked client_id allows an attacker to initiate their own PKCE
flow impersonating the app — but they still need the user to complete the
browser auth step.  
**Mitigation:** Client ID is not a secret in the OAuth 2.0 PKCE model.
Treat it as semi-public; never commit a real client_id to the repo.

### T5 — No Client Secret  
**By design.** PKCE eliminates the need for a Client Secret in the local
runtime.  No secret is ever stored, logged, or transmitted.

---

## Gaps (known, owner-tracked)

| ID | Gap | Priority |
|----|-----|----------|
| G1 | Token file not auto-chmod'd to 0o600 on write | Low |
| G2 | `access_token` appears in debug log at DEBUG level if log level is set to DEBUG | Low |
| G3 | No token revocation on logout — `runtime/spotify-token.json` is deleted but the refresh_token is not explicitly revoked at `accounts.spotify.com/api/token/revoke` | Low |

---

## See also

- [operations.md](operations.md) — Spotify dashboard setup, auth walkthrough
- [configuration.md](configuration.md) — `[spotify.web]` config reference
- [web-api-auth-prep.md](web-api-auth-prep.md) — PKCE implementation notes
