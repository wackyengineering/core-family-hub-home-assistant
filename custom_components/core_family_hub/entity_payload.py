"""Sanitize Home Assistant state before it leaves the household."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .const import SUPPORTED_DOMAINS

ALLOWED_ATTRIBUTES = {
    "light": frozenset(
        {
            "brightness",
            "color_temp",
            "min_color_temp_kelvin",
            "max_color_temp_kelvin",
            "rgb_color",
            "supported_color_modes",
        }
    ),
    "switch": frozenset({"device_class"}),
    "fan": frozenset({"percentage", "percentage_step", "preset_mode", "preset_modes"}),
    "climate": frozenset(
        {
            "current_temperature",
            "current_humidity",
            "temperature",
            "target_temp_high",
            "target_temp_low",
            "hvac_modes",
            "hvac_action",
            "min_temp",
            "max_temp",
            "target_temp_step",
            "temperature_unit",
        }
    ),
    "sensor": frozenset({"unit_of_measurement", "device_class", "state_class"}),
    "binary_sensor": frozenset({"device_class"}),
    "cover": frozenset({"current_position", "device_class"}),
    "scene": frozenset(),
    # Camera source URLs, access tokens, thumbnails, and stream metadata stay
    # inside Home Assistant. CORE synchronizes identity/state only.
    "camera": frozenset(),
}


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)) and len(value) <= 32:
        safe = [_safe_value(item) for item in value]
        return safe if all(item is not _UNSAFE for item in safe) else _UNSAFE
    return _UNSAFE


_UNSAFE = object()


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def state_to_payload(
    state: Any,
    registry_entity_id: str | None = None,
    registry_device_id: str | None = None,
    area_id: str | None = None,
    area_name: str | None = None,
    entity_category: str | None = None,
) -> dict[str, Any] | None:
    """Return an allowlisted state payload or None for unsupported domains."""
    entity_id = str(getattr(state, "entity_id", ""))
    domain = entity_id.partition(".")[0]
    if domain not in SUPPORTED_DOMAINS:
        return None
    raw_attributes = getattr(state, "attributes", {}) or {}
    attributes: dict[str, Any] = {}
    for key in ALLOWED_ATTRIBUTES[domain]:
        if key not in raw_attributes:
            continue
        value = _safe_value(raw_attributes[key])
        if value is not _UNSAFE:
            attributes[key] = value
    raw_state = str(getattr(state, "state", "unknown"))[:120]
    friendly_name = str(raw_attributes.get("friendly_name") or entity_id)[:160]
    return {
        "entityId": entity_id,
        "registryEntityId": registry_entity_id,
        "registryDeviceId": registry_device_id,
        "areaId": area_id,
        "areaName": area_name,
        "entityCategory": entity_category,
        "friendlyName": friendly_name,
        "state": raw_state,
        "attributes": attributes,
        # Home Assistant uses "unknown" when an entity is reachable but has not
        # produced a value. Only its explicit "unavailable" state means CORE
        # should present the entity as offline/unreachable.
        "available": raw_state != "unavailable",
        "lastChangedAt": _iso(getattr(state, "last_changed", None)),
    }
