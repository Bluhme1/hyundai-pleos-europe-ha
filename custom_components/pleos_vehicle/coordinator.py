"""Coordinator for the Pleos Vehicle Data integration."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, fields
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_conversion import DistanceConverter

from .api import PleosAuthError, PleosClient, PleosError
from .const import (
    CONF_TANK_CAPACITY,
    DEFAULT_TANK_CAPACITY,
    DOMAIN,
    KEY_FUEL_ECONOMY,
    KEY_FUEL_ECONOMY_AVERAGE,
    KEY_FUEL_ECONOMY_UNIT,
    LITRES_PER_UK_GALLON,
    MAX_ODOMETER_STEP,
    REFUEL_LEVEL_RISE,
    SCAN_INTERVAL,
    STORAGE_VERSION,
)
from .readings import fuel_level, length_unit, odometer

_LOGGER = logging.getLogger(__name__)

# Fuel economy follows the car's own unit: miles per UK gallon for a car
# showing miles, litres per 100 km for one showing kilometres.
ECONOMY_UNITS = {
    UnitOfLength.MILES: "mpg",
    UnitOfLength.KILOMETERS: "L/100km",
}


def tank_capacity_from_entry(entry: ConfigEntry) -> float:
    """Return the configured fuel tank size in litres."""
    value = entry.options.get(CONF_TANK_CAPACITY, entry.data.get(CONF_TANK_CAPACITY))
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return DEFAULT_TANK_CAPACITY


def economy_value(distance: float, litres: float, unit: str | None) -> float | None:
    """Return the distance covered per unit of fuel, in the car's own unit."""
    if unit is None or distance <= 0 or litres <= 0:
        return None
    if unit == UnitOfLength.MILES:
        return round(distance / (litres / LITRES_PER_UK_GALLON), 1)
    kilometres = DistanceConverter.convert(distance, unit, UnitOfLength.KILOMETERS)
    return round(litres / kilometres * 100, 1)


@dataclass
class FuelEconomyState:
    """Distance driven and fuel used, accumulated per vehicle.

    Kept across restarts, so the totals do not start again every time Home
    Assistant is restarted. The Pleos API has no economy figure of its own.
    """

    last_odometer: float | None = None
    last_fuel_level: float | None = None
    tank_distance: float = 0.0
    tank_fuel: float = 0.0
    average_distance: float = 0.0
    average_fuel: float = 0.0


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
        self.tank_capacity = tank_capacity_from_entry(config_entry)
        self._fuel_economy: dict[str, FuelEconomyState] = {}
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{config_entry.entry_id}")

    async def async_load_fuel_economy(self) -> None:
        """Restore the fuel economy accumulators after a restart or reload."""
        stored = await self._store.async_load()
        if not isinstance(stored, dict):
            return
        names = [field.name for field in fields(FuelEconomyState)]
        for vin, values in stored.items():
            if isinstance(values, dict):
                self._fuel_economy[vin] = FuelEconomyState(
                    **{name: values[name] for name in names if name in values}
                )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        data: dict[str, dict[str, Any]] = {}
        updated = False
        try:
            for vin in self.vehicles:
                vehicle_data = await self.client.async_get_vehicle_data(vin)
                data[vin] = {**vehicle_data, "vin": vin}
                updated = self._update_fuel_economy(vin, data[vin]) or updated
        except PleosAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PleosError as err:
            raise UpdateFailed(str(err)) from err
        if updated:
            await self._store.async_save(
                {vin: asdict(state) for vin, state in self._fuel_economy.items()}
            )
        return data

    def _update_fuel_economy(self, vin: str, data: dict[str, Any]) -> bool:
        """Add the fuel economy figures to one vehicle's data.

        Pleos reports the fuel level as a percentage and never reports litres
        burned, so economy is worked out from the distance driven and the drop
        in the fuel level since the previous update. Returns whether a reading
        was folded in.
        """
        state = self._fuel_economy.setdefault(vin, FuelEconomyState())
        unit = length_unit(data)
        data[KEY_FUEL_ECONOMY_UNIT] = ECONOMY_UNITS.get(unit) if unit else None

        current_odometer = odometer(data)
        current_level = fuel_level(data)
        if current_odometer is not None and current_level is not None:
            self._accumulate(state, current_odometer, current_level)

        data[KEY_FUEL_ECONOMY] = economy_value(state.tank_distance, state.tank_fuel, unit)
        data[KEY_FUEL_ECONOMY_AVERAGE] = economy_value(
            state.average_distance, state.average_fuel, unit
        )
        return current_odometer is not None and current_level is not None

    def _accumulate(
        self,
        state: FuelEconomyState,
        current_odometer: float,
        current_level: float,
    ) -> None:
        """Fold one reading into the accumulators.

        Most cars only upload occasionally, so a reading can cover many days of
        driving. The fuel level is quantised to one percent, but summing the
        drops telescopes, so a whole tank is accurate where a single update is
        not.
        """
        previous_odometer = state.last_odometer
        previous_level = state.last_fuel_level
        state.last_odometer = current_odometer
        state.last_fuel_level = current_level
        if previous_odometer is None or previous_level is None:
            # First reading for this vehicle: nothing to compare against yet.
            return

        distance = current_odometer - previous_odometer
        # A fall, or an implausibly large jump, is a unit change or a replaced
        # instrument cluster rather than distance driven. Skip the whole
        # interval, and carry on from the new reading.
        if not 0 <= distance <= MAX_ODOMETER_STEP:
            return

        # A rise in the level is a refill. The fuel added and the fuel burned
        # in the same interval cannot be told apart, so the interval is skipped,
        # and the tank window starts again from the new reading. A small rise
        # is rounding noise, and a drop is fuel burned.
        if previous_level - current_level <= -REFUEL_LEVEL_RISE:
            state.tank_distance = 0.0
            state.tank_fuel = 0.0
            return

        state.average_distance += distance
        state.tank_distance += distance
        level_lost = previous_level - current_level
        if level_lost > 0:
            litres = level_lost / 100 * self.tank_capacity
            state.average_fuel += litres
            state.tank_fuel += litres


type PleosConfigEntry = ConfigEntry[PleosVehicleCoordinator]
