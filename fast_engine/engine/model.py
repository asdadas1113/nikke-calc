from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .capabilities import EffectCapability
    from .conditions import ConditionRule
    from .targets import TargetSpec
    from .triggers import TriggerIndex, TriggerRule


@dataclass(frozen=True, slots=True)
class EnemyStaticProfile:
    """Patternless target used by Fast ranking.

    `duration` is the battle horizon, not a fixed simulation timestep.
    The runtime advances from event to event and may aggregate unchanged spans.
    """

    defense: float = 31784.0
    element: str | None = None
    core_uptime: float = 0.0
    core_hit_rate_when_open: float = 1.0
    duration: float = 180.0

    def __post_init__(self) -> None:
        if self.defense < 0:
            raise ValueError("enemy defense must be >= 0")
        if self.duration <= 0:
            raise ValueError("duration must be > 0")
        for name, value in (
            ("core_uptime", self.core_uptime),
            ("core_hit_rate_when_open", self.core_hit_rate_when_open),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

    @property
    def effective_core_rate(self) -> float:
        return self.core_uptime * self.core_hit_rate_when_open


@dataclass(frozen=True, slots=True)
class CompiledEffect:
    """One Moris effect lowered into Fast compile-time metadata.

    Runtime hot paths should use the numeric fields and precompiled trigger rules
    instead of repeatedly decoding parsed JSON strings/dicts.
    """

    effect_id: int
    actor: int
    actor_effect_index: int
    source: str | None
    source_tag: str
    name: str
    effect_type: str
    stat: str | None
    polarity: str | None
    target: Any
    target_spec: "TargetSpec"
    conditions: tuple[str, ...]
    condition_rules: tuple["ConditionRule", ...]
    triggers: tuple["TriggerRule", ...]
    value: float | None
    duration: float | None
    max_stack: float | None
    max_trigger: int | None
    tick_interval: float | None
    parameters: Mapping[str, Any]
    capability: "EffectCapability"


@dataclass(frozen=True, slots=True)
class CompiledCharacter:
    """Moris input reduced to immutable Fast compile-time data."""

    name: str
    base_atk: float
    base_def: float
    base_hp: float
    element: str | None
    character_class: str
    squad_group: str | None
    burst_stage: str
    burst_cooldown: float
    burst_regen_time: float
    weapon_type: str
    weapon: Mapping[str, Any]
    effects: tuple[CompiledEffect, ...]
    skill_levels: Mapping[str, int]
    favorite_stage: int

    @property
    def effect_capabilities(self) -> tuple["EffectCapability", ...]:
        return tuple(effect.capability for effect in self.effects)


@dataclass(frozen=True, slots=True)
class CompiledSquad:
    members: tuple[CompiledCharacter, ...]
    trigger_index: "TriggerIndex"

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(member.name for member in self.members)

    @property
    def effects(self) -> tuple[CompiledEffect, ...]:
        return tuple(effect for member in self.members for effect in member.effects)

    @property
    def capability_blockers(self) -> tuple["EffectCapability", ...]:
        return tuple(effect.capability for effect in self.effects if effect.capability.blocks_fast)

    @property
    def fast_ready(self) -> bool:
        return not self.capability_blockers


@dataclass(slots=True)
class ActorRuntimeState:
    """Small mutable state surface that the event runtime is allowed to keep."""

    ammo: float = 0.0
    hp: float = 0.0
    shield: float = 0.0
    states: dict[str, Any] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    counters: dict[str, float] = field(default_factory=dict)
    last_dealt_damage: float = 0.0
    damage_accumulators: dict[str, float] = field(default_factory=dict)
    weapon_mode: str | None = None


@dataclass(frozen=True, slots=True)
class FastScore:
    squad_total: float
    char_total: tuple[float, ...]
    duration: float
    events_processed: int
    unsupported: tuple[str, ...] = ()
