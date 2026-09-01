from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, TYPE_CHECKING

from .dynamic_rapid import DynamicRapidCadenceRuntime
from .scheduler import EventScheduler, ScheduledEvent
from .state import StateStore
from .triggers import TriggerMode
from .weapon import DynamicChargeCadenceRuntime

if TYPE_CHECKING:
    from .effects import ActiveEffectStore
    from .model import CompiledEffect, CompiledSquad


_INTERNAL_BULLET_CONSUME_EVENT = "__fast_consume_dynamic_bullet_lifetime__"


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
    """Composite dynamic weapon runtime for the currently certified slices.

    Charge weapons keep the existing generation-based SR/RL cadence runtime.
    Selected non-clip auto/MG actors use a compressed rapid cadence runtime that
    supports live reload speed and the first exact player-control interval
    (``cover.policy == own_full_burst``). The two paths share the scheduler but
    never share actor state: charge actors remain in the base runtime while rapid
    actors live in ``_rapid_reload``.

    Score callbacks run after a physical shot has advanced ammo state but before
    post-shot hit/full-charge/last-bullet effects are dispatched. This preserves
    Moris' damage-before-hit-notify ordering without introducing a frame loop.
    """

    __slots__ = (
        "_hit_thresholds",
        "_raw_full_charge_actors",
        "_score_actors",
        "_score_shot_sink",
        "_rapid_reload",
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
        self._rapid_reload = DynamicRapidCadenceRuntime(
            squad,
            effects,
            state,
            scheduler,
            duration=duration,
            effect_filter=effect_filter,
        )

        actors = set(self.actors)
        for actor in interesting:
            if str(squad.members[actor].weapon.get("fire_mode") or "") == "charge":
                actors.add(actor)
        self.actors = tuple(sorted(actors))

    @property
    def all_dynamic_actors(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.actors) | set(self._rapid_reload.actors)))

    def attach_score_shot_sink(
        self,
        actors: tuple[int, ...] | frozenset[int],
        sink: Callable[[int, float], None],
    ) -> None:
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
        # Charge duration_bullets must be registered before battle-start
        # activation so ActiveEffectStore does not schedule a stale static
        # Nth-shot expiry. Rapid registration is additive in the store.
        self.effects.enable_dynamic_bullet_lifetime_targets(selected)
        self._score_actors = selected
        self._score_shot_sink = sink
        if selected:
            self.actors = tuple(sorted(set(self.actors) | set(selected)))

    def attach_score_block_sink(
        self,
        actors: tuple[int, ...] | frozenset[int],
        sink: Callable[[int, int, float], None],
    ) -> None:
        self._rapid_reload.attach_score_sink(actors, sink)

    def begin_full_burst(
        self,
        now: float,
        casted: Sequence[bool],
        full_burst_end: float,
    ) -> tuple[int, ...]:
        return self._rapid_reload.begin_full_burst(now, casted, full_burst_end)

    @staticmethod
    def _ammo_charge_gain(full: int, stat: str, value: float) -> int:
        if stat == "ammo_charge_pct":
            # Moris uses Python round() on final effective maximum ammo.
            return int(round(float(full) * float(value) / 100.0))
        if stat == "ammo_charge_flat":
            return int(value)
        raise ValueError(f"unsupported ammo charge stat: {stat}")

    def apply_ammo_charge(
        self,
        stat: str,
        targets: tuple[int, ...],
        value: float,
        now: float,
    ) -> bool:
        """Apply an instant ammo refill to dynamic weapon state.

        All recipients are validated before mutation. Reload-cancel-on-full is
        intentionally outside this slice; certification rejects such controls.
        """

        if value < 0.0:
            return False
        selected = tuple(dict.fromkeys(int(actor) for actor in targets))
        dynamic = set(self.all_dynamic_actors)
        if not selected or any(actor not in dynamic for actor in selected):
            return False

        # Bring every selected actor to immediately before the instant effect.
        # BurstRuntime already does this globally, but keeping it local makes the
        # callback safe for direct tests and future non-burst instant sources.
        self.advance_to(float(now), inclusive=False)

        for actor in selected:
            if actor in self._rapid_reload.actors:
                runtime = self._rapid_reload
                st = runtime._states.get(actor)
                if st is None:
                    return False
                full = runtime._machine(actor)._full_ammo()
                gain = self._ammo_charge_gain(full, stat, value)
                st.ammo = min(full, st.ammo + gain)
                if st.phase == "reload_wait" and st.ammo > 0:
                    # The empty-magazine probe has not started reloading yet.
                    # Refilled ammo therefore preserves that next fire probe.
                    st.phase = "firing"
                    st.phase_end = max(float(now), st.phase_end)
                runtime._invalidate(st)
                runtime._plan(actor, float(now))
                self.state.set_ammo(actor, st.ammo)
                continue

            st = self._states.get(actor)
            if st is None:
                return False
            full = self._full_ammo(actor, float(now))
            gain = self._ammo_charge_gain(full, stat, value)
            st.ammo = min(full, st.ammo + gain)
            if st.phase == "post_fire_reload" and st.ammo > 0:
                # Refill arrived after the last shot but before reload start.
                # Keep the existing post-fire boundary, then charge again.
                st.phase = "post_fire"
            self._invalidate(st)
            self._plan(actor, float(now))
            self.state.set_ammo(actor, st.ammo)
        return True

    def consume_post_shot_bullet_lifetimes(self, actor: int, now: float) -> tuple[int, ...]:
        return self._rapid_reload.consume_post_shot_bullet_lifetimes(actor, now)

    def emits_every_charge_shot(self, actor: int) -> bool:
        return actor in self.actors and (
            self.emits_each_charge_hit
            or actor in self._raw_full_charge_actors
            or actor in self._score_actors
        )

    def supports_dynamic_last_bullet(self, actor: int) -> bool:
        if actor in self._rapid_reload.actors:
            return False
        return self.emits_every_charge_shot(actor)

    def emits_squad_body_hit(self, actor: int) -> bool:
        return actor in self.actors and self.emits_each_charge_hit

    def _shot_is_boundary(self, actor: int, absolute_count: int) -> bool:
        if actor in self._score_actors or actor in self._raw_full_charge_actors:
            return True
        if super()._shot_is_boundary(actor, absolute_count):
            return True
        return any(
            absolute_count % threshold == 0
            for threshold in self._hit_thresholds.get(actor, ())
        )

    def start(self, now: float = 0.0) -> None:
        super().start(now)
        self._rapid_reload.start(now)

    def advance_to(self, t: float, *, inclusive: bool = False) -> None:
        super().advance_to(t, inclusive=inclusive)
        self._rapid_reload.advance_to(t, inclusive=inclusive)

    def sync(self, now: float) -> None:
        super().sync(now)
        self._rapid_reload.sync(now)

    def handle_boundary(self, event: ScheduledEvent) -> DynamicChargeBoundary | None:
        rapid = self._rapid_reload.handle_boundary(event)
        if rapid is not None:
            signals = [
                DynamicCountSignal(row.event_key, row.count_increment)
                for row in rapid.signals
            ]
            if self._rapid_reload.effects.has_dynamic_bullet_lifetime(
                rapid.actor, now=float(event.time)
            ):
                # BurstRuntime dispatches boundary signals in tuple order. This
                # internal signal therefore runs after pellet/hit_count effects,
                # matching Moris consume_bullet_buffs, and before rapid
                # last_bullet (which remains fail-closed in this slice).
                signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))
            return DynamicChargeBoundary(
                rapid.actor,
                tuple(signals),
                is_last_bullet=rapid.is_last_bullet,
            )

        row = super().handle_boundary(event)
        if row is None:
            return None
        actor, _base_event_key, count_increment = row

        if actor in self._score_actors:
            if self._score_shot_sink is None:
                raise RuntimeError("Fast dynamic score actor has no shot sink")
            self._score_shot_sink(actor, float(event.time))

        signals: list[DynamicCountSignal] = []
        if actor in self._thresholds or actor in self._raw_full_charge_actors:
            signals.append(DynamicCountSignal("full_charge_hit", count_increment))
        if actor in self._hit_thresholds:
            signals.append(DynamicCountSignal("hit_count", count_increment))
        if self.effects.has_dynamic_bullet_lifetime(actor, now=float(event.time)):
            # The consuming charge shot is scored above and its hit/full-charge
            # signals are delivered first. Remove bullet-duration state only at
            # the same post-shot point used by the rapid runtime.
            signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))
        return DynamicChargeBoundary(
            actor,
            tuple(signals),
            is_last_bullet=self._states[actor].ammo <= 0,
        )
