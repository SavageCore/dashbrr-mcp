"""MCP server exposing the Dashbrr REST API (https://github.com/autobrr/dashbrr) as tools.

One tool per endpoint (see README for the full list). The dashbrr API is
session-authenticated, not API-key authenticated: either the instance runs with
DASHBRR_AUTH_BYPASS=true (treats any caller as the builtin user) or a session
token obtained from a prior login is supplied. This server sends whatever token
it is given as `Authorization: Bearer <DASHBRR_API_KEY>` and lets the instance
decide.

Unlike the tracearr server, this API has a write surface (settings, queue
deletes, overseerr requests, ui preferences, plex auth) -- those tools are
marked destructiveHint and not readOnlyHint.

Base path `/api` is hardcoded in build_client; only the root liveness probe
`/health` bypasses it.
"""

import os
import sys
from typing import Any
from urllib.parse import quote

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

READONLY = ToolAnnotations(readOnlyHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)

# Dashbrr responses are plain JSON. `dict[str, Any]` (not bare `Any`) matters
# here: FastMCP needs a concrete schema to build MCP structured content, and
# skips that step entirely for an `Any` return type -- which silently makes
# Client.call_tool's `.data` come back None for any tool returning a JSON array.
JSONObj = dict[str, Any]
JSONVal = JSONObj | list[Any]

mcp = FastMCP("dashbrr-mcp")

_client: httpx.AsyncClient | None = None
_base_url: str = ""


def build_client(base_url: str, api_key: str | None, transport: httpx.BaseTransport | None = None) -> httpx.AsyncClient:
    global _base_url
    _base_url = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return httpx.AsyncClient(base_url=f"{_base_url}/api", headers=headers, transport=transport)


async def _req(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    root: bool = False,
) -> JSONVal | None:
    assert _client is not None, "client not configured"
    url = f"{_base_url}{path}" if root else path
    r = await _client.request(method, url, params=params, json=json_body)
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except (ValueError, AttributeError):
            msg = r.text
        raise ToolError(f"Dashbrr API {r.status_code}: {msg}")
    if r.status_code == 204 or not r.content:
        return None
    return r.json()


def _seg(value: str | int) -> str:
    """URL-encode a path segment (service/instance ids, queue ids)."""
    return quote(str(value), safe="")


