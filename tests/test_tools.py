"""Offline tests: one per Dashbrr API endpoint, plus auth/error-path tests.

No network. Each tool call is checked against the exact HTTP request it should
produce (method, path incl. URL-encoding, query params, JSON body) via
httpx.MockTransport, using FastMCP's in-memory Client (see
https://gofastmcp.com/development/tests).
"""

import json

import httpx
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.exceptions import ToolError

import dashbrr_mcp


class Recorder:
    """Captures the single request made during a test and replays a canned response."""

    def __init__(self):
        self.method = None
        self.url = None
        self.headers = None
        self.params = None
        self.json = None
        self.response = httpx.Response(200, json={"success": True})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.method = request.method
        self.url = request.url
        self.headers = request.headers
        self.params = request.url.params
        self.json = json.loads(request.content) if request.content else None
        return self.response


@pytest.fixture
def recorder():
    return Recorder()


@pytest_asyncio.fixture
async def server(recorder, monkeypatch):
    transport = httpx.MockTransport(recorder.handler)
    client = dashbrr_mcp.build_client("https://dashbrr.example.com", "test-session-token", transport=transport)
    monkeypatch.setattr(dashbrr_mcp, "_client", client)
    yield dashbrr_mcp.mcp
    await client.aclose()


_OP_GROUP = {op: group for group, ops in dashbrr_mcp._GROUPS.items() for op in ops}


async def call(server, name, **kwargs):
    """Call `name` (an operation name) through the portmanteau group tool
    that now hosts it, so every existing per-operation test keeps working
    unmodified aside from this helper."""
    async with Client(server) as c:
        return await c.call_tool(_OP_GROUP[name], {"operation": name, "arguments": kwargs})


# --- discovery & config --------------------------------------------------------

async def test_1_list_settings(server, recorder):
    await call(server, "dashbrr_list_settings")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/settings"


async def test_2_get_ui_preferences_collapse(server, recorder):
    await call(server, "dashbrr_get_ui_preferences_collapse")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/ui/preferences/collapse"


# --- health --------------------------------------------------------------------

async def test_3_get_health(server, recorder):
    await call(server, "dashbrr_get_health")
    assert recorder.method == "GET"
    assert recorder.url.path == "/health"


async def test_4_check_service_health(server, recorder):
    await call(server, "dashbrr_check_service_health", service="sonarr-1")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/health/sonarr-1"


async def test_4b_check_service_health_sends_url_and_key(server, recorder):
    await call(server, "dashbrr_check_service_health", service="sonarr-1", url="http://sonarr:8989", api_key="sekrit")
    assert recorder.url.path == "/api/health/sonarr-1"
    assert recorder.params["url"] == "http://sonarr:8989"
    assert recorder.params["apiKey"] == "sekrit"


# --- plex ----------------------------------------------------------------------

async def test_5_create_plex_pin(server, recorder):
    recorder.response = httpx.Response(200, json={"id": 1, "code": "1234"})
    await call(server, "dashbrr_create_plex_pin")
    assert recorder.method == "POST"
    assert recorder.url.path == "/api/plex/auth/pin"


async def test_6_get_plex_pin(server, recorder):
    await call(server, "dashbrr_get_plex_pin", pin_id=1234)
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/plex/auth/pin/1234"


async def test_7_get_plex_sessions(server, recorder):
    await call(server, "dashbrr_get_plex_sessions", instance_id="plex-main")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/plex/sessions"
    assert recorder.params["instanceId"] == "plex-main"


# --- autobrr -------------------------------------------------------------------

