"""Base entity for PleatView."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import PleatViewDevice


class PleatViewEntity(Entity):
    """An entity backed by a TV's pushed state."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: PleatViewDevice) -> None:
        """Initialize the entity."""
        self._device = device
        info = device.info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            name=device.name,
            manufacturer=info.get("manufacturer") or "PleatView",
            model=info.get("model"),
            sw_version=info.get("app_version"),
            configuration_url=device.client.base_url,
        )

    @property
    def available(self) -> bool:
        """Return whether the TV is connected."""
        return self._device.available

    async def async_added_to_hass(self) -> None:
        """Follow state pushed by the TV."""
        self.async_on_remove(self._device.async_add_listener(self.async_write_ha_state))
