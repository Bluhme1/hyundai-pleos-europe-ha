"""Sensor platform for the Pleos Vehicle Data integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import PleosConfigEntry, PleosVehicleCoordinator
from .entity import PleosVehicleEntity, dig

LENGTH_UNITS = {
    "km": UnitOfLength.KILOMETERS,
    "mile": UnitOfLength.MILES,
    "miles": UnitOfLength.MILES,
    "meter": UnitOfLength.METERS,
    "feet": UnitOfLength.FEET,
}
TEMPERATURE_UNITS = {
    "C": UnitOfTemperature.CELSIUS,
    "F": UnitOfTemperature.FAHRENHEIT,
}
PRESSURE_UNITS = {
    "psi": UnitOfPressure.PSI,
    "kpa": UnitOfPressure.KPA,
    "bar": UnitOfPressure.BAR,
}
TIMESTAMP_BLOCKS = ("batteries", "driving", "powertrains", "status", "locations")


@dataclass(frozen=True, kw_only=True)
class PleosSensorEntityDescription(SensorEntityDescription):
    """Describes a Pleos sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    unit_fn: Callable[[dict[str, Any]], str | None] | None = None


def _timestamp(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _last_updated(data: dict[str, Any]) -> datetime | None:
    stamps = [_timestamp(dig(data, name, "timestamp")) for name in TIMESTAMP_BLOCKS]
    known = [stamp for stamp in stamps if stamp is not None]
    return max(known) if known else None


def _range_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the usable distance-to-empty entries Pleos reports."""
    entries = dig(data, "powertrains", "distanceToEmpties")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if _entry_value(entry) is not None]


def _entry_value(entry: Any) -> int | None:
    if not isinstance(entry, dict):
        return None
    try:
        return int(entry["value"])
    except (KeyError, TypeError, ValueError):
        return None


def _fuel_range_entry(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the petrol driving range entry.

    A plug-in hybrid reports several ``PHEV`` entries with no ``ICE``/``HEV``
    one, so the largest of them is the petrol range.
    """
    entries = _range_entries(data)
    for entry in entries:
        if entry.get("type") in ("ICE", "HEV"):
            return entry
    plug_in = [entry for entry in entries if entry.get("type") == "PHEV"]
    if plug_in:
        return max(plug_in, key=_entry_value)
    return None


def _ev_range_entry(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the electric driving range entry.

    A plug-in hybrid reports several ``PHEV`` entries with no ``EV`` one, so
    the smallest of them is the electric range.
    """
    entries = _range_entries(data)
    for entry in entries:
        if entry.get("type") == "EV":
            return entry
    plug_in = [entry for entry in entries if entry.get("type") == "PHEV"]
    if len(plug_in) > 1:
        return min(plug_in, key=_entry_value)
    return None


def _fuel_range_value(data: dict[str, Any]) -> int | None:
    return _entry_value(_fuel_range_entry(data))


def _ev_range_value(data: dict[str, Any]) -> int | None:
    return _entry_value(_ev_range_entry(data))


def _range_unit(entry: dict[str, Any] | None) -> str | None:
    return LENGTH_UNITS.get(entry.get("unit")) if entry else None


def _fuel_range_unit(data: dict[str, Any]) -> str | None:
    return _range_unit(_fuel_range_entry(data))


def _ev_range_unit(data: dict[str, Any]) -> str | None:
    return _range_unit(_ev_range_entry(data))


def _tire_value(row: int, side: str) -> Callable[[dict[str, Any]], float | None]:
    def _value(data: dict[str, Any]) -> float | None:
        raw = dig(data, "status", "tire", row, side)
        unit = dig(data, "status", "tire", row, "unit")
        if not isinstance(raw, (int, float)) or raw == 255:
            return None
        if unit == "kpa":
            return raw * 5
        if unit == "bar":
            return raw / 10
        return raw

    return _value


def _tire_unit(row: int) -> Callable[[dict[str, Any]], str | None]:
    def _unit(data: dict[str, Any]) -> str | None:
        return PRESSURE_UNITS.get(dig(data, "status", "tire", row, "unit"))

    return _unit


SENSORS: tuple[PleosSensorEntityDescription, ...] = (
    PleosSensorEntityDescription(
        key="vehicle_identification_number",
        translation_key="vehicle_identification_number",
        value_fn=lambda data: data.get("vin"),
    ),
    PleosSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        # No device_class, so the odometer stays in the car's own unit
        # (miles here) instead of being converted into the system unit.
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: dig(data, "driving", "odometer", "value"),
        unit_fn=lambda data: LENGTH_UNITS.get(
            dig(data, "driving", "odometer", "unit")
        ),
    ),
    PleosSensorEntityDescription(
        key="fuel_level",
        translation_key="fuel_level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: dig(data, "powertrains", "engine", "fuelLevel"),
    ),
    PleosSensorEntityDescription(
        key="fuel_driving_range",
        translation_key="fuel_driving_range",
        # No device_class: with one, Home Assistant converts the value into the
        # configured length unit (km here). Pleos reports the car's own unit,
        # so leave the value and unit exactly as the car reports them.
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_fuel_range_value,
        unit_fn=_fuel_range_unit,
    ),
    PleosSensorEntityDescription(
        key="ev_driving_range",
        translation_key="ev_driving_range",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_ev_range_value,
        unit_fn=_ev_range_unit,
    ),
    PleosSensorEntityDescription(
        key="ev_battery_percentage",
        translation_key="ev_battery_percentage",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: dig(data, "batteries", "charge", "stateOfCharge"),
    ),
    PleosSensorEntityDescription(
        key="ev_estimated_current_charge_duration",
        translation_key="ev_estimated_current_charge_duration",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda data: dig(data, "batteries", "charge", "remainTime"),
    ),
    PleosSensorEntityDescription(
        key="ev_target_range_charge_ac",
        translation_key="charge_target_ac",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: dig(
            data, "batteries", "charge", "targetStateOfCharge", "standard"
        ),
    ),
    PleosSensorEntityDescription(
        key="ev_target_range_charge_dc",
        translation_key="charge_target_dc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: dig(
            data, "batteries", "charge", "targetStateOfCharge", "quick"
        ),
    ),
    PleosSensorEntityDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: dig(data, "status", "outsideTemperature", "value"),
        unit_fn=lambda data: TEMPERATURE_UNITS.get(
            dig(data, "status", "outsideTemperature", "unit")
        ),
    ),
    PleosSensorEntityDescription(
        key="air_temperature",
        translation_key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: dig(
            data, "status", "climateControl", "temperature", "value"
        ),
        unit_fn=lambda data: TEMPERATURE_UNITS.get(
            dig(data, "status", "climateControl", "temperature", "unit")
        ),
    ),
    PleosSensorEntityDescription(
        key="tire_pressure_front_left",
        translation_key="tire_pressure_front_left",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_tire_value(0, "left"),
        unit_fn=_tire_unit(0),
    ),
    PleosSensorEntityDescription(
        key="tire_pressure_front_right",
        translation_key="tire_pressure_front_right",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_tire_value(0, "right"),
        unit_fn=_tire_unit(0),
    ),
    PleosSensorEntityDescription(
        key="tire_pressure_rear_left",
        translation_key="tire_pressure_rear_left",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_tire_value(1, "left"),
        unit_fn=_tire_unit(1),
    ),
    PleosSensorEntityDescription(
        key="tire_pressure_rear_right",
        translation_key="tire_pressure_rear_right",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_tire_value(1, "right"),
        unit_fn=_tire_unit(1),
    ),
    PleosSensorEntityDescription(
        key="last_updated_at",
        translation_key="last_updated_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_updated,
    ),
    PleosSensorEntityDescription(
        key="location_last_updated_at",
        translation_key="location_last_updated_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: _timestamp(dig(data, "locations", "timestamp")),
    ),
)


class PleosVehicleSensor(PleosVehicleEntity, SensorEntity):
    """A sensor backed by Pleos vehicle data."""

    entity_description: PleosSensorEntityDescription

    def __init__(
        self,
        coordinator: PleosVehicleCoordinator,
        vin: str,
        description: PleosSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, vin, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.vehicle_data is None:
            return None
        return self.entity_description.value_fn(self.vehicle_data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit, which may depend on the vehicle's reported units."""
        unit_fn = self.entity_description.unit_fn
        if unit_fn is None or self.vehicle_data is None:
            return self.entity_description.native_unit_of_measurement
        return unit_fn(self.vehicle_data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Pleos sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        PleosVehicleSensor(coordinator, vin, description)
        for vin in coordinator.vehicles
        for description in SENSORS
    )
