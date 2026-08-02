"""Lifecycle, state synchronization, and command execution for CORE."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import Any

from homeassistant.const import EVENT_STATE_CHANGED, __version__ as HOME_ASSISTANT_VERSION
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store

from .batching import take_pending_batch
from .bridge_client import CoreBridgeAuthenticationError, CoreBridgeClient, CoreBridgeError
from .command_policy import UnsafeCommand, validate_command
from .const import (
    COMMAND_PULL_LIMIT,
    FALLBACK_COMMAND_POLL_SECONDS,
    HEARTBEAT_SECONDS,
    MAX_STATE_BATCH,
    STATE_BATCH_SECONDS,
    SUPPORTED_DOMAINS,
)
from .entity_payload import state_to_payload

_LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1


class CoreBridgeRuntime:
    """Maintain one outbound companion connection."""

    def __init__(self, hass: HomeAssistant, entry_id: str, client: CoreBridgeClient) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.client = client
        self._stop = asyncio.Event()
        self._command_wakeup = asyncio.Event()
        self._state_wakeup = asyncio.Event()
        self._pending_states: dict[str, State] = {}
        self._tasks: list[asyncio.Task[Any]] = []
        self._unsub_state: Callable[[], None] | None = None
        self._cursor = 0
        self._executed: dict[str, dict[str, Any]] = {}
        self._store = Store(hass, STORE_VERSION, f"core_family_hub.{entry_id}")

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        self._cursor = int(stored.get("cursor", 0))
        self._executed = dict(stored.get("executed", {}))
        await self._async_full_sync()
        self._unsub_state = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._state_changed)
        self._tasks = [
            self.hass.async_create_task(self._state_worker()),
            self.hass.async_create_task(self._command_worker()),
            self.hass.async_create_task(self._heartbeat_worker()),
            self.hass.async_create_task(self._realtime_worker()),
        ]

    async def async_stop(self) -> None:
        self._stop.set()
        self._command_wakeup.set()
        self._state_wakeup.set()
        if self._unsub_state:
            self._unsub_state()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._save_store()

    def _registries(self) -> tuple[Any, Any, Any]:
        return er.async_get(self.hass), dr.async_get(self.hass), ar.async_get(self.hass)

    def _payload_for_state(self, state: State) -> dict[str, Any] | None:
        entity_registry, device_registry, area_registry = self._registries()
        entity_entry = entity_registry.async_get(state.entity_id)
        device_entry = device_registry.async_get(entity_entry.device_id) if entity_entry and entity_entry.device_id else None
        area_id = (entity_entry.area_id if entity_entry else None) or (device_entry.area_id if device_entry else None)
        area_entry = area_registry.async_get_area(area_id) if area_id else None
        return state_to_payload(
            state,
            registry_entity_id=entity_entry.id if entity_entry else None,
            registry_device_id=entity_entry.device_id if entity_entry else None,
            area_id=area_id,
            area_name=area_entry.name if area_entry else None,
        )

    async def _async_full_sync(self) -> None:
        payloads = [
            payload
            for state in self.hass.states.async_all()
            if state.domain in SUPPORTED_DOMAINS
            if (payload := self._payload_for_state(state)) is not None
        ]
        self._cursor += 1
        snapshot_entity_ids = [payload["entityId"] for payload in payloads]
        for offset in range(0, len(payloads) or 1, MAX_STATE_BATCH):
            chunk = payloads[offset : offset + MAX_STATE_BATCH]
            await self.client.async_sync(
                chunk,
                self._cursor,
                full_snapshot=offset + MAX_STATE_BATCH >= len(payloads),
                snapshot_entity_ids=snapshot_entity_ids if offset + MAX_STATE_BATCH >= len(payloads) else None,
            )
        await self._save_store()

    @callback
    def _state_changed(self, event: Event) -> None:
        state = event.data.get("new_state")
        if state is None or state.domain not in SUPPORTED_DOMAINS:
            return
        self._pending_states[state.entity_id] = state
        self._state_wakeup.set()

    async def _state_worker(self) -> None:
        while not self._stop.is_set():
            await self._state_wakeup.wait()
            self._state_wakeup.clear()
            await asyncio.sleep(STATE_BATCH_SECONDS)
            states = take_pending_batch(self._pending_states, MAX_STATE_BATCH)
            payloads = [payload for state in states if (payload := self._payload_for_state(state)) is not None]
            if not payloads:
                continue
            try:
                self._cursor += 1
                await self.client.async_sync(payloads, self._cursor)
                await self._save_store()
                if self._pending_states:
                    self._state_wakeup.set()
            except CoreBridgeError as err:
                _LOGGER.warning("Could not synchronize CORE entity state: %s", err)
                for state in states:
                    self._pending_states[state.entity_id] = state
                await asyncio.sleep(5)
                self._state_wakeup.set()

    async def _command_worker(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._command_wakeup.wait(), FALLBACK_COMMAND_POLL_SECONDS)
            except TimeoutError:
                pass
            self._command_wakeup.clear()
            try:
                while not self._stop.is_set():
                    commands = await self.client.async_pull_commands()
                    for command in commands:
                        await self._execute_command(command)
                    if len(commands) < COMMAND_PULL_LIMIT:
                        break
            except CoreBridgeAuthenticationError:
                _LOGGER.error("CORE connector was revoked; re-pair the integration")
                return
            except CoreBridgeError as err:
                _LOGGER.warning("Could not retrieve CORE commands: %s", err)

    async def _execute_command(self, raw_command: dict[str, Any]) -> None:
        command_id = str(raw_command.get("id") or "")
        if command_id in self._executed:
            previous = self._executed[command_id]
            await self.client.async_acknowledge(command_id, bool(previous["success"]), previous.get("result"), previous.get("errorCode"), previous.get("errorMessage"))
            return
        try:
            command = validate_command(raw_command)
            await self.hass.services.async_call(
                command.domain,
                command.service,
                command.service_data,
                blocking=True,
            )
            observed = self.hass.states.get(command.service_data["entity_id"])
            result = {
                "serviceAcknowledged": True,
                "observedState": observed.state if observed else None,
            }
            record = {"success": True, "result": result}
            self._executed[command.command_id] = record
            self._trim_executed()
            await self._save_store()
            await self.client.async_acknowledge(command.command_id, True, result)
        except UnsafeCommand as err:
            record = {"success": False, "errorCode": "unsafe_command", "errorMessage": str(err)}
            self._executed[command_id] = record
            self._trim_executed()
            await self._save_store()
            await self.client.async_acknowledge(command_id, False, error_code="unsafe_command", error_message=str(err))
        except Exception as err:  # Home Assistant service exceptions vary by integration.
            _LOGGER.warning("CORE command %s failed: %s", command_id, err)
            message = str(err)[:500]
            record = {"success": False, "errorCode": "service_failed", "errorMessage": message}
            self._executed[command_id] = record
            self._trim_executed()
            await self._save_store()
            await self.client.async_acknowledge(command_id, False, error_code="service_failed", error_message=message)

    def _trim_executed(self) -> None:
        while len(self._executed) > 500:
            self._executed.pop(next(iter(self._executed)))

    async def _heartbeat_worker(self) -> None:
        while not self._stop.is_set():
            try:
                await self.client.async_heartbeat(self._cursor, HOME_ASSISTANT_VERSION)
            except CoreBridgeAuthenticationError:
                return
            except CoreBridgeError as err:
                _LOGGER.warning("CORE heartbeat failed: %s", err)
            try:
                await asyncio.wait_for(self._stop.wait(), HEARTBEAT_SECONDS)
            except TimeoutError:
                pass

    async def _realtime_worker(self) -> None:
        delay = 1
        while not self._stop.is_set():
            try:
                await self.client.async_listen_for_command_wakeups(self._wake_commands, self._stop)
                delay = 1
            except (CoreBridgeError, OSError) as err:
                if self._stop.is_set():
                    return
                _LOGGER.debug("CORE realtime wake-up disconnected: %s", err)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    async def _wake_commands(self) -> None:
        self._command_wakeup.set()

    async def _save_store(self) -> None:
        await self._store.async_save({"cursor": self._cursor, "executed": self._executed})
