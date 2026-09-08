"""Frozen research config — must be locked before holdout evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class V2FrozenConfig:
    """Holdout discipline: do not mutate after validation freeze."""

    strategy_id: str
    tf_weights: Mapping[str, float]
    weight_trend: float
    weight_structure: float
    weight_momentum: float
    weight_location: float
    weight_volume: float
    weight_impulse: float
    long_threshold: float
    short_threshold: float
    tf_long_threshold: float
    tf_short_threshold: float
    structure_conflict_dampen: float
    impulse_tanh_scale: float
    impulse_w1: float
    impulse_w3: float
    impulse_w4: float
    higher_tf_strong_conflict_enabled: bool
    frozen: bool = True
    notes: tuple[str, ...] = field(default_factory=tuple)


# Initial hypothesis — freeze before holdout; do not retune after holdout view.
# Phase 16.2.4A: this snapshot is IMMUTABLE — do not change values after holdout view.
DEFAULT_V2_CONFIG = V2FrozenConfig(
    strategy_id="mtf_technical_v2_candidate",
    tf_weights={"M15": 0.50, "H1": 0.30, "H4": 0.15, "D1": 0.05},
    weight_trend=0.25,
    weight_structure=0.15,
    weight_momentum=0.20,
    weight_location=0.10,
    weight_volume=0.10,
    weight_impulse=0.20,
    long_threshold=20.0,
    short_threshold=-20.0,
    tf_long_threshold=25.0,
    tf_short_threshold=-25.0,
    structure_conflict_dampen=0.35,
    impulse_tanh_scale=1.5,
    impulse_w1=0.50,
    impulse_w3=0.30,
    impulse_w4=0.20,
    higher_tf_strong_conflict_enabled=False,
    notes=(
        "Initial M15-first hypothesis — not PnL-optimized.",
        "H4/D1 do not implicit-veto; higher_tf_strong_conflict disabled.",
        "FROZEN for Phase 16.2.4 / 16.2.4A — no retune after holdout.",
    ),
)

# Fingerprint of freeze_snapshot used in 16.2.4 holdout — 16.2.4A must match.
FROZEN_SNAPSHOT_16_2_4 = {
    "strategy_id": "mtf_technical_v2_candidate",
    "tf_weights": {"M15": 0.5, "H1": 0.3, "H4": 0.15, "D1": 0.05},
    "component_weights": {
        "trend": 0.25,
        "structure": 0.15,
        "momentum": 0.2,
        "location": 0.1,
        "volume": 0.1,
        "impulse": 0.2,
    },
    "thresholds": {"long": 20.0, "short": -20.0},
    "structure_conflict_dampen": 0.35,
    "impulse_mapping": {"scale": 1.5, "w1": 0.5, "w3": 0.3, "w4": 0.2},
    "higher_tf_strong_conflict_enabled": False,
}


def freeze_snapshot_dict(config: V2FrozenConfig) -> dict[str, object]:
    return {
        "strategy_id": config.strategy_id,
        "tf_weights": dict(config.tf_weights),
        "component_weights": {
            "trend": config.weight_trend,
            "structure": config.weight_structure,
            "momentum": config.weight_momentum,
            "location": config.weight_location,
            "volume": config.weight_volume,
            "impulse": config.weight_impulse,
        },
        "thresholds": {
            "long": config.long_threshold,
            "short": config.short_threshold,
        },
        "structure_conflict_dampen": config.structure_conflict_dampen,
        "impulse_mapping": {
            "scale": config.impulse_tanh_scale,
            "w1": config.impulse_w1,
            "w3": config.impulse_w3,
            "w4": config.impulse_w4,
        },
        "higher_tf_strong_conflict_enabled": config.higher_tf_strong_conflict_enabled,
        "frozen": True,
    }


def assert_config_frozen(config: V2FrozenConfig) -> None:
    if not config.frozen:
        msg = "V2 config must be frozen before holdout"
        raise RuntimeError(msg)


def assert_freeze_matches_16_2_4(config: V2FrozenConfig) -> None:
    """Hard-fail if anyone retunes after the original holdout freeze."""
    snap = freeze_snapshot_dict(config)
    for key, expected in FROZEN_SNAPSHOT_16_2_4.items():
        actual = snap[key]
        if actual != expected:
            msg = f"Freeze drift on {key}: {actual!r} != {expected!r}"
            raise RuntimeError(msg)
