"""Integration tests against a real Dashbrr instance.

Skipped unless DASHBRR_URL and DASHBRR_API_KEY are set. Run with:
    uv run pytest -m integration

Read-only only: these tests never write to the instance -- no settings
changes, no queue deletes, no Overseerr approvals. Per-service tools only
run for services actually configured on the instance.
"""

import os

import pytest
from fastmcp import Client

import dashbrr_mcp

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.environ.get("DASHBRR_URL") and os.environ.get("DASHBRR_API_KEY")),
        reason="requires DASHBRR_URL and DASHBRR_API_KEY",
    ),
]


@pytest.fixture(autouse=True)
def configure_client():
    dashbrr_mcp._client = dashbrr_mcp.build_client(os.environ["DASHBRR_URL"], os.environ["DASHBRR_API_KEY"])
    yield


async def call(name, **kwargs):
    async with Client(dashbrr_mcp.mcp) as c:
        return await c.call_tool(name, kwargs)


def instances(settings, prefix):
    """Configured instanceIds starting with the given service prefix."""
    return [k for k in settings if k.startswith(prefix)]


async def test_get_health():
    result = await call("dashbrr_get_health")
    assert result.data["status"] == "ok"


async def test_list_settings_is_map():
    result = await call("dashbrr_list_settings")
    assert isinstance(result.data, dict)


async def test_get_ui_preferences_collapse():
    await call("dashbrr_get_ui_preferences_collapse")


async def test_health_for_configured_services():
    settings = (await call("dashbrr_list_settings")).data
    for instance_id in list(settings)[:3]:
        result = await call("dashbrr_check_service_health", service=instance_id)
        assert "status" in result.data


async def test_autobrr_endpoints_when_configured():
    settings = (await call("dashbrr_list_settings")).data
    if not instances(settings, "autobrr"):
        pytest.skip("no autobrr instance configured")
    await call("dashbrr_get_autobrr_stats", instance_id=instances(settings, "autobrr")[0])
    await call("dashbrr_get_autobrr_irc", instance_id=instances(settings, "autobrr")[0])
    await call("dashbrr_get_autobrr_releases", instance_id=instances(settings, "autobrr")[0])


async def test_summary_endpoints_when_configured():
    settings = (await call("dashbrr_list_settings")).data
    for prefix, tool in [
        ("plex", "dashbrr_get_plex_sessions"),
        ("jellyfin", "dashbrr_get_jellyfin_summary"),
        ("uptimekuma", "dashbrr_get_uptimekuma_summary"),
        ("maintainerr", "dashbrr_get_maintainerr_collections"),
        ("overseerr", "dashbrr_get_overseerr_requests"),
        ("sonarr", "dashbrr_get_sonarr_queue"),
        ("sonarr", "dashbrr_get_sonarr_stats"),
        ("radarr", "dashbrr_get_radarr_queue"),
        ("lidarr", "dashbrr_get_lidarr_queue"),
        ("readarr", "dashbrr_get_readarr_queue"),
        ("prowlarr", "dashbrr_get_prowlarr_stats"),
        ("prowlarr", "dashbrr_get_prowlarr_indexers"),
        ("traefik", "dashbrr_get_traefik_summary"),
        ("bazarr", "dashbrr_get_bazarr_summary"),
        ("sabnzbd", "dashbrr_get_sabnzbd_summary"),
        ("nzbget", "dashbrr_get_nzbget_summary"),
    ]:
        matches = instances(settings, prefix)
        if not matches:
            continue
        await call(tool, instance_id=matches[0])


async def test_tailscale_devices_when_configured():
    settings = (await call("dashbrr_list_settings")).data
    if not instances(settings, "tailscale"):
        pytest.skip("no tailscale instance configured")
    await call("dashbrr_get_tailscale_devices")
