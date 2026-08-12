# AGENTS.md — dashbrr-mcp

MCP server exposing [Dashbrr](https://github.com/autobrr/dashbrr)'s REST API as
tools so an LLM can read and manage a dashbrr instance: configured services,
per-service health, and summary panels for autobrr, Plex, Jellyfin, Sonarr,
Radarr, Lidarr, Readarr, Prowlarr, Overseerr, Traefik, Bazarr, SABnzbd, NZBGet,
Uptime Kuma, Maintainerr, and Tailscale. Uses FastMCP, `uv` for deps.

Exposed as **5 resource-scoped portmanteau tools**, not one tool per endpoint — see "Portmanteau registration" below. A prior version registered all 34 endpoints individually; that blew the MCP context budget (~34 tools × ~250 tokens ≈ 9k tokens just for this one server) and has been retired.

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
GET endpoints were originally marked `readOnlyHint=True`; write endpoints
(settings POST/DELETE, ui preferences PUT, queue DELETEs, overseerr request
POST, plex auth PIN POST) were `destructiveHint=True`. Keep the whole
server in `dashbrr_mcp.py` unless it outgrows it. Base path `/api` is
hardcoded in `build_client` (only the root liveness probe `GET /health`
bypasses it).

## Portmanteau registration — **do not go back to one tool per endpoint**
- `_GROUPS` near the bottom of `dashbrr_mcp.py` buckets every endpoint function into one of 5 resource groups (`dashbrr_settings`, `dashbrr_health`, `dashbrr_plex`, `dashbrr_arr_queues`, `dashbrr_other_services`). Unlike most other refactored servers here, this grouping is per-*service* rather than per-*resource*, since Dashbrr's endpoint shape is one summary/action per third-party service rather than a single domain with CRUD verbs. `_register_tools()` registers exactly one MCP tool per group via `_register_group`, which wraps the group's functions in a single `dispatch(operation, arguments)` closure. The endpoint functions themselves are unchanged — they're plain callables looked up by name via `globals()`, not separately-registered tools.
- `operation` is typed `Literal[<the group's function names>]`, so FastMCP/pydantic validates it against the real operation list before `dispatch` ever runs — an invalid operation never reaches the group tool's body.
- `dispatch`'s return type is `JSONVal | str | None` (not bare `JSONVal`): several delete/set operations (`dashbrr_delete_sonarr_queue_item` and its radarr/lidarr/readarr siblings, `dashbrr_set_overseerr_request_status`, `dashbrr_delete_settings`, `dashbrr_set_ui_preference_collapse`) return `None` on success. Narrowing the union breaks FastMCP's structured-content validation for those.
- Adding a new endpoint: write the function as before (no decorator), then add its name to exactly one group in `_GROUPS`. `tests/test_tools.py::test_all_operations_grouped` fails if a name doesn't resolve to a real module attribute.
- New resource area big enough to need its own group (rare): add a new `_GROUPS` key. Keep the total group count at or under ~15 — that ceiling is the entire point of this pattern.
- If you're tempted to add a per-endpoint `@mcp.tool` decorator back, don't — every endpoint must be reachable only via its group's `operation` enum. A 34-tool server (one per endpoint) previously cost ~9k tokens of system-prompt budget on every session start; the 5-tool grouped version costs roughly a tenth of that.
- Annotations: a group tool is `readOnlyHint=True` (`READONLY`) only when *every* operation in it was originally read-only (tracked in `_register_tools()`'s `readonly_names` set). Mixed groups carry no hints.
