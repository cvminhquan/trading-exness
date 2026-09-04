"""One-shot operator approval for controlled DEMO smoke. Not a strategy enablement."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class OneShotApproval:
    """
    Process-local one-shot authorization.

    active=True means LIVE_DEMO_APPROVAL was set.
    After try_consume succeeds once, further consumes fail.
    Does NOT enable a strategy loop. Does NOT bypass other gates.
    """

    active: bool
    _consumed: bool = field(default=False, init=False)
    _consumed_intent_id: str | None = field(default=None, init=False)

    @property
    def consumed(self) -> bool:
        return self._consumed

    @property
    def consumed_intent_id(self) -> str | None:
        return self._consumed_intent_id

    def try_consume(self, *, intent_id: str) -> bool:
        if not self.active:
            logger.warning("demo_approval_missing", intent_id=intent_id)
            return False
        if self._consumed:
            logger.warning(
                "demo_approval_already_consumed",
                intent_id=intent_id,
                prior_intent_id=self._consumed_intent_id,
            )
            return False
        self._consumed = True
        self._consumed_intent_id = intent_id
        logger.info(
            "demo_approval_consumed",
            intent_id=intent_id,
            note="ONE_SHOT — further submissions blocked",
        )
        return True
