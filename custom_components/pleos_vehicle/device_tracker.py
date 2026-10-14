"""Device tracker platform for the Pleos Vehicle Data integration."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PleosConfigEntry, PleosVehicleCoordinator
from .entity import PleosVehicleEntity, dig


class PleosLocationTracker(PleosVehicleEntity, TrackerEntity):
    """Location of a Pleos vehicle."""

    _attr_source_type = SourceType.GPS
    _attr_translation_key = "location"

    def __init__(self, coordinator: PleosVehicleCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "location")

    @property
    def latitude(self) -> float | None:
        """Return the latitude."""
        return dig(self.vehicle_data, "locations", "location", "latitude")

    @property
    def longitude(self) -> float | None:
        """Return the longitude."""
        return dig(self.vehicle_data, "locations", "location", "longitude")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Pleos location tracker."""
    coordinator = entry.runtime_data
    async_add_entities(
        PleosLocationTracker(coordinator, vin) for vin in coordinator.vehicles
    )
