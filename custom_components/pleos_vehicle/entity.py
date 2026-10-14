"""Shared entity base for the Pleos Vehicle Data integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BRANDS, DOMAIN
from .coordinator import PleosVehicleCoordinator


def dig(data: Any, *path: str | int) -> Any:
    """Return a nested value, or None when any step is missing."""
    for key in path:
        try:
            data = data[key]
        except (KeyError, IndexError, TypeError):
            return None
    return data


class PleosVehicleEntity(CoordinatorEntity[PleosVehicleCoordinator]):
    """Base class for entities that belong to one vehicle."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PleosVehicleCoordinator, vin: str, key: str
    ) -> None:
        super().__init__(coordinator)
        vehicle = coordinator.vehicles[vin]
        self._vin = vin
        self._attr_unique_id = f"{vin}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            manufacturer=BRANDS.get(coordinator.client.brand, "Unknown"),
            model=vehicle.get("sellname") or vehicle.get("name") or None,
            name=vehicle.get("nickname") or vin,
        )

    @property
    def vehicle_data(self) -> dict[str, Any] | None:
        """Return the latest data for this vehicle."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._vin)

    @property
    def available(self) -> bool:
        """Return whether the vehicle data is available."""
        return super().available and self.vehicle_data is not None
