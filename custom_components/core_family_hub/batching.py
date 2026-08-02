"""Dependency-free queue helpers for companion state synchronization."""

from __future__ import annotations

from typing import TypeVar


T = TypeVar("T")


def take_pending_batch(pending: dict[str, T], limit: int) -> list[T]:
    """Remove and return at most ``limit`` values while preserving newer work."""
    keys = list(pending)[:limit]
    return [pending.pop(key) for key in keys]
