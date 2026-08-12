# AGENTS.md — dashbrr-mcp

MCP server exposing [Dashbrr](https://github.com/autobrr/dashbrr)'s REST API as
tools so an LLM can read and manage a dashbrr instance: configured services,
per-service health, and summary panels for autobrr, Plex, Jellyfin, Sonarr,
Radarr, Lidarr, Readarr, Prowlarr, Overseerr, Traefik, Bazarr, SABnzbd, NZBGet,
Uptime Kuma, Maintainerr, and Tailscale. Uses FastMCP, `uv` for deps.

## Testing
- Offline suite: `make test` (or `uv run pytest`)
- Live integration (needs `DASHBRR_URL`/`DASHBRR_API_KEY`): `make test-integration`

## Release workflow
Always use the `make bump-*` targets to bump the version (`uv version --bump patch|minor|major`), which updates `pyproject.toml` and `uv.lock` together. Do NOT edit the version by hand.

- Bump: `make bump-patch` (or `bump-minor` / `bump-major`)
- Commit message is **just the version**, e.g. `0.1.2` — nothing else.
- Tag it `v<version>` (e.g. `v0.1.2`).
- Push main and the tag:
  ```
  git push origin main
  git push origin v<version>
  ```
- Then sync the project copy:
  ```
  cd /home/savagecore/Documents/christopfarr/mcp/dashbrr-mcp
  git fetch origin && git reset --hard origin/main
  ```
- Deploy to the Proxmox host (root SSH key): pull the repo then reinstall the uv tool:
  ```
  ssh root@192.168.50.3 -- 'cd /root/dashbrr-mcp && git fetch origin && git reset --hard origin/main'
  ssh root@192.168.50.3 -- 'cd /root/dashbrr-mcp && uv tool install --force .'
  ```
  The host runs it via `uv tool install` → `/root/.local/bin/dashbrr-mcp` (not from the repo).

## Auth
Dashbrr uses session auth, not an API key. The instance must run with
`DASHBRR_AUTH_BYPASS=true`, or `DASHBRR_API_KEY` must hold a session token
(`dashbrr_user_session` cookie value). It is sent as `Authorization: Bearer
<token>`; if unset, no auth header is sent and the server relies on auth bypass.

## Read/write note
Unlike the tracearr server, the Dashbrr API has a write surface. Read-only
GET endpoints get `readOnlyHint=True`; write endpoints (settings POST/DELETE,
ui preferences PUT, queue DELETEs, overseerr request POST, plex auth PIN POST)
get `destructiveHint=True` and must never be marked read-only. Keep the whole
server in `dashbrr_mcp.py` unless it outgrows it; add tools one per endpoint
with the `dashbrr_` prefix. Base path `/api` is hardcoded in `build_client`
(only the root liveness probe `GET /health` bypasses it).
