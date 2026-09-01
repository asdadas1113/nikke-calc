from __future__ import annotations

from typing import Callable, TYPE_CHECKING

from .triggers import TriggerMode
from .weapon import (
    WeaponCadenceMachine,
    WeaponTriggerBoundary,
    _WeaponBoundaryCollector,
)

if TYPE_CHECKING:
    from .model import CompiledEffect, CompiledSquad


class _HitAwareBoundaryCollector(_WeaponBoundaryCollector):
    """Moris-compatible generic hit counter over Fast's compressed shot blocks.

    Moris notifies ``hit_count`` once per actual hit, not once per trigger pull.
    For SG that means once per pellet, and multi-muzzle weapons likewise advance
    by every muzzle hit. The parent collector already supports several threshold
    crossings at the same shot time; this subclass only supplies the correct
    events-per-shot multiplier while preserving block aggregation.
    """

    __slots__ = ("hits_per_shot",)

    def __init__(
        self,
        actor: int,
        thresholds: dict[str, tuple[int, ...]],
        *,
        hits_per_shot: int,
    ) -> None:
        super().__init__(actor, thresholds)
        self.hits_per_shot = max(1, int(hits_per_shot))

    @classmethod
    def from_character(
        cls,
        actor: int,
        character,
        *,
        effect_filter: Callable[["CompiledEffect"], bool],
        hits_per_shot: int,
    ) -> "_HitAwareBoundaryCollector":
        thresholds: dict[str, set[int]] = {}
        for effect in character.effects:
            if not effect_filter(effect):
                continue
            for rule in effect.triggers:
                if rule.event_key not in {"hit_count", "full_charge_hit", "pellet_hit"}:
                    continue
                if rule.mode is not TriggerMode.MODULO or not rule.trigger_count_reducible:
                    continue
                threshold = int(rule.threshold or 0)
                if threshold > 0:
                    thresholds.setdefault(rule.event_key, set()).add(threshold)
        return cls(
            actor,
            {key: tuple(sorted(values)) for key, values in thresholds.items()},
            hits_per_shot=hits_per_shot,
        )

    def add_block(
        self,
        event_key: str,
        first_t: float,
        shot_count: int,
        shot_interval: float,
        *,
        events_per_shot: int = 1,
    ) -> None:
        if event_key == "hit_count":
            events_per_shot = self.hits_per_shot
        super().add_block(
            event_key,
            first_t,
            shot_count,
            shot_interval,
            events_per_shot=events_per_shot,
        )


def simulate_weapon_trigger_boundaries(
    squad: "CompiledSquad",
    *,
    duration: float,
    effect_filter: Callable[["CompiledEffect"], bool],
) -> tuple[WeaponTriggerBoundary, ...]:
    """Canonical static trigger-boundary planner used by Fast runtime.

    No per-shot global events are materialized. A whole unchanged shot block is
    still aggregated, but generic ``hit_count`` progress uses the actual number
    of hits produced by each shot.
    """

    out: list[WeaponTriggerBoundary] = []
    for actor, character in enumerate(squad.members):
        machine = WeaponCadenceMachine(actor, character, duration=duration)
        collector = _HitAwareBoundaryCollector.from_character(
            actor,
            character,
            effect_filter=effect_filter,
            hits_per_shot=machine._hits_per_shot(),
        )
        if not collector.thresholds:
            continue
        machine.run(collector=collector)
        out.extend(collector.boundaries)
    out.sort(key=lambda row: (row.time, row.actor, row.event_key))
    return tuple(out)
