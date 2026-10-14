"""Constants for the Pleos Vehicle Data integration."""

from datetime import timedelta

DOMAIN = "pleos_vehicle"

API_BASE_URL = "https://api.pleos.ai/v1"
REQUEST_TIMEOUT = 30

BRANDS = {"hyundai": "Hyundai", "kia": "Kia", "genesis": "Genesis"}
DEFAULT_BRAND = "hyundai"

CONF_BRAND = "brand"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_VEHICLES = "vehicles"

SCAN_INTERVAL = timedelta(minutes=15)

SERVICE_REFRESH = "refresh"
