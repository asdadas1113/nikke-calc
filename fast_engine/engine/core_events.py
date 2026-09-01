from __future__ import annotations

import heapq
import math
from typing import Callable, Iterable, Mapping

from .model import CompiledEffect, CompiledSquad
from .normal_attack import compile_normal_attack_spec
from .shot_blocks import ShotBlock, compile_static_shot_blocks
from .triggers import TriggerMode
from .weapon import WeaponTriggerBoundary

_EPS = 1e-12


def is_static_expected_core_count_rule(rule) -> bool:
    """Return the first certified expected-value core-count trigger shape.

    Moris distinguishes the legacy ``core_hit:N`` spelling, whose threshold can
    be changed by trigger-count-reduction buffs, from the fixed
    ``core_hit_count:N`` spelling used by current count mechanics. Fast only
    certifies the latter until dynamic threshold replanning exists.
    """

    return (
        rule.event_key == "core_hit"
        and rule.mode is TriggerMode.MODULO
        and rule.trigger_count_reducible
        and rule.raw.startswith("core_hit_count:")
        and int(rule.threshold or 0) > 0
    )


def _merged_multiples(thresholds: Iterable[int], limit: int) -> tuple[int, ...]:
    """Merge multiples of several thresholds without scanning every core hit."""

    heap = [(int(step), int(step)) for step in sorted(set(thresholds)) if step > 0]
    heapq.heapify(heap)
    out: list[int] = []
    last = 0
    while heap:
        value, step = heapq.heappop(heap)
        if value > limit:
            break
        if value != last:
            out.append(value)
            last = value
        heapq.heappush(heap, (value + step, step))
    return tuple(out)


def expected_core_boundaries_for_blocks(
    actor: int,
    blocks: Iterable[ShotBlock],
    *,
    hits_per_shot: int,
    core_probability: float,
    thresholds: Iterable[int],
) -> tuple[WeaponTriggerBoundary, ...]:
    """Materialize only meaningful expected ``core_hit_count:N`` crossings.

    Moris expected mode adds ``P_core`` once per physical hit/pellet and emits a
    logical ``core_hit`` each time that fractional accumulator reaches 1. Fast
    uses the equivalent cumulative expectation, but skips all logical core hits
    that cannot satisfy any compiled modulo threshold. SG/multi-muzzle weapons
    therefore still count every physical hit while avoiding global bullet events.
    """

    rows = tuple(block for block in blocks if block.count > 0)
    hit_width = max(1, int(hits_per_shot))
    probability = min(1.0, max(0.0, float(core_probability)))
    expected_per_shot = hit_width * probability
    if not rows or expected_per_shot <= 0.0:
        return ()

    steps = tuple(sorted({int(value) for value in thresholds if int(value) > 0}))
    if not steps:
        return ()

    total_shots = sum(block.count for block in rows)
    total_emitted = int(math.floor(total_shots * expected_per_shot + _EPS))
    if total_emitted <= 0:
        return ()

    crossings = _merged_multiples(steps, total_emitted)
    if not crossings:
        return ()

    out: list[WeaponTriggerBoundary] = []
    block_index = 0
    shots_before_block = 0
    last_dispatched = 0

    for absolute_count in crossings:
        # Earliest 1-based shot after which Moris' fractional accumulator has
        # emitted at least ``absolute_count`` logical core-hit events. Multiple
        # pellet crossings inside one SG shot intentionally share one timestamp.
        shot_number = max(
            1,
            int(math.ceil(absolute_count / expected_per_shot - _EPS)),
        )
        while (
            block_index < len(rows)
            and shot_number > shots_before_block + rows[block_index].count
        ):
            shots_before_block += rows[block_index].count
            block_index += 1
        if block_index >= len(rows):
            break
        block = rows[block_index]
        offset = shot_number - shots_before_block - 1
        time = block.first_time + offset * block.interval
        out.append(
            WeaponTriggerBoundary(
                time=time,
                actor=actor,
                event_key="core_hit",
                count_increment=absolute_count - last_dispatched,
            )
        )
        last_dispatched = absolute_count

    return tuple(out)


def simulate_static_expected_core_boundaries(
    squad: CompiledSquad,
    *,
    duration: float,
    core_probability_by_actor: Mapping[int, float],
    effect_filter: Callable[[CompiledEffect], bool] | None = None,
) -> tuple[WeaponTriggerBoundary, ...]:
    """Compile actor-selective expected core-count boundaries from shot blocks."""

    allow = effect_filter or (lambda effect: True)
    blocks_by_actor = compile_static_shot_blocks(squad, duration=duration)
    out: list[WeaponTriggerBoundary] = []

    for actor, member in enumerate(squad.members):
        thresholds = {
            int(rule.threshold or 0)
            for effect in member.effects
            if allow(effect)
            for rule in effect.triggers
            if is_static_expected_core_count_rule(rule)
        }
        if not thresholds:
            continue
        spec = compile_normal_attack_spec(member)
        out.extend(
            expected_core_boundaries_for_blocks(
                actor,
                blocks_by_actor[actor],
                hits_per_shot=spec.hits_per_shot,
                core_probability=core_probability_by_actor.get(actor, 0.0),
                thresholds=thresholds,
            )
        )

    # Equal-time crossings for one actor were appended in absolute-count order;
    # Python's stable sort preserves that order while globally interleaving actors.
    out.sort(key=lambda boundary: (boundary.time, boundary.actor, boundary.event_key))
    return tuple(out)
