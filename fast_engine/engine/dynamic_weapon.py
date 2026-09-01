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
    """Dynamic SR/RL cadence with several count signals on one physical shot.

    The base runtime already fast-forwards unchanged charge/reload spans and
    materializes only meaningful full-charge boundaries.  This layer adds
    generic ``hit_count:N`` thresholds to the same physical boundary schedule,
    so a shot that advances both counters creates one scheduler event rather
    than one event per semantic counter (and still never creates a frame loop).
    """

    __slots__ = ("_hit_thresholds",)

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
            if values:
                hit_thresholds[actor] = tuple(sorted(values))
        self._hit_thresholds = hit_thresholds

        # A charge actor may be interesting only because of generic hit_count.
        # Add it to the base runtime before start() initializes actor state.
        actors = set(self.actors)
        for actor in hit_thresholds:
            if str(squad.members[actor].weapon.get("fire_mode") or "") == "charge":
                actors.add(actor)
        self.actors = tuple(sorted(actors))

    def _shot_is_boundary(self, actor: int, absolute_count: int) -> bool:
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
        if actor in self._thresholds:
            signals.append(DynamicCountSignal("full_charge_hit", count_increment))
        if actor in self._hit_thresholds:
            signals.append(DynamicCountSignal("hit_count", count_increment))
        return DynamicChargeBoundary(actor, tuple(signals))