def _omit(params: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose values are empty/None so the API's defaults apply."""
    return {k: v for k, v in params.items() if v not in ("", None)}


def _queue_delete_opts(**flags: bool) -> dict[str, str]:
    """Queue-delete options are only meaningful when explicitly `true`."""
    return {name: "true" for name, on in flags.items() if on}


# --- discovery & config -------------------------------------------------------

@mcp.tool(annotations=READONLY)
async def dashbrr_list_settings() -> JSONObj:
    """List every configured service on the dashbrr instance, keyed by
    instanceId (e.g. `sonarr-1`, `plex-main`, `autobrr-0`). API keys are
    stripped from the response. Use the instanceId keys here as the
    instance_id argument to the per-service tools."""
    return await _req("GET", "/settings")


@mcp.tool(annotations=READONLY)
async def dashbrr_get_ui_preferences_collapse() -> JSONObj:
    """Current UI collapse preferences (which dashboard panels are collapsed)
    for the authenticated user."""
    return await _req("GET", "/ui/preferences/collapse")


# --- health -------------------------------------------------------------------

@mcp.tool(annotations=READONLY)
async def dashbrr_get_health() -> JSONObj:
    """Liveness probe for the dashbrr instance itself (not any monitored
    service). Returns {"status": "ok"} when up."""
    return await _req("GET", "/health", root=True)


@mcp.tool(annotations=READONLY)
async def dashbrr_check_service_health(service: str, url: str = "", api_key: str = "") -> JSONObj:
    """Run a health check for one configured service. `service` is the full
    instanceId (e.g. `sonarr-1`, `plex-main`). Optionally pass `url` and
    `api_key` to test an as-yet-unsaved service configuration; leave both
    empty to check the stored one."""
    return await _req(
        "GET",
        f"/health/{_seg(service)}",
        _omit({"url": url, "apiKey": api_key}),
    )


# --- plex ---------------------------------------------------------------------

@mcp.tool(annotations=WRITE)
async def dashbrr_create_plex_pin() -> JSONObj:
    """Start a Plex authentication flow: create a Plex PIN. Returns the pin id
    and code; poll it with dashbrr_get_plex_pin until it carries an authToken."""
    return await _req("POST", "/plex/auth/pin")


@mcp.tool(annotations=READONLY)
async def dashbrr_get_plex_pin(pin_id: int) -> JSONObj:
    """Poll the status of a Plex PIN created with dashbrr_create_plex_pin.
    Once the pin has been authorised (has an authToken), the Plex auth flow
    is complete."""
    return await _req("GET", f"/plex/auth/pin/{_seg(pin_id)}")


@mcp.tool(annotations=READONLY)
async def dashbrr_get_plex_sessions(instance_id: str) -> JSONObj:
    """Active Plex playback sessions. `instance_id` must be type-prefixed,
    e.g. `plex-main`."""
    return await _req("GET", "/plex/sessions", _omit({"instanceId": instance_id}))


# --- autobrr ------------------------------------------------------------------

@mcp.tool(annotations=READONLY)
async def dashbrr_get_autobrr_stats(instance_id: str) -> JSONObj:
    """autobrr release counters: total/filtered/rejected/approved/error
    counts. `instance_id` must be type-prefixed, e.g. `autobrr-0`."""
    return await _req("GET", "/autobrr/stats", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_autobrr_irc(instance_id: str) -> list[Any]:
    """autobrr IRC networks and their health (name/healthy/enabled).
    `instance_id` must be type-prefixed, e.g. `autobrr-0`."""
    return await _req("GET", "/autobrr/irc", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_autobrr_releases(instance_id: str) -> JSONObj:
    """Recent autobrr releases (data array, count, next_cursor).
    `instance_id` must be type-prefixed, e.g. `autobrr-0`."""
    return await _req("GET", "/autobrr/releases", _omit({"instanceId": instance_id}))


# --- media / infra summaries ---------------------------------------------------

@mcp.tool(annotations=READONLY)
async def dashbrr_get_jellyfin_summary(instance_id: str) -> JSONObj:
    """Jellyfin system info plus active sessions (play state, now playing
    item, transcoding). `instance_id` must be type-prefixed, e.g.
    `jellyfin-main`."""
    return await _req("GET", "/jellyfin/summary", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_uptimekuma_summary(instance_id: str) -> JSONObj:
    """Uptime Kuma monitor summary. `instance_id` must be type-prefixed,
    e.g. `uptimekuma-0`."""
    return await _req("GET", "/uptimekuma/summary", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_maintainerr_collections(instance_id: str) -> list[Any]:
    """Maintainerr collections (id, title, isActive, deleteAfterDays,
    mediaCount). `instance_id` must be type-prefixed, e.g. `maintainerr-0`."""
    return await _req("GET", "/maintainerr/collections", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_overseerr_requests(instance_id: str) -> JSONObj:
    """Pending Overseerr media requests (pendingCount + request list with
    media and requester info). `instance_id` must be type-prefixed, e.g.
    `overseerr-0`."""
    return await _req("GET", "/overseerr/requests", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_traefik_summary(instance_id: str) -> JSONObj:
    """Traefik router/service/middleware overview, flagged issue routers, and
    certificate summary. `instance_id` must be type-prefixed, e.g.
    `traefik-0`."""
    return await _req("GET", "/traefik/summary", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_bazarr_summary(instance_id: str) -> JSONObj:
    """Bazarr badges, subtitle provider statuses, and health issues.
    `instance_id` must be type-prefixed, e.g. `bazarr-0`."""
    return await _req("GET", "/bazarr/summary", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_sabnzbd_summary(instance_id: str) -> JSONObj:
    """SABnzbd queue plus recent failures. `instance_id` must be
    type-prefixed, e.g. `sabnzbd-0`."""
    return await _req("GET", "/sabnzbd/summary", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_nzbget_summary(instance_id: str) -> JSONObj:
    """NZBGet queue, status, and recent failures. `instance_id` must be
    type-prefixed, e.g. `nzbget-0`."""
    return await _req("GET", "/nzbget/summary", _omit({"instanceId": instance_id}))


# --- arr queues ---------------------------------------------------------------

@mcp.tool(annotations=READONLY)
async def dashbrr_get_sonarr_queue(instance_id: str) -> JSONObj:
    """Sonarr download queue (paged records with series/episode info).
    `instance_id` must be type-prefixed, e.g. `sonarr-1`."""
    return await _req("GET", "/sonarr/queue", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_sonarr_stats(instance_id: str) -> JSONObj:
    """Sonarr queue-derived stats plus server version: {stats, version}.
    `instance_id` must be type-prefixed, e.g. `sonarr-1`."""
    return await _req("GET", "/sonarr/stats", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_radarr_queue(instance_id: str) -> JSONObj:
    """Radarr download queue (paged records with movie info).
    `instance_id` must be type-prefixed, e.g. `radarr-1`."""
    return await _req("GET", "/radarr/queue", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_lidarr_queue(instance_id: str) -> JSONObj:
    """Lidarr download queue. `instance_id` must be type-prefixed, e.g.
    `lidarr-0`."""
    return await _req("GET", "/lidarr/queue", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_readarr_queue(instance_id: str) -> JSONObj:
    """Readarr download queue. `instance_id` must be type-prefixed, e.g.
    `readarr-0`."""
    return await _req("GET", "/readarr/queue", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_prowlarr_stats(instance_id: str) -> JSONObj:
    """Prowlarr grab/fail counts and indexer count. `instance_id` must be
    type-prefixed, e.g. `prowlarr-0`."""
    return await _req("GET", "/prowlarr/stats", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_prowlarr_indexers(instance_id: str) -> list[Any]:
    """Prowlarr indexer list (id, name, enable, priority, response time,
    grab/query counts). `instance_id` must be type-prefixed, e.g.
    `prowlarr-0`."""
    return await _req("GET", "/prowlarr/indexers", _omit({"instanceId": instance_id}))


@mcp.tool(annotations=READONLY)
async def dashbrr_get_tailscale_devices(instance_id: str = "", api_key: str = "") -> list[Any]:
    """Tailscale devices on the tailnet. Pass either `instance_id` (a
    type-prefixed tailscale instance from the settings) or a raw Tailscale
    `api_key`; if neither is given the first tailscale-configured instance is
    used."""
    return await _req(
        "GET",
        "/tailscale/devices",
        _omit({"instanceId": instance_id, "apiKey": api_key}),
    )


# --- write: queue deletes ------------------------------------------------------

@mcp.tool(annotations=WRITE)
async def dashbrr_delete_sonarr_queue_item(
    instance_id: str,
    id: int,
    remove_from_client: bool = False,
    blocklist: bool = False,
    skip_redownload: bool = False,
    change_category: bool = False,
) -> None:
    """Delete an item from the Sonarr download queue. `id` is the queue
    record id (from dashbrr_get_sonarr_queue). `instance_id` must be
    type-prefixed, e.g. `sonarr-1`. Options are only applied when set to
    true: remove_from_client (delete the download from the client),
    blocklist (add the release to the blocklist), skip_redownload, and
    change_category."""
    await _req(
        "DELETE",
        f"/sonarr/queue/{_seg(id)}",
        _omit(
            {
                "instanceId": instance_id,
                **_queue_delete_opts(
                    removeFromClient=remove_from_client,
                    blocklist=blocklist,
                    skipRedownload=skip_redownload,
                    changeCategory=change_category,
                ),
            }
        ),
    )


@mcp.tool(annotations=WRITE)
async def dashbrr_delete_radarr_queue_item(
    instance_id: str,
    id: int,
    remove_from_client: bool = False,
    blocklist: bool = False,
    skip_redownload: bool = False,
    change_category: bool = False,
) -> None:
    """Delete an item from the Radarr download queue. `id` is the queue
    record id (from dashbrr_get_radarr_queue). `instance_id` must be
    type-prefixed, e.g. `radarr-1`. Options (remove_from_client, blocklist,
    skip_redownload, change_category) are only applied when set to true."""
    await _req(
        "DELETE",
        f"/radarr/queue/{_seg(id)}",
        _omit(
            {
                "instanceId": instance_id,
                **_queue_delete_opts(
                    removeFromClient=remove_from_client,
                    blocklist=blocklist,
                    skipRedownload=skip_redownload,
                    changeCategory=change_category,
                ),
            }
        ),
    )


@mcp.tool(annotations=WRITE)
async def dashbrr_delete_lidarr_queue_item(
    instance_id: str,
    id: int,
    remove_from_client: bool = False,
    blocklist: bool = False,
    skip_redownload: bool = False,
    change_category: bool = False,
) -> None:
    """Delete an item from the Lidarr download queue. `id` is the queue
    record id (from dashbrr_get_lidarr_queue). `instance_id` must be
    type-prefixed, e.g. `lidarr-0`. Options (remove_from_client, blocklist,
    skip_redownload, change_category) are only applied when set to true."""
    await _req(
        "DELETE",
        f"/lidarr/queue/{_seg(id)}",
        _omit(
            {
                "instanceId": instance_id,
                **_queue_delete_opts(
                    removeFromClient=remove_from_client,
                    blocklist=blocklist,
                    skipRedownload=skip_redownload,
                    changeCategory=change_category,
                ),
            }
        ),
    )


@mcp.tool(annotations=WRITE)
async def dashbrr_delete_readarr_queue_item(
    instance_id: str,
    id: int,
    remove_from_client: bool = False,
    blocklist: bool = False,
    skip_redownload: bool = False,
    change_category: bool = False,
) -> None:
    """Delete an item from the Readarr download queue. `id` is the queue
    record id (from dashbrr_get_readarr_queue). `instance_id` must be
    type-prefixed, e.g. `readarr-0`. Options (remove_from_client, blocklist,
    skip_redownload, change_category) are only applied when set to true."""
    await _req(
        "DELETE",
        f"/readarr/queue/{_seg(id)}",
        _omit(
            {
                "instanceId": instance_id,
                **_queue_delete_opts(
                    removeFromClient=remove_from_client,
                    blocklist=blocklist,
                    skipRedownload=skip_redownload,
                    changeCategory=change_category,
                ),
            }
        ),
    )


# --- write: overseerr ----------------------------------------------------------

@mcp.tool(annotations=WRITE)
async def dashbrr_set_overseerr_request_status(instance_id: str, request_id: int, status: str) -> None:
    """Approve or decline a pending Overseerr media request. `instance_id`
    must be type-prefixed, e.g. `overseerr-0`. `request_id` comes from
    dashbrr_get_overseerr_requests. `status` is `2` (approve) or `3`
    (decline)."""
    if status not in ("2", "3"):
        raise ToolError("status must be '2' (approve) or '3' (decline)")
    await _req(
        "POST",
        f"/services/{_seg(instance_id)}/overseerr/request/{_seg(request_id)}/{_seg(status)}",
    )


# --- write: settings & ui ------------------------------------------------------

@mcp.tool(annotations=WRITE)
async def dashbrr_save_settings(
    instance: str,
    display_name: str,
    url: str,
    api_key: str = "",
    access_url: str = "",
) -> JSONObj | None:
    """Create or update a service configuration on the dashbrr instance.
    `instance` is the type-prefixed instanceId (e.g. `sonarr-1`). `api_key`
    is the upstream service's key -- write-only: omit it (or leave blank) to
    keep the existing key when updating. `access_url` is the URL clients
    should use to reach the service (optional)."""
    body: dict[str, Any] = {"displayName": display_name, "url": url}
    if api_key:
        body["apiKey"] = api_key
    if access_url:
        body["accessUrl"] = access_url
    return await _req("POST", f"/settings/{_seg(instance)}", json_body=body)


@mcp.tool(annotations=WRITE)
async def dashbrr_delete_settings(instance: str) -> None:
    """Delete a service configuration from the dashbrr instance. `instance`
    is the type-prefixed instanceId (e.g. `sonarr-1`). This removes the
    service from the dashboard -- use dashbrr_list_settings first."""
    await _req("DELETE", f"/settings/{_seg(instance)}")


@mcp.tool(annotations=WRITE)
async def dashbrr_set_ui_preference_collapse(key: str, collapsed: bool) -> None:
    """Set whether a dashboard panel is collapsed for the authenticated user.
    `key` identifies the panel; `collapsed` toggles its state."""
    await _req(
        "PUT",
        "/ui/preferences/collapse",
        json_body={"key": key, "collapsed": collapsed},
    )


def main() -> None:
    global _client
    url = os.environ.get("DASHBRR_URL")
    if not url:
        print("DASHBRR_URL environment variable is required (e.g. https://dashbrr.example.com)", file=sys.stderr)
        raise SystemExit(1)
    api_key = os.environ.get("DASHBRR_API_KEY")
    if not api_key:
        print(
            "Warning: DASHBRR_API_KEY is unset. The dashbrr instance must run with "
            "DASHBRR_AUTH_BYPASS=true or you must supply a session token.",
            file=sys.stderr,
        )
    _client = build_client(url, api_key)
    mcp.run()


if __name__ == "__main__":
    main()
