"""Constants for the CORE Family Hub companion integration."""

DOMAIN = "core_family_hub"
PROTOCOL_VERSION = 1

CONF_BRIDGE_URL = "bridge_url"
CONF_CONNECTION_ID = "connection_id"
CONF_CONNECTOR_SECRET = "connector_secret"
CONF_PAIRING_CODE = "pairing_code"
CONF_REALTIME_KEY = "realtime_key"
CONF_REALTIME_URL = "realtime_url"
CONF_TENANT_ID = "tenant_id"
CONF_WAKE_TOPIC = "wake_topic"

DEFAULT_BRIDGE_URL = (
    "https://jypnnfkajewpiyekvsxi.supabase.co/functions/v1/"
    "home-assistant-bridge"
)
HEARTBEAT_SECONDS = 20
FALLBACK_COMMAND_POLL_SECONDS = 10
COMMAND_PULL_LIMIT = 25
STATE_BATCH_SECONDS = 0.75
MAX_STATE_BATCH = 500

SUPPORTED_DOMAINS = frozenset(
    {
        "light",
        "switch",
        "fan",
        "climate",
        "sensor",
        "binary_sensor",
        "cover",
        "scene",
    }
)