async def test_8_get_autobrr_stats(server, recorder):
    await call(server, "dashbrr_get_autobrr_stats", instance_id="autobrr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/autobrr/stats"
    assert recorder.params["instanceId"] == "autobrr-0"


async def test_9_get_autobrr_irc(server, recorder):
    recorder.response = httpx.Response(200, json=[])
    result = await call(server, "dashbrr_get_autobrr_irc", instance_id="autobrr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/autobrr/irc"
    assert result.data == []


async def test_10_get_autobrr_releases(server, recorder):
    await call(server, "dashbrr_get_autobrr_releases", instance_id="autobrr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/autobrr/releases"
    assert recorder.params["instanceId"] == "autobrr-0"


# --- media / infra summaries ---------------------------------------------------

async def test_11_get_jellyfin_summary(server, recorder):
    await call(server, "dashbrr_get_jellyfin_summary", instance_id="jellyfin-main")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/jellyfin/summary"
    assert recorder.params["instanceId"] == "jellyfin-main"


async def test_12_get_uptimekuma_summary(server, recorder):
    await call(server, "dashbrr_get_uptimekuma_summary", instance_id="uptimekuma-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/uptimekuma/summary"
    assert recorder.params["instanceId"] == "uptimekuma-0"


async def test_13_get_maintainerr_collections(server, recorder):
    recorder.response = httpx.Response(200, json=[])
    result = await call(server, "dashbrr_get_maintainerr_collections", instance_id="maintainerr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/maintainerr/collections"
    assert result.data == []


async def test_14_get_overseerr_requests(server, recorder):
    await call(server, "dashbrr_get_overseerr_requests", instance_id="overseerr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/overseerr/requests"
    assert recorder.params["instanceId"] == "overseerr-0"


async def test_15_get_traefik_summary(server, recorder):
    await call(server, "dashbrr_get_traefik_summary", instance_id="traefik-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/traefik/summary"
    assert recorder.params["instanceId"] == "traefik-0"


async def test_16_get_bazarr_summary(server, recorder):
    await call(server, "dashbrr_get_bazarr_summary", instance_id="bazarr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/bazarr/summary"
    assert recorder.params["instanceId"] == "bazarr-0"


async def test_17_get_sabnzbd_summary(server, recorder):
    await call(server, "dashbrr_get_sabnzbd_summary", instance_id="sabnzbd-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/sabnzbd/summary"
    assert recorder.params["instanceId"] == "sabnzbd-0"


async def test_18_get_nzbget_summary(server, recorder):
    await call(server, "dashbrr_get_nzbget_summary", instance_id="nzbget-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/nzbget/summary"
    assert recorder.params["instanceId"] == "nzbget-0"


# --- arr queues ---------------------------------------------------------------

async def test_19_get_sonarr_queue(server, recorder):
    await call(server, "dashbrr_get_sonarr_queue", instance_id="sonarr-1")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/sonarr/queue"
    assert recorder.params["instanceId"] == "sonarr-1"


async def test_20_get_sonarr_stats(server, recorder):
    await call(server, "dashbrr_get_sonarr_stats", instance_id="sonarr-1")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/sonarr/stats"
    assert recorder.params["instanceId"] == "sonarr-1"


async def test_21_get_radarr_queue(server, recorder):
    await call(server, "dashbrr_get_radarr_queue", instance_id="radarr-1")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/radarr/queue"
    assert recorder.params["instanceId"] == "radarr-1"


async def test_22_get_lidarr_queue(server, recorder):
    await call(server, "dashbrr_get_lidarr_queue", instance_id="lidarr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/lidarr/queue"
    assert recorder.params["instanceId"] == "lidarr-0"


async def test_23_get_readarr_queue(server, recorder):
    await call(server, "dashbrr_get_readarr_queue", instance_id="readarr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/readarr/queue"
    assert recorder.params["instanceId"] == "readarr-0"


async def test_24_get_prowlarr_stats(server, recorder):
    await call(server, "dashbrr_get_prowlarr_stats", instance_id="prowlarr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/prowlarr/stats"
    assert recorder.params["instanceId"] == "prowlarr-0"


async def test_25_get_prowlarr_indexers(server, recorder):
    recorder.response = httpx.Response(200, json=[])
    result = await call(server, "dashbrr_get_prowlarr_indexers", instance_id="prowlarr-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/prowlarr/indexers"
    assert result.data == []


async def test_26_get_tailscale_devices(server, recorder):
    recorder.response = httpx.Response(200, json={"devices": [], "status": "success"})
    result = await call(server, "dashbrr_get_tailscale_devices", instance_id="tailscale-0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/tailscale/devices"
    assert recorder.params["instanceId"] == "tailscale-0"
    assert result.data == {"devices": [], "status": "success"}


async def test_26b_tailscale_accepts_raw_api_key(server, recorder):
    recorder.response = httpx.Response(200, json={"devices": [], "status": "success"})
    await call(server, "dashbrr_get_tailscale_devices", api_key="tskey-secret")
    assert recorder.params["apiKey"] == "tskey-secret"
    assert "instanceId" not in recorder.params


async def test_26c_tailscale_with_neither_picks_first_instance(server, recorder):
    recorder.response = httpx.Response(200, json={"devices": [], "status": "success"})
    await call(server, "dashbrr_get_tailscale_devices")
    assert "instanceId" not in recorder.params
    assert "apiKey" not in recorder.params


# --- write: queue deletes ------------------------------------------------------

@pytest.mark.parametrize(
    ("tool", "path", "instance"),
    [
        ("dashbrr_delete_sonarr_queue_item", "/api/sonarr/queue/42", "sonarr-1"),
        ("dashbrr_delete_radarr_queue_item", "/api/radarr/queue/42", "radarr-1"),
        ("dashbrr_delete_lidarr_queue_item", "/api/lidarr/queue/42", "lidarr-0"),
        ("dashbrr_delete_readarr_queue_item", "/api/readarr/queue/42", "readarr-0"),
    ],
)
async def test_27_30_queue_deletes(server, recorder, tool, path, instance):
    recorder.response = httpx.Response(204)
    await call(server, tool, instance_id=instance, id=42)
    assert recorder.method == "DELETE"
    assert recorder.url.path == path
    assert recorder.params["instanceId"] == instance
    assert "removeFromClient" not in recorder.params


async def test_31_queue_delete_options_sent_only_when_true(server, recorder):
    recorder.response = httpx.Response(204)
    await call(
        server,
        "dashbrr_delete_sonarr_queue_item",
        instance_id="sonarr-1",
        id=42,
        remove_from_client=True,
        blocklist=True,
    )
    assert recorder.params["removeFromClient"] == "true"
    assert recorder.params["blocklist"] == "true"
    assert "skipRedownload" not in recorder.params
    assert "changeCategory" not in recorder.params


# --- write: overseerr ----------------------------------------------------------

async def test_32_set_overseerr_request_status(server, recorder):
    recorder.response = httpx.Response(204)
    await call(server, "dashbrr_set_overseerr_request_status", instance_id="overseerr-0", request_id=7, status="2")
    assert recorder.method == "POST"
    assert recorder.url.path == "/api/services/overseerr-0/overseerr/request/7/2"


async def test_32b_overseerr_invalid_status_rejected(server, recorder):
    recorder.response = httpx.Response(204)
    with pytest.raises(ToolError, match="status"):
        await call(server, "dashbrr_set_overseerr_request_status", instance_id="overseerr-0", request_id=7, status="1")
    assert recorder.method is None


# --- write: settings & ui ------------------------------------------------------

async def test_33_save_settings(server, recorder):
    recorder.response = httpx.Response(200, json={"instanceId": "sonarr-1"})
    result = await call(
        server,
        "dashbrr_save_settings",
        instance="sonarr-1",
        display_name="Sonarr",
        url="http://sonarr:8989",
        api_key="sekrit",
        access_url="https://sonarr.example.com",
    )
    assert recorder.method == "POST"
    assert recorder.url.path == "/api/settings/sonarr-1"
    assert recorder.json == {
        "displayName": "Sonarr",
        "url": "http://sonarr:8989",
        "apiKey": "sekrit",
        "accessUrl": "https://sonarr.example.com",
    }
    assert result.data == {"instanceId": "sonarr-1"}


async def test_33b_save_settings_omits_api_key_when_blank(server, recorder):
    recorder.response = httpx.Response(200, json={"instanceId": "sonarr-1"})
    await call(
        server,
        "dashbrr_save_settings",
        instance="sonarr-1",
        display_name="Sonarr",
        url="http://sonarr:8989",
    )
    assert recorder.json == {"displayName": "Sonarr", "url": "http://sonarr:8989"}
    assert "apiKey" not in recorder.json
    assert "accessUrl" not in recorder.json


async def test_34_delete_settings(server, recorder):
    recorder.response = httpx.Response(204)
    await call(server, "dashbrr_delete_settings", instance="sonarr-1")
    assert recorder.method == "DELETE"
    assert recorder.url.path == "/api/settings/sonarr-1"


async def test_35_set_ui_preference_collapse(server, recorder):
    recorder.response = httpx.Response(204)
    await call(server, "dashbrr_set_ui_preference_collapse", key="sonarr-1", collapsed=True)
    assert recorder.method == "PUT"
    assert recorder.url.path == "/api/ui/preferences/collapse"
    assert recorder.json == {"key": "sonarr-1", "collapsed": True}


# --- auth header --------------------------------------------------------------

async def test_token_sent_as_bearer_header(server, recorder):
    await call(server, "dashbrr_list_settings")
    assert recorder.headers["authorization"] == "Bearer test-session-token"


async def test_no_token_means_no_authorization_header(recorder, monkeypatch):
    transport = httpx.MockTransport(recorder.handler)
    client = dashbrr_mcp.build_client("https://dashbrr.example.com", None, transport=transport)
    monkeypatch.setattr(dashbrr_mcp, "_client", client)
    await call(dashbrr_mcp.mcp, "dashbrr_list_settings")
    assert "authorization" not in recorder.headers
    await client.aclose()


# --- error paths ---------------------------------------------------------------

async def test_401_error_surfaces_status(server, recorder):
    recorder.response = httpx.Response(401, json={"message": "Unauthorized"})
    with pytest.raises(ToolError, match="401"):
        await call(server, "dashbrr_list_settings")


async def test_404_error_message_reaches_caller(server, recorder):
    recorder.response = httpx.Response(404, json={"message": "service not found"})
    with pytest.raises(ToolError, match="service not found"):
        await call(server, "dashbrr_check_service_health", service="sonarr-1")


async def test_429_rate_limit_surfaces_status(server, recorder):
    recorder.response = httpx.Response(429, json={"message": "Rate limit exceeded"})
    with pytest.raises(ToolError, match="429"):
        await call(server, "dashbrr_list_settings")


async def test_non_json_error_body_does_not_crash(server, recorder):
    recorder.response = httpx.Response(502, text="<html>Bad Gateway</html>")
    with pytest.raises(ToolError, match="502"):
        await call(server, "dashbrr_list_settings")


# --- main() ----------------------------------------------------------------

def test_main_requires_dashbrr_url(monkeypatch):
    monkeypatch.delenv("DASHBRR_URL", raising=False)
    with pytest.raises(SystemExit):
        dashbrr_mcp.main()


# --- portmanteau grouping safety net --------------------------------------------

def test_all_operations_grouped():
    """Every entry in _OP_GROUP came from _GROUPS; assert no duplicates and
    that every group name resolves to a real module-level function - this is
    the safety net for the group-tool consolidation."""
    grouped_names = [n for names in dashbrr_mcp._GROUPS.values() for n in names]
    assert len(grouped_names) == len(set(grouped_names))
    for n in grouped_names:
        assert hasattr(dashbrr_mcp, n), f"{n} not found in dashbrr_mcp module"


async def test_group_tools_are_the_only_registered_tools(server):
    async with Client(server) as c:
        tools = await c.list_tools()
    assert {t.name for t in tools} == set(dashbrr_mcp._GROUPS)


async def test_unknown_operation_rejected_by_schema(server):
    # The Literal[...] enum on `operation` means an invalid value never
    # reaches _register_group's dispatch body - pydantic rejects it first.
    with pytest.raises(ToolError, match="validation error"):
        async with Client(server) as c:
            await c.call_tool("dashbrr_health", {"operation": "not_a_real_operation"})
