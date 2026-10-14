"""Readings taken out of a Pleos vehicle payload."""

from __future__ import annotations

from typing import Any

from homeassistant.const import UnitOfLength
from homeassistant.util.unit_conversion import DistanceConverter

LENGTH_UNITS = {
    "km": UnitOfLength.KILOMETERS,
    "mile": UnitOfLength.MILES,
    "miles": UnitOfLength.MILES,
    "meter": UnitOfLength.METERS,
    "feet": UnitOfLength.FEET,
}


def dig(data: Any, *path: str | int) -> Any:
    """Return a nested value, or None when any step is missing."""
    for key in path:
        try:
            data = data[key]
        except (KeyError, IndexError, TypeError):
            return None
    return data


def length_unit(data: dict[str, Any]) -> str | None:
    """Return the length unit the car itself displays."""
    return LENGTH_UNITS.get(dig(data, "driving", "odometer", "unit"))


def odometer(data: dict[str, Any]) -> float | None:
    """Return the odometer, corrected into the car's own unit.

    Unlike the driving ranges, the vehicle API reports the odometer distance
    in kilometres while labelling it with the car's display unit: a car
    showing miles sends the km figure with a ``mile`` unit. Convert it so the
    number matches the unit the car actually displays.
    """
    raw = dig(data, "driving", "odometer", "value")
    unit = length_unit(data)
    if not isinstance(raw, (int, float)) or isinstance(raw, bool) or unit is None:
        return raw
    return round(DistanceConverter.convert(raw, UnitOfLength.KILOMETERS, unit), 1)


def fuel_level(data: dict[str, Any]) -> float | None:
    """Return the fuel level as a percentage of the tank."""
    value = dig(data, "powertrains", "engine", "fuelLevel")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value)


def battery_level(data: dict[str, Any]) -> float | None:
    """Return the battery state of charge as a percentage."""
    value = dig(data, "batteries", "charge", "stateOfCharge")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value)
