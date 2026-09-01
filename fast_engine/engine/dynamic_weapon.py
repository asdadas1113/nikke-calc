from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from .scheduler import EventScheduler, ScheduledEvent
from .state import StateStore
from .triggers import TriggerMode
from .weapon import DynamicChargeCadenceRuntime

if TYPE_CHECKING:
    from .effects import ActiveEffectStore
    from .model import CompiledEffect, CompiledSquad


@dataclass(frozen=True, slots=True)
class DynamicCountSignal:
    event_key: str
    count_increment: int


@dataclass(frozen=True, slots=True)
class DynamicChargeBoundary:
    actor: int
    signals: tuple[DynamicCountSignal, ...]


class MultiSignalChargeCadenceRuntime(DynamicChargeCadenceRuntime):
    """Dynamic SR/RL cadence with several signals on one physical shot.

    The base runtime already fast-forwards unchanged charge/reload spans and
    materializes only meaningful full-charge boundaries. This layer adds generic
    ``hit_count:N`` thresholds and an actor-selective literal
    ``full_charge_hit`` producer. The latter promotes every full-charge shot only
    for actors that actually own an executable raw consumer; unrelated charge
    actors remain aggregated and no global every-shot loop is introduced.

    Moris ``hit_count`` advances once per charge attack, independent of pellet or
    muzzle multiplicity. ``pellet_hit`` is the separate per-hit stream, so a
    multi-hit charge weapon does not need intra-shot hit_count expansion here.
    """

    __slots__ = ("_hit_thresholds", "_raw_full_charge_actors")

    def __init__(
        self,
        squad: "CompiledSquad",
        effects: "ActiveEffectStore",
        state: StateStore,
        scheduler: EventScheduler,
        *,
        duration: float,
        effect_filter: Callable[["CompiledEffect"], bool],
    ) -> None:
        super().__init__(
            squad,
            effects,
            state,
            scheduler,
            duration=duration,
            effect_filter=effect_filter,
        )

        hit_thresholds: dict[int, tuple[int, ...]] = {}
        raw_full_charge_actors: set[int] = set()
        for actor, character in enumerate(squad.members):
            values: set[int] = set()
            for effect in character.effects:
                if not effect_filter(effect):
                    continue
                for rule in effect.triggers:
                    if (
                        rule.event_key == "hit_count"
                        and rule.mode is TriggerMode.MODULO
                        and rule.trigger_count_reducible
                    ):
                        threshold = int(rule.threshold or 0)
                        if threshold > 0:
                            values.add(threshold)
                    if (
                        rule.event_key == "full_charge_hit"
                        and rule.mode is TriggerMode.EVENT
                    ):
                        raw_full_charge_actors.add(actor)
            if values:
                hit_thresholds[actor] = tuple(sorted(values))

        interesting = set(hit_thresholds) | raw_full_charge_actors
        for actor in interesting:
            character = squad.members[actor]
            if str(character.weapon.get("fire_mode") or "") != "charge":
                if actor in raw_full_charge_actors:
                    raise NotImplementedError(
                        "Fast raw full_charge_hit consumer on non-charge weapon is not certified: "
                        + character.name
                    )

        self._hit_thresholds = hit_thresholds
        self._raw_full_charge_actors = frozenset(raw_full_charge_actors)

        # A charge actor may be interesting only because of generic hit_count or
        # a literal full_charge_hit consumer. Add it before start() initializes
        # actor state; static weapon planners will then skip the same actor.
        actors = set(self.actors)
        for actor in interesting:
            if str(squad.members[actor].weapon.get("fire_mode") or "") == "charge":
                actors.add(actor)
        self.actors = tuple(sorted(actors))

    def _shot_is_boundary(self, actor: int, absolute_count: int) -> bool:
        if actor in self._raw_full_charge_actors:
            return True
        if super()._shot_is_boundary(actor, absolute_count):
            return True
        return any(
            absolute_count % threshold == 0
            for threshold in self._hit_thresholds.get(actor, ())
        )

    def handle_boundary(self, event: ScheduledEvent) -> DynamicChargeBoundary | None:
        row = super().handle_boundary(event)
        if row is None:
            return None
        actor, _base_event_key, count_increment = row

        signals: list[DynamicCountSignal] = []
        if actor in self._thresholds or actor in self._raw_full_charge_actors:
            signals.append(DynamicCountSignal("full_charge_hit", count_increment))
        if actor in self._hit_thresholds:
            signals.append(DynamicCountSignal("hit_count", count_increment))
        return DynamicChargeBoundary(actor, tuple(signals))
