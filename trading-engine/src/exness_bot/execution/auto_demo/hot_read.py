"""Hot-read safety-critical settings before each auto-demo side effect."""

from __future__ import annotations

import os

from exness_bot.config.settings import Settings


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def hot_read_safety_settings(base: Settings) -> Settings:
    """
    Re-read kill switch / approval / auto-demo / trading_env from process env.

    Other settings remain startup-frozen on ``base``.
    Kill-switch semantics: LIVE_KILL_SWITCH=true must block the next side effect.
    """
    updates: dict[str, object] = {
        "live_kill_switch": _env_bool("LIVE_KILL_SWITCH", base.live_kill_switch),
        "live_demo_approval": _env_bool("LIVE_DEMO_APPROVAL", base.live_demo_approval),
        "auto_demo_execution_enabled": _env_bool(
            "AUTO_DEMO_EXECUTION_ENABLED",
            getattr(base, "auto_demo_execution_enabled", False),
        ),
    }
    env = os.environ.get("TRADING_ENV")
    if env is not None and env.strip():
        updates["trading_env"] = env.strip().lower()
    return base.model_copy(update=updates)
