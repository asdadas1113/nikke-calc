from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any, Iterable


class TriggerMode(str, Enum):
    """Precompiled timing semantics.

    The runtime emits a small event key and only evaluates rules already indexed
    under that key.  No parsed timing strings are scanned in the hot path.
    """

    EVENT = "event"                 # exact event key
    PERIODIC = "periodic"           # every:Ns, scheduled directly
    MODULO = "modulo"               # every Nth matching event
    AT_LEAST = "at_least"           # Nth and every later matching event
    EXACT = "exact"                 # exactly Nth matching event
    CONDITIONAL_MODULO = "conditional_modulo"
    CONDITIONAL_AT_LEAST = "conditional_at_least"
    VALUE_AT_LEAST = "value_at_least"  # event payload/metric >= threshold


@dataclass(frozen=True, slots=True)
class TriggerRule:
    raw: str
    event_key: str | None
    mode: TriggerMode
    threshold: float | None = None
    group: str | None = None
    interval: float | None = None
    trigger_count_reducible: bool = False

    @property
    def is_periodic(self) -> bool:
        return self.mode is TriggerMode.PERIODIC


@dataclass(frozen=True, slots=True)
class IndexedTrigger:
    effect_id: int
    rule_index: int


@dataclass(frozen=True, slots=True)
class TriggerIndex:
    """Immutable event lookup table for one compiled squad.

    Both global and actor-scoped views are compiled once. Most runtime events
    are delivered to one effect owner, so `for_actor_event()` avoids filtering a
    squad-wide bucket on every hit/burst.
    """

    by_event: dict[str, tuple[IndexedTrigger, ...]]
    periodic: tuple[IndexedTrigger, ...]
    by_actor_event: tuple[dict[str, tuple[IndexedTrigger, ...]], ...]
    periodic_by_actor: tuple[tuple[IndexedTrigger, ...], ...]

    def for_event(self, event_key: str) -> tuple[IndexedTrigger, ...]:
        return self.by_event.get(event_key, ())

    def for_actor_event(self, actor: int, event_key: str) -> tuple[IndexedTrigger, ...]:
        if not 0 <= actor < len(self.by_actor_event):
            raise IndexError(f"actor out of range: {actor}")
        return self.by_actor_event[actor].get(event_key, ())

    @classmethod
    def from_effects(cls, effects: Iterable[Any], *, actor_count: int | None = None) -> "TriggerIndex":
        rows = tuple(effects)
        inferred = 0 if not rows else max(effect.actor for effect in rows) + 1
        actor_count = inferred if actor_count is None else actor_count
        if actor_count < inferred:
            raise ValueError("actor_count is smaller than effect actor indexes")
        buckets: dict[str, list[IndexedTrigger]] = {}
        periodic: list[IndexedTrigger] = []
        actor_buckets: list[dict[str, list[IndexedTrigger]]] = [dict() for _ in range(actor_count)]
        actor_periodic: list[list[IndexedTrigger]] = [[] for _ in range(actor_count)]
        for effect in rows:
            for rule_index, rule in enumerate(effect.triggers):
                item = IndexedTrigger(effect.effect_id, rule_index)
                if rule.is_periodic:
                    periodic.append(item)
                    actor_periodic[effect.actor].append(item)
                elif rule.event_key is not None:
                    buckets.setdefault(rule.event_key, []).append(item)
                    actor_buckets[effect.actor].setdefault(rule.event_key, []).append(item)
        return cls(
            by_event={key: tuple(items) for key, items in buckets.items()},
            periodic=tuple(periodic),
            by_actor_event=tuple(
                {key: tuple(items) for key, items in actor.items()} for actor in actor_buckets
            ),
            periodic_by_actor=tuple(tuple(items) for items in actor_periodic),
        )


def _positive_number(raw: str, *, timing: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"invalid timing threshold {timing!r}") from exc
    if not isfinite(value) or value <= 0:
        raise ValueError(f"timing threshold must be > 0: {timing!r}")
    return value


def _positive_int(raw: str, *, timing: str) -> int:
    value = _positive_number(raw, timing=timing)
    if not value.is_integer():
        raise ValueError(f"timing threshold must be an integer: {timing!r}")
    return int(value)


def resolve_timing_placeholder(timing: str, trigger_value: float | int | None) -> str:
    if "{0}" not in timing:
        return timing
    if trigger_value is None:
        raise ValueError(f"timing placeholder has no trigger value: {timing!r}")
    value = float(trigger_value)
    rendered = str(int(value)) if value.is_integer() else format(value, "g")
    return timing.replace("{0}", rendered)


