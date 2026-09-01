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
    is_last_bullet: bool = False


class MultiSignalChargeCadenceRuntime(DynamicChargeCadenceRuntime):
    """Dynamic SR/RL cadence with several signals on one physical shot.

    The base runtime already fast-forwards unchanged charge/reload spans and
    materializes only meaningful full-charge boundaries. This layer adds generic
    ``hit_count:N`` thresholds and an actor-selective literal
    ``full_charge_hit`` producer. The latter promotes every full-charge shot only
    for actors that actually own an executable raw consumer; unrelated charge
    actors remain aggregated and no global every-shot loop is introduced.

    The score path may additionally promote selected charge actors to every-shot
    boundaries. That promotion is opt-in and installed before ``start()``. The
    score callback runs after the physical shot has advanced ammo state but before
    post-shot ``full_charge_hit`` / ``hit_count`` effects are dispatched, matching
    Moris' damage-before-hit-notify ordering without teaching the generic runtime
    about damage formulas.

    Moris ``hit_count`` advances once per charge attack, independent of pellet or
    muzzle multiplicity. ``pellet_hit`` is the separate per-hit stream, so a
    multi-hit charge weapon does not need intra-shot hit_count expansion here.
    """

    __slots__ = (
        "_hit_thresholds",
        "_raw_full_charge_actors",
        "_score_actors",
        "_score_shot_sink",
    )

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
        self._score_actors: frozenset[int] = frozenset()
        self._score_shot_sink: Callable[[int, float], None] | None = None

        # A charge actor may be interesting only because of generic hit_count or
        # a literal full_charge_hit consumer. Add it before start() initializes
        # actor state; static weapon planners will then skip the same actor.
        actors = set(self.actors)
        for actor in interesting:
            if str(squad.members[actor].weapon.get("fire_mode") or "") == "charge":
                actors.add(actor)
        self.actors = tuple(sorted(actors))

    def attach_score_shot_sink(
        self,
        actors: tuple[int, ...] | frozenset[int],
        sink: Callable[[int, float], None],
    ) -> None:
        """Promote selected charge actors to physical-shot score boundaries.

        This must be installed before ``start()`` so no early shot can be
        fast-forwarded under the old boundary set. Only charge weapons are
        accepted; auto/MG dynamic scoring is deliberately a separate slice.
        """

        if self._states:
            raise RuntimeError("Fast score shot sink must be attached before weapon start")
        selected = frozenset(int(actor) for actor in actors)
        for actor in selected:
            if actor < 0 or actor >= len(self.squad.members):
                raise IndexError(f"actor out of range: {actor}")
            if str(self.squad.members[actor].weapon.get("fire_mode") or "") != "charge":
                raise NotImplementedError(
                    "Fast dynamic score shot sink only supports charge weapons: "
                    + self.squad.members[actor].name
                )
        self._score_actors = selected
        self._score_shot_sink = sink
        if selected:
            self.actors = tuple(sorted(set(self.actors) | set(selected)))

    def emits_every_charge_shot(self, actor: int) -> bool:
        """Whether this runtime materializes every physical charge shot for actor."""
        return actor in self.actors and (
            self.emits_each_charge_hit
            or actor in self._raw_full_charge_actors
            or actor in self._score_actors
        )

    def _shot_is_boundary(self, actor: int, absolute_count: int) -> bool:
        if actor in self._score_actors or actor in self._raw_full_charge_actors:
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

        if actor in self._score_actors:
            if self._score_shot_sink is None:
                raise RuntimeError("Fast dynamic score actor has no shot sink")
            # Score every physical charge shot before any post-shot trigger can
            # mutate damage-facing state for the next shot.
            self._score_shot_sink(actor, float(event.time))

        signals: list[DynamicCountSignal] = []
        if actor in self._thresholds or actor in self._raw_full_charge_actors:
            signals.append(DynamicCountSignal("full_charge_hit", count_increment))
        if actor in self._hit_thresholds:
            signals.append(DynamicCountSignal("hit_count", count_increment))
        return DynamicChargeBoundary(
            actor,
            tuple(signals),
            is_last_bullet=self._states[actor].ammo <= 0,
        )