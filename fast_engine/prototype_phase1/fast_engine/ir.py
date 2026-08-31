from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
import json

from .inventory import (
    readiness,
    stat_subsystem,
    status_for_stat,
    timing_family,
    condition_family,
    target_family,
)


@dataclass(frozen=True)
class TriggerIR:
    timings: tuple[str, ...]
    timing_families: tuple[str, ...]
    conditions: tuple[str, ...]
    condition_families: tuple[str, ...]


@dataclass(frozen=True)
class EffectIR:
    character: str
    source: str
    name: str
    effect_type: str
    stat: str | None
    moris_status: str
    subsystem: str
    readiness: str
    trigger: TriggerIR
    target: Any
    target_family: str
    scaling: str | None
    scaling_ref: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def requires_moris_fallback(self) -> bool:
        return self.readiness == "D"

    @property
    def is_moris_nop(self) -> bool:
        return self.readiness == "N"


@dataclass(frozen=True)
class CharacterIR:
    name: str
    effects: tuple[EffectIR, ...]

    @property
    def requires_moris_fallback(self) -> bool:
        return any(e.requires_moris_fallback for e in self.effects)

    @property
    def fallback_effects(self) -> tuple[EffectIR, ...]:
        return tuple(e for e in self.effects if e.requires_moris_fallback)


CORE_FIELDS = frozenset({
    "source", "type", "name", "trigger", "target", "stat", "scaling", "scaling_ref",
})


def compile_effect(character: str, effect: Mapping[str, Any]) -> EffectIR:
    trigger = effect.get("trigger") or {}
    timings = tuple(trigger.get("timing") or ())
    conditions = tuple(trigger.get("condition") or ())
    r, _reasons = readiness(dict(effect))
    metadata = {k: v for k, v in effect.items() if k not in CORE_FIELDS}
    return EffectIR(
        character=character,
        source=str(effect.get("source", "")),
        name=str(effect.get("name", "")),
        effect_type=str(effect.get("type", "")),
        stat=effect.get("stat"),
        moris_status=status_for_stat(effect.get("stat")),
        subsystem=stat_subsystem(effect.get("stat"), str(effect.get("type", ""))),
        readiness=r,
        trigger=TriggerIR(
            timings=timings,
            timing_families=tuple(timing_family(t) for t in timings),
            conditions=conditions,
            condition_families=tuple(condition_family(c) for c in conditions),
        ),
        target=effect.get("target"),
        target_family=target_family(effect.get("target")),
        scaling=effect.get("scaling"),
        scaling_ref=effect.get("scaling_ref"),
        metadata=MappingProxyType(metadata),
    )


def compile_catalog(parsed_skills_path: Path) -> tuple[CharacterIR, ...]:
    parsed = json.loads(parsed_skills_path.read_text(encoding="utf-8"))
    return tuple(
        CharacterIR(name=name, effects=tuple(compile_effect(name, e) for e in effects))
        for name, effects in parsed.items()
    )
