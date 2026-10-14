"""The Pleos Vehicle Data integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import PleosClient
from .const import (
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_VEHICLES,
    DEFAULT_BRAND,
    DOMAIN,
    SERVICE_REFRESH,
)
from .coordinator import PleosConfigEntry, PleosVehicleCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Pleos Vehicle Data services."""

    async def _async_refresh(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.async_refresh()

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _async_refresh)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PleosConfigEntry) -> bool:
    """Set up Pleos Vehicle Data from a config entry."""
    client = PleosClient(
        async_get_clientsession(hass),
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        entry.data.get(CONF_BRAND, DEFAULT_BRAND),
    )
    coordinator = PleosVehicleCoordinator(
        hass, entry, client, entry.data[CONF_VEHICLES]
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PleosConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
