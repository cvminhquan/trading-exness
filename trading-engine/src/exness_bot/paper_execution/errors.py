"""Durable intent-store errors — fail closed. No broker types."""

from __future__ import annotations


class IntentStoreError(Exception):
    """Base error for durable intent persistence."""


class InvalidLifecycleTransition(IntentStoreError):
    """Requested lifecycle transition is not allowed."""


class DuplicateIdempotencyKey(IntentStoreError):
    """
    Idempotency key already exists.

    Callers should treat this as a deterministic duplicate — not a new intent.
    """

    def __init__(self, *, idempotency_key: str, existing: object) -> None:
        self.idempotency_key = idempotency_key
        self.existing = existing
        super().__init__(f"Duplicate idempotency_key: {idempotency_key}")


class CorruptStateError(IntentStoreError):
    """Local snapshot is corrupt or inconsistent — do not reset to empty."""


class UnsupportedSchemaError(IntentStoreError):
    """schemaVersion is missing or not supported."""
