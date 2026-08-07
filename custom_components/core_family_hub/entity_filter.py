"""Choose the minimum useful Home Assistant entity set for CORE."""

from __future__ import annotations

from typing import Any

from .const import SUPPORTED_DOMAINS

CONFIGURATION_HELPER_SUFFIXES = (
    "_auto_off_enabled",
    "_auto_update_enabled",
    "_dock_child_lock",
    "_do_not_disturb",
    "_fan_sleep_mode",
    "_led",
)


def is_configuration_helper_entity_id(entity_id: str) -> bool:
    """Recognize narrowly scoped switch settings left uncategorized by integrations."""

    domain, separator, object_id = entity_id.partition(".")
    return bool(
        separator
        and domain == "switch"
        and any(object_id.endswith(suffix) for suffix in CONFIGURATION_HELPER_SUFFIXES)
    )


def entity_category_value(entity_entry: Any | None) -> str | None:
    """Return the normalized Home Assistant category CORE understands."""

    raw_category = getattr(entity_entry, "entity_category", None) if entity_entry else None
    if raw_category is None:
        return None
    value = str(getattr(raw_category, "value", raw_category)).strip().lower()
    return value or None


def should_sync_entity(state: Any, entity_entry: Any | None = None) -> bool:
    """Return whether a Home Assistant entity should leave the household.

    Home Assistant integrations commonly create configuration and diagnostic
    entities alongside the primary device. CORE keeps useful read-only diagnostic
    telemetry, but does not need firmware/configuration toggles or entities the
    household already hid or disabled.
    """

    entity_id = str(getattr(state, "entity_id", ""))
    domain = entity_id.partition(".")[0]
    if domain not in SUPPORTED_DOMAINS:
        return False
    if is_configuration_helper_entity_id(entity_id):
        return False

    if entity_entry is None:
        # Some state-only entities do not have registry entries. Keep supported
        # primary states available for explicit selection in CORE.
        return True

    if getattr(entity_entry, "disabled_by", None) is not None:
        return False
    if getattr(entity_entry, "hidden_by", None) is not None:
        return False
    if entity_category_value(entity_entry) == "config":
        return False
    return True
