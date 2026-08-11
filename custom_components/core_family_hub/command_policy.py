"""Defense-in-depth validation for commands received by the companion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class UnsafeCommand(ValueError):
    """The server command is outside the companion allowlist."""


@dataclass(frozen=True)
class ValidatedCommand:
    command_id: str
    domain: str
    service: str
    service_data: dict[str, Any]


ALLOWED_SERVICES = {
    "light": frozenset({"turn_on", "turn_off"}),
    "switch": frozenset({"turn_on", "turn_off"}),
    "fan": frozenset({"turn_on", "turn_off", "set_percentage"}),
    "climate": frozenset({"set_temperature", "set_hvac_mode"}),
    "cover": frozenset({"open_cover", "close_cover", "set_cover_position"}),
    "scene": frozenset({"turn_on"}),
}

ALLOWED_DATA_KEYS = {
    ("light", "turn_on"): frozenset({"entity_id", "brightness_pct"}),
    ("light", "turn_off"): frozenset({"entity_id"}),
    ("switch", "turn_on"): frozenset({"entity_id"}),
    ("switch", "turn_off"): frozenset({"entity_id"}),
    ("fan", "turn_on"): frozenset({"entity_id"}),
    ("fan", "turn_off"): frozenset({"entity_id"}),
    ("fan", "set_percentage"): frozenset({"entity_id", "percentage"}),
    ("climate", "set_temperature"): frozenset(
        {"entity_id", "temperature", "target_temp_low", "target_temp_high"}
    ),
    ("climate", "set_hvac_mode"): frozenset({"entity_id", "hvac_mode"}),
    ("cover", "open_cover"): frozenset({"entity_id"}),
    ("cover", "close_cover"): frozenset({"entity_id"}),
    ("cover", "set_cover_position"): frozenset({"entity_id", "position"}),
    ("scene", "turn_on"): frozenset({"entity_id"}),
}


def _bounded_number(data: dict[str, Any], key: str, minimum: float, maximum: float) -> None:
    value = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise UnsafeCommand(f"{key} is outside the allowed range")


def validate_command(command: dict[str, Any]) -> ValidatedCommand:
    """Validate the entire server-produced service call before local execution."""
    command_id = str(command.get("id") or "")
    entity_id = str(command.get("entity_id") or "")
    domain = str(command.get("domain") or "")
    service = str(command.get("service") or "")
    data = command.get("service_data")
    if not command_id or not entity_id or entity_id.partition(".")[0] != domain:
        raise UnsafeCommand("command identity is invalid")
    if domain not in ALLOWED_SERVICES or service not in ALLOWED_SERVICES[domain]:
        raise UnsafeCommand("domain or service is not allowed")
    if not isinstance(data, dict) or data.get("entity_id") != entity_id:
        raise UnsafeCommand("command target is invalid")
    if set(data) - ALLOWED_DATA_KEYS[(domain, service)]:
        raise UnsafeCommand("command contains unsupported service data")
    if "brightness_pct" in data:
        _bounded_number(data, "brightness_pct", 0, 100)
    if "percentage" in data:
        _bounded_number(data, "percentage", 0, 100)
    if "position" in data:
        _bounded_number(data, "position", 0, 100)
    if "temperature" in data:
        _bounded_number(data, "temperature", -50, 150)
    has_low = "target_temp_low" in data
    has_high = "target_temp_high" in data
    if has_low != has_high:
        raise UnsafeCommand("temperature range requires both limits")
    if has_low:
        _bounded_number(data, "target_temp_low", -50, 150)
        _bounded_number(data, "target_temp_high", -50, 150)
        if data["target_temp_low"] >= data["target_temp_high"]:
            raise UnsafeCommand("temperature range is invalid")
    if "temperature" in data and has_low:
        raise UnsafeCommand("temperature command cannot mix a target and a range")
    if "hvac_mode" in data and data["hvac_mode"] not in {
        "off",
        "heat",
        "cool",
        "auto",
        "heat_cool",
        "dry",
        "fan_only",
    }:
        raise UnsafeCommand("HVAC mode is not allowed")
    return ValidatedCommand(command_id, domain, service, dict(data))