def compile_trigger_rule(timing: str, *, trigger_value: float | int | None = None) -> TriggerRule:
    """Compile the current Moris timing grammar into branch-light metadata.

    Semantics intentionally mirror `BuffManager._timing_to_index_key()` and
    `_timing_match()` for the timing families Fast intends to consume later.
    Conditions are compiled separately; conditional count rules only mark the
    count phase here.
    """

    timing = resolve_timing_placeholder(str(timing), trigger_value)

    if timing == "passive":
        return TriggerRule(timing, "battle_start", TriggerMode.EVENT)
    if timing.startswith("every:"):
        raw = timing.split(":", 1)[1]
        if raw.endswith("s"):
            raw = raw[:-1]
        interval = _positive_number(raw, timing=timing)
        return TriggerRule(timing, None, TriggerMode.PERIODIC, interval=interval)

    if timing.startswith("conditional_burst_cast_count:"):
        parts = timing.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"invalid conditional burst timing: {timing!r}")
        return TriggerRule(
            timing, "burst_cast", TriggerMode.CONDITIONAL_AT_LEAST,
            threshold=float(_positive_int(parts[2], timing=timing)), group=parts[1],
        )
    if timing.startswith("conditional_hit_count:"):
        parts = timing.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"invalid conditional hit timing: {timing!r}")
        return TriggerRule(
            timing, "hit_count", TriggerMode.CONDITIONAL_MODULO,
            threshold=float(_positive_int(parts[2], timing=timing)), group=parts[1],
        )

    if timing.startswith("burst_cast_count:"):
        n = _positive_int(timing.split(":", 1)[1], timing=timing)
        return TriggerRule(timing, "burst_cast", TriggerMode.AT_LEAST, threshold=float(n))
    if timing.startswith("full_burst_start_count:"):
        n = _positive_int(timing.split(":", 1)[1], timing=timing)
        return TriggerRule(timing, "full_burst_start", TriggerMode.AT_LEAST, threshold=float(n))
    if timing.startswith("full_burst_start_exact:"):
        n = _positive_int(timing.split(":", 1)[1], timing=timing)
        return TriggerRule(timing, "full_burst_start", TriggerMode.EXACT, threshold=float(n))
    if timing.startswith("full_burst_end_count:"):
        n = _positive_int(timing.split(":", 1)[1], timing=timing)
        return TriggerRule(timing, "full_burst_end", TriggerMode.AT_LEAST, threshold=float(n))

    if timing.startswith("hit_count:"):
        parts = timing.split(":", 2)
        if len(parts) == 3 and not parts[1].lstrip("-").isdigit():
            n = _positive_int(parts[2], timing=timing)
            return TriggerRule(
                timing, f"hit_count:{parts[1]}", TriggerMode.MODULO,
                threshold=float(n), trigger_count_reducible=True,
            )
        n = _positive_int(parts[1], timing=timing)
        return TriggerRule(
            timing, "hit_count", TriggerMode.MODULO,
            threshold=float(n), trigger_count_reducible=True,
        )

    modulo_specs = (
        ("full_charge_count:", "full_charge_hit", True),
        ("core_hit_count:", "core_hit", True),
        ("core_hit:", "core_hit", True),
        ("crit_hit_count:", "crit_hit", True),
        ("pellet_hit_count:", "pellet_hit", True),
        ("pellet_hit:", "pellet_hit", True),
        ("received_hit_count:", "received_hit", False),
        ("received_hit:", "received_hit", False),
        ("non_full_charge_hit_count:", "non_full_charge_hit", False),
        ("squad_ammo_consume:", "squad_ammo_consume", False),
        ("part_hit_count:", "squad_part_hit", False),
        ("body_hit_count:", "squad_body_hit", False),
    )
    for prefix, key, reducible in modulo_specs:
        if timing.startswith(prefix):
            n = _positive_int(timing[len(prefix):], timing=timing)
            return TriggerRule(
                timing, key, TriggerMode.MODULO, threshold=float(n),
                trigger_count_reducible=reducible,
            )

    if timing.startswith("hp_below_count:"):
        parts = timing.split(":")
        if len(parts) != 3:
            raise ValueError(f"invalid hp count timing: {timing!r}")
        n = _positive_int(parts[2], timing=timing)
        return TriggerRule(timing, f"hp_below:{parts[1]}", TriggerMode.EXACT, threshold=float(n))

    if timing.startswith("charge_hold_count:"):
        parts = timing.split(":")
        if len(parts) != 3:
            raise ValueError(f"invalid charge hold count timing: {timing!r}")
        n = _positive_int(parts[2], timing=timing)
        return TriggerRule(timing, f"charge_hold:{parts[1]}", TriggerMode.MODULO, threshold=float(n))

    if timing.startswith("multi_hit:"):
        n = _positive_int(timing.split(":", 1)[1], timing=timing)
        # Moris emits `multi_hit:<actual>`; Fast can dispatch all multi-hit rules
        # from one key and compare the actual hit count to this threshold.
        return TriggerRule(timing, "multi_hit", TriggerMode.VALUE_AT_LEAST, threshold=float(n))

    # These are exact event names; no runtime string interpretation is needed.
    return TriggerRule(timing, timing, TriggerMode.EVENT)
