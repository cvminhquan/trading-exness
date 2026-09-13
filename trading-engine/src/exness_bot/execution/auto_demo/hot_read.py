"""Canonical safety settings loader for auto_demo CLI / loop hot-read.

Precedence for safety-critical keys (aligned with pydantic-settings ``Settings``):

1. Explicit process environment variables (shell export / ``$env:NAME``)
2. Project ``.env`` loaded by ``Settings`` (cwd-relative ``env_file``)
3. Field defaults on ``Settings``

Do **not** parse ``AUTO_DEMO_EXECUTION_ENABLED`` (or sibling safety flags) with a
separate ``os.getenv`` bool helper — that diverges from ``Settings`` and caused
``preflight`` / ``run`` to disagree.
"""

from __future__ import annotations

import os
from typing import Final

from exness_bot.config.settings import Settings, get_settings

# Keys re-applied on every hot-read / enablement check.
#
# EXECUTION_MODE is hot-read AND fail-closed on auto_demo enablement:
# EXECUTION_MODE=live (or non-paper) blocks autonomous DEMO (Phase 17.3.3).
# Autonomous DEMO still also requires TRADING_ENV=demo + AUTO_DEMO_* + LIVE_* +
# allowlist + account trade_mode (see evaluate_auto_demo_enablement).
_SAFETY_ENV_NAMES: Final[tuple[str, ...]] = (
    "LIVE_KILL_SWITCH",
    "LIVE_DEMO_APPROVAL",
    "AUTO_DEMO_EXECUTION_ENABLED",
    "TRADING_ENV",
    "DEMO_ACCOUNT_ALLOWLIST",
    "EXECUTION_MODE",
)


def load_auto_demo_settings() -> Settings:
    """Load CLI settings from the same canonical ``Settings`` source every time.

    Clears the process-wide ``get_settings`` cache so a prior import cannot
    serve a stale snapshot that never saw the project ``.env``.
    """
    get_settings.cache_clear()
    settings = Settings()
    get_settings.cache_clear()
    return settings


def hot_read_safety_settings(base: Settings) -> Settings:
    """
    Re-apply safety-critical fields before each auto-demo side effect.

    Precedence:
    1. Process environment (explicit override)
    2. Values already on ``base`` (from ``Settings`` / ``.env`` at load time)

    Parsing goes through ``Settings`` only — same validators as status/preflight/run.
    """
    layered: dict[str, object] = {
        "_env_file": None,
        "LIVE_KILL_SWITCH": base.live_kill_switch,
        "LIVE_DEMO_APPROVAL": base.live_demo_approval,
        "AUTO_DEMO_EXECUTION_ENABLED": base.auto_demo_execution_enabled,
        "TRADING_ENV": base.trading_env,
        "DEMO_ACCOUNT_ALLOWLIST": base.demo_account_allowlist,
        "EXECUTION_MODE": (
            base.execution_mode.value
            if hasattr(base.execution_mode, "value")
            else base.execution_mode
        ),
    }
    for name in _SAFETY_ENV_NAMES:
        if name in os.environ:
            layered[name] = os.environ[name]

    parsed = Settings(**layered)  # type: ignore[arg-type]
    return base.model_copy(
        update={
            "live_kill_switch": parsed.live_kill_switch,
            "live_demo_approval": parsed.live_demo_approval,
            "auto_demo_execution_enabled": parsed.auto_demo_execution_enabled,
            "trading_env": parsed.trading_env,
            "demo_account_allowlist": parsed.demo_account_allowlist,
            "execution_mode": parsed.execution_mode,
        }
    )


def auto_demo_run_allowed(settings: Settings) -> bool:
    """Same enablement bit ``run`` / ``once`` use before mutate paths."""
    return bool(hot_read_safety_settings(settings).auto_demo_execution_enabled)
