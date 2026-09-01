from __future__ import annotations

from typing import Callable, TYPE_CHECKING

from .weapon import WeaponCadenceMachine, WeaponTriggerBoundary, _WeaponBoundaryCollector

if TYPE_CHECKING:
    from .model import CompiledEffect, CompiledSquad


def simulate_weapon_trigger_boundaries(
    squad: "CompiledSquad",
    *,
    duration: float,
    effect_filter: Callable[["CompiledEffect"], bool],
) -> tuple[WeaponTriggerBoundary, ...]:
    """Canonical static trigger-boundary planner used by Fast runtime.

    Moris keeps two distinct counters:
    - ``hit_count`` advances once per trigger pull / projectile attack,
    - ``pellet_hit`` advances once per pellet (and therefore may advance several
      times at the same shot timestamp for SG/multi-muzzle attacks).

    The cadence machine already emits exactly those two compressed streams, so
    no per-shot or per-pellet global events are materialized unless a threshold
    is actually crossed.
    """

    out: list[WeaponTriggerBoundary] = []
    for actor, character in enumerate(squad.members):
        collector = _WeaponBoundaryCollector.from_character(
            actor,
            character,
            effect_filter=effect_filter,
        )
        if not collector.thresholds:
            continue
        WeaponCadenceMachine(actor, character, duration=duration).run(
            collector=collector
        )
        out.extend(collector.boundaries)
    out.sort(key=lambda row: (row.time, row.actor, row.event_key))
    return tuple(out)
