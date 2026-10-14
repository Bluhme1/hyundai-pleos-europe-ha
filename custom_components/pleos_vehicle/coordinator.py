"""Coordinator for the Pleos Vehicle Data integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PleosAuthError, PleosClient, PleosError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class PleosVehicleCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls Pleos for every vehicle on the API key."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: PleosClient,
        vehicles: list[dict[str, Any]],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.vehicles: dict[str, dict[str, Any]] = {v["vin"]: v for v in vehicles}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        data: dict[str, dict[str, Any]] = {}
        try:
            for vin in self.vehicles:
                vehicle_data = await self.client.async_get_vehicle_data(vin)
                data[vin] = {**vehicle_data, "vin": vin}
        except PleosAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PleosError as err:
            raise UpdateFailed(str(err)) from err
        return data


type PleosConfigEntry = ConfigEntry[PleosVehicleCoordinator]
