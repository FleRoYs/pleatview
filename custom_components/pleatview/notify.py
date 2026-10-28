"""Notify entity for PleatView: on-screen notification cards."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PleatViewConfigEntry, PleatViewDevice
from .entity import PleatViewEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleatViewConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the notify entity."""
    async_add_entities([PleatViewNotifyEntity(entry.runtime_data)])


class PleatViewNotifyEntity(PleatViewEntity, NotifyEntity):
    """Sends notify.send_message to the TV."""

    _attr_name = None
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, device: PleatViewDevice) -> None:
        """Initialize the entity."""
        super().__init__(device)
        self._attr_unique_id = f"{device.device_id}_notify"

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Show a notification card on the TV."""
        await self._device.async_command("notify", message=message, title=title)
