"""Tests for the PleatView config and options flows."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import patch

from custom_components.pleatview.const import (
    AUTH_MANAGED,
    AUTH_NONE,
    AUTH_TOKEN,
    CONF_ALLOW_CONTROL,
    CONF_AUTH_MODE,
    CONF_HA_TOKEN,
    CONF_TOKEN,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .conftest import make_entry
from .fake_tv import FakeTV

SETUP = "custom_components.pleatview.async_setup_entry"


def discovery(tv: FakeTV, **properties: str) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address("127.0.0.1"),
        ip_addresses=[ip_address("127.0.0.1")],
        hostname="living-room-tv.local.",
        name="Living Room TV._pleatview._tcp.local.",
        port=tv.port,
        type="_pleatview._tcp.local.",
        properties={"id": "tv-1", "api": "1", **properties},
    )


async def _pair(hass: HomeAssistant, flow_id: str, tv: FakeTV) -> dict:
    result = await hass.config_entries.flow.async_configure(flow_id, {"pin": "000000"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_pin"}
    result = await hass.config_entries.flow.async_configure(flow_id, {"pin": tv.pin})
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "dashboard_auth"
    return result


async def test_user_flow(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake_tv.port}
    )
    assert result["step_id"] == "pair"
    await _pair(hass, result["flow_id"], fake_tv)
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "auth_none"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room TV"
    assert result["result"].unique_id == "tv-1"
    assert result["data"][CONF_AUTH_MODE] == AUTH_NONE
    assert result["data"][CONF_TOKEN] in fake_tv.tokens


async def test_user_flow_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_flow_managed_user(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery(fake_tv)
    )
    assert result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"]["name"] == "Living Room TV"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "pair"
    await _pair(hass, result["flow_id"], fake_tv)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "auth_managed"})
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ALLOW_CONTROL: False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTH_MODE] == AUTH_MANAGED
    assert result["data"][CONF_ALLOW_CONTROL] is False


async def test_zeroconf_updates_moved_tv(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    entry = make_entry(fake_tv)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_HOST: "10.0.0.99"})
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery(fake_tv)
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "127.0.0.1"


async def test_zeroconf_without_id(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    info = discovery(fake_tv)
    info.properties.pop("id")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_ZEROCONF}, data=info)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_discovery_info"


async def test_token_mode_validates_token(hass: HomeAssistant, fake_tv: FakeTV, hass_access_token: str) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake_tv.port}
    )
    await _pair(hass, result["flow_id"], fake_tv)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "auth_token"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HA_TOKEN: "nonsense"})
    assert result["errors"] == {CONF_HA_TOKEN: "invalid_ha_token"}
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HA_TOKEN: hass_access_token})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTH_MODE] == AUTH_TOKEN
    assert result["data"][CONF_HA_TOKEN] == hass_access_token


async def test_options_flow(hass: HomeAssistant, fake_tv: FakeTV) -> None:
    entry = make_entry(fake_tv)
    entry.add_to_hass(hass)
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "init"
        defaults = {
            "kiosk": "full", "zoom": 100, "rotate_seconds": 0, "return_home_minutes": 0,
            "reload_minutes": 0, "keep_screen_on": True, "launch_on_boot": True,
        }
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**defaults, "ha_url": "ha.local:8123"}
        )
        assert result["errors"] == {"ha_url": "invalid_url"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**defaults, "zoom": 75, "dashboards": "Cams = /dashboard-cams"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["zoom"] == 75
    assert entry.options["dashboards"] == "Cams = /dashboard-cams"
