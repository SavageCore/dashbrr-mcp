# dashbrr-mcp

Part of the [arr-mcps](https://github.com/SavageCore/arr-mcps) collection.
MCP server exposing [Dashbrr](https://github.com/autobrr/dashbrr)'s REST API as
tools, so an LLM can read **and manage** a dashbrr instance: configured
services, per-service health, and the summary panels for autobrr, Plex,
Jellyfin, Sonarr, Radarr, Lidarr, Readarr, Prowlarr, Overseerr, Traefik,
Bazarr, SABnzbd, NZBGet, Uptime Kuma, Maintainerr, and Tailscale. Write tools
cover settings management, download-queue deletes, Overseerr approvals, UI
preferences, and the Plex auth PIN flow.

Built with [FastMCP](https://gofastmcp.com).

## Auth

Dashbrr uses **session auth**, not an API key. Two ways to use this server:

- Run dashbrr with `DASHBRR_AUTH_BYPASS=true` — the API treats any caller as
  the builtin user. Set `DASHBRR_API_KEY` to any value (or leave it unset; the
  server still starts and no auth header is sent).
- Obtain a session token (e.g. extract the `dashbrr_user_session` cookie after
  logging in to the UI) and set `DASHBRR_API_KEY` to it — it is sent as
  `Authorization: Bearer <token>`.

## Install

Download a wheel from the [latest release](https://github.com/SavageCore/dashbrr-mcp/releases/latest)
and install it as a `uv` tool (no repo checkout needed):

```bash
uv tool install dashbrr_mcp-*.whl
```

This puts a `dashbrr-mcp` command on your PATH. Register it with Claude Code:

```bash
claude mcp add dashbrr \
  --env DASHBRR_URL=https://your-dashbrr-host \
  --env DASHBRR_API_KEY=<token-or-empty> \
  -- dashbrr-mcp
```

### From source

```bash
uv sync
cp .env.example .env   # fill in DASHBRR_URL and optionally DASHBRR_API_KEY
```

```bash
claude mcp add dashbrr \
  --env DASHBRR_URL=https://your-dashbrr-host \
  --env DASHBRR_API_KEY=<token-or-empty> \
  -- uv run --directory /path/to/dashbrr-mcp dashbrr-mcp
```

## Config

| Env var | Required | Default |
|---|---|---|
| `DASHBRR_URL` | yes | - |
| `DASHBRR_API_KEY` | no | none (no auth header sent; requires `DASHBRR_AUTH_BYPASS=true` on the instance) |

## Tools

One tool per Dashbrr API endpoint. Per-service tools take `instance_id`, the
type-prefixed instance id from `dashbrr_list_settings` (e.g. `sonarr-1`,
`plex-main`, `autobrr-0`).

### Read-only

| Tool | Endpoint |
|---|---|
| `dashbrr_list_settings` | `GET /api/settings` |
| `dashbrr_get_ui_preferences_collapse` | `GET /api/ui/preferences/collapse` |
| `dashbrr_get_health` | `GET /health` |
| `dashbrr_check_service_health` | `GET /api/health/{service}` |
| `dashbrr_get_plex_pin` | `GET /api/plex/auth/pin/{pinId}` |
| `dashbrr_get_plex_sessions` | `GET /api/plex/sessions` |
| `dashbrr_get_autobrr_stats` | `GET /api/autobrr/stats` |
| `dashbrr_get_autobrr_irc` | `GET /api/autobrr/irc` |
| `dashbrr_get_autobrr_releases` | `GET /api/autobrr/releases` |
| `dashbrr_get_jellyfin_summary` | `GET /api/jellyfin/summary` |
| `dashbrr_get_uptimekuma_summary` | `GET /api/uptimekuma/summary` |
| `dashbrr_get_maintainerr_collections` | `GET /api/maintainerr/collections` |
| `dashbrr_get_overseerr_requests` | `GET /api/overseerr/requests` |
| `dashbrr_get_sonarr_queue` | `GET /api/sonarr/queue` |
| `dashbrr_get_sonarr_stats` | `GET /api/sonarr/stats` |
| `dashbrr_get_radarr_queue` | `GET /api/radarr/queue` |
| `dashbrr_get_lidarr_queue` | `GET /api/lidarr/queue` |
| `dashbrr_get_readarr_queue` | `GET /api/readarr/queue` |
| `dashbrr_get_prowlarr_stats` | `GET /api/prowlarr/stats` |
| `dashbrr_get_prowlarr_indexers` | `GET /api/prowlarr/indexers` |
| `dashbrr_get_traefik_summary` | `GET /api/traefik/summary` |
| `dashbrr_get_bazarr_summary` | `GET /api/bazarr/summary` |
| `dashbrr_get_sabnzbd_summary` | `GET /api/sabnzbd/summary` |
| `dashbrr_get_nzbget_summary` | `GET /api/nzbget/summary` |
| `dashbrr_get_tailscale_devices` | `GET /api/tailscale/devices` |

### Write / destructive

| Tool | Endpoint |
|---|---|
| `dashbrr_create_plex_pin` | `POST /api/plex/auth/pin` |
| `dashbrr_delete_sonarr_queue_item` | `DELETE /api/sonarr/queue/{id}` |
| `dashbrr_delete_radarr_queue_item` | `DELETE /api/radarr/queue/{id}` |
| `dashbrr_delete_lidarr_queue_item` | `DELETE /api/lidarr/queue/{id}` |
| `dashbrr_delete_readarr_queue_item` | `DELETE /api/readarr/queue/{id}` |
| `dashbrr_set_overseerr_request_status` | `POST /api/services/{instanceId}/overseerr/request/{requestId}/{status}` |
| `dashbrr_save_settings` | `POST /api/settings/{instance}` |
| `dashbrr_delete_settings` | `DELETE /api/settings/{instance}` |
| `dashbrr_set_ui_preference_collapse` | `PUT /api/ui/preferences/collapse` |

`dashbrr_set_overseerr_request_status` takes `status` as the literal string
`2` (approve) or `3` (decline). Queue deletes only send options
(`remove_from_client`, `blocklist`, `skip_redownload`, `change_category`) when
set to true. `dashbrr_save_settings` omits `api_key` when blank so the stored
key is retained on update.

## Development

```bash
make help  # list all commands
```

| Command | Does |
|---|---|
| `make sync` | `uv sync` |
| `make test` | Offline tests - one per endpoint, mocked HTTP |
| `make test-integration` | Tests against the live instance (needs `DASHBRR_URL`/`DASHBRR_API_KEY`) |
| `make build` | Build wheel + sdist into `dist/` |
| `make bump-patch` / `bump-minor` / `bump-major` | Bump the version in `pyproject.toml` + `uv.lock` |
| `make clean` | Remove build artifacts |

The release workflow (`.github/workflows/release.yml`) builds and publishes to
[Releases](https://github.com/SavageCore/dashbrr-mcp/releases) whenever a `v*`
tag is pushed - so the usual flow is `make bump-patch`, commit, then tag and
push.

The integration suite is read-only and never writes to your instance.
