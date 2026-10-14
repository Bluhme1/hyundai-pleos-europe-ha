"""Config flow for the Pleos Vehicle Data integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import PleosAuthError, PleosClient, PleosError
from .const import (
    BRANDS,
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_VEHICLES,
    DEFAULT_BRAND,
    DOMAIN,
)

BRAND_OPTIONS = [
    SelectOptionDict(value=value, label=label) for value, label in BRANDS.items()
]

CREDENTIAL_FIELDS = {
    vol.Required(CONF_CLIENT_ID): str,
    vol.Required(CONF_CLIENT_SECRET): TextSelector(
        TextSelectorConfig(type=TextSelectorType.PASSWORD)
    ),
}

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BRAND, default=DEFAULT_BRAND): SelectSelector(
            SelectSelectorConfig(options=BRAND_OPTIONS, mode=SelectSelectorMode.DROPDOWN)
        ),
        **CREDENTIAL_FIELDS,
    }
)

REAUTH_SCHEMA = vol.Schema(CREDENTIAL_FIELDS)


async def _async_fetch_vehicles(
    hass: HomeAssistant, brand: str, client_id: str, client_secret: str
) -> list[dict[str, str]]:
    """Validate the credentials and return the vehicles they can read."""
    client = PleosClient(
        async_get_clientsession(hass), client_id, client_secret, brand
    )
    vehicles = await client.async_get_vehicles()
    return [
        {
            "vin": vehicle["vin"],
            "nickname": vehicle.get("nickname") or vehicle["vin"],
            "name": vehicle.get("name") or "",
            "sellname": vehicle.get("sellname") or "",
        }
        for vehicle in vehicles
        if vehicle.get("vin")
    ]


class PleosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pleos Vehicle Data."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the brand and the Pleos API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                vehicles = await _async_fetch_vehicles(
                    self.hass,
                    user_input[CONF_BRAND],
                    user_input[CONF_CLIENT_ID],
                    user_input[CONF_CLIENT_SECRET],
                )
            except PleosAuthError:
                errors["base"] = "invalid_auth"
            except PleosError:
                errors["base"] = "cannot_connect"
            else:
                if not vehicles:
                    errors["base"] = "no_vehicles"
                else:
                    await self.async_set_unique_id(user_input[CONF_CLIENT_ID])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"Pleos Vehicle Data ({BRANDS[user_input[CONF_BRAND]]})",
                        data={**user_input, CONF_VEHICLES: vehicles},
                    )
        return self.async_show_form(
            step_id="user", data_schema=STEP_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after Pleos rejected the credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new Client ID and Client Secret."""
        errors: dict[str, str] = {}
        entry: ConfigEntry = self._get_reauth_entry()
        if user_input is not None:
            brand = entry.data.get(CONF_BRAND, DEFAULT_BRAND)
            try:
                vehicles = await _async_fetch_vehicles(
                    self.hass,
                    brand,
                    user_input[CONF_CLIENT_ID],
                    user_input[CONF_CLIENT_SECRET],
                )
            except PleosAuthError:
                errors["base"] = "invalid_auth"
            except PleosError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={**user_input, CONF_VEHICLES: vehicles},
                    reason="reauth_successful",
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )
