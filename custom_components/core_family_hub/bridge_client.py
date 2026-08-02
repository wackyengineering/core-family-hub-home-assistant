"""Outbound HTTP and Realtime client for the CORE bridge."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
from typing import Any


class CoreBridgeError(Exception):
    """A recoverable CORE bridge error."""


class CoreBridgeAuthenticationError(CoreBridgeError):
    """The connector was revoked or is no longer valid."""


class CoreBridgeClient:
    """Small dependency-free client using Home Assistant's aiohttp session."""

    def __init__(
        self,
        session: Any,
        bridge_url: str,
        connection_id: str | None = None,
        connector_secret: str | None = None,
        realtime_url: str | None = None,
        realtime_key: str | None = None,
        wake_topic: str | None = None,
    ) -> None:
        self._session = session
        self.bridge_url = bridge_url.rstrip("/")
        self.connection_id = connection_id
        self.connector_secret = connector_secret
        self.realtime_url = realtime_url
        self.realtime_key = realtime_key
        self.wake_topic = wake_topic

    async def _request(self, payload: dict[str, Any], authenticated: bool = True) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if authenticated:
            if not self.connection_id or not self.connector_secret:
                raise CoreBridgeAuthenticationError("CORE connector is not paired")
            headers["Authorization"] = f"Bearer {self.connector_secret}"
            headers["x-core-connection-id"] = self.connection_id
        try:
            async with self._session.post(
                self.bridge_url,
                json=payload,
                headers=headers,
                timeout=30,
            ) as response:
                try:
                    body = await response.json()
                except (ValueError, json.JSONDecodeError):
                    body = {}
                if response.status in (401, 403):
                    raise CoreBridgeAuthenticationError(
                        str(body.get("error") or "CORE connector authentication failed")
                    )
                if response.status >= 400:
                    raise CoreBridgeError(
                        str(body.get("error") or f"CORE bridge returned HTTP {response.status}")
                    )
                if not isinstance(body, dict):
                    raise CoreBridgeError("CORE bridge returned an invalid response")
                return body
        except (CoreBridgeError, CoreBridgeAuthenticationError):
            raise
        except (TimeoutError, OSError) as err:
            raise CoreBridgeError(f"CORE bridge is unavailable: {err}") from err

    async def async_pair(
        self,
        pairing_code: str,
        protocol_version: int,
        home_assistant_version: str,
    ) -> dict[str, Any]:
        return await self._request(
            {
                "action": "pair",
                "pairingCode": pairing_code,
                "protocolVersion": protocol_version,
                "homeAssistantVersion": home_assistant_version,
            },
            authenticated=False,
        )

    async def async_heartbeat(
        self,
        state_cursor: int,
        home_assistant_version: str,
        status: str = "connected",
        error: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            {
                "action": "heartbeat",
                "stateCursor": state_cursor,
                "homeAssistantVersion": home_assistant_version,
                "status": status,
                "error": error,
            }
        )

    async def async_sync(
        self,
        entities: list[dict[str, Any]],
        state_cursor: int,
        full_snapshot: bool = False,
        snapshot_entity_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            {
                "action": "sync",
                "entities": entities,
                "stateCursor": state_cursor,
                "fullSnapshot": full_snapshot,
                "snapshotEntityIds": snapshot_entity_ids,
            }
        )

    async def async_pull_commands(self) -> list[dict[str, Any]]:
        response = await self._request({"action": "pull"})
        commands = response.get("commands", [])
        return commands if isinstance(commands, list) else []

    async def async_acknowledge(
        self,
        command_id: str,
        success: bool,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        await self._request(
            {
                "action": "ack",
                "commandId": command_id,
                "success": success,
                "result": result,
                "errorCode": error_code,
                "errorMessage": error_message,
            }
        )

    async def async_listen_for_command_wakeups(
        self,
        on_wakeup: Callable[[], Awaitable[None]],
        stop_event: asyncio.Event,
    ) -> None:
        """Listen for public broadcasts containing only an opaque command ID."""
        if not self.realtime_url or not self.realtime_key or not self.wake_topic:
            raise CoreBridgeError("CORE realtime wake-up configuration is incomplete")
        socket_url = f"{self.realtime_url}?apikey={self.realtime_key}&vsn=1.0.0"
        topic = f"realtime:{self.wake_topic}"
        async with self._session.ws_connect(socket_url, heartbeat=30, timeout=30) as socket:
            await socket.send_json(
                {
                    "topic": topic,
                    "event": "phx_join",
                    "payload": {
                        "config": {
                            "broadcast": {"ack": False, "self": False},
                            "presence": {"enabled": False},
                            "private": False,
                        }
                    },
                    "ref": "1",
                    "join_ref": "1",
                }
            )
            heartbeat_ref = 1
            while not stop_event.is_set():
                try:
                    message = await asyncio.wait_for(socket.receive(), timeout=25)
                except TimeoutError:
                    heartbeat_ref += 1
                    await socket.send_json(
                        {
                            "topic": "phoenix",
                            "event": "heartbeat",
                            "payload": {},
                            "ref": str(heartbeat_ref),
                            "join_ref": None,
                        }
                    )
                    continue
                if getattr(message, "type", None) in (8, 257, 258):
                    raise CoreBridgeError("CORE realtime connection closed")
                try:
                    payload = json.loads(message.data)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if (
                    isinstance(payload, dict)
                    and payload.get("topic") == topic
                    and payload.get("event") == "broadcast"
                    and isinstance(payload.get("payload"), dict)
                    and payload["payload"].get("event") == "command_ready"
                ):
                    await on_wakeup()
