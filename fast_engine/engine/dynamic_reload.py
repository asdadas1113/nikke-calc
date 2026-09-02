from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, TYPE_CHECKING

from .scheduler import EventKind, EventScheduler, ScheduledEvent
from .state import StateStore
from .triggers import TriggerMode
from .weapon import (
    WeaponCadenceMachine, _EPS, _round_half_up, reducible_threshold_candidates,
)

if TYPE_CHECKING:
    from .effects import ActiveEffectStore
    from .model import CompiledEffect, CompiledSquad


@dataclass(frozen=True, slots=True)
class DynamicRapidToken:
    actor: int
    generation: int
    expected_hit_count: int


@dataclass(frozen=True, slots=True)
class DynamicRapidCountSignal:
    event_key: str
    count_increment: int


@dataclass(frozen=True, slots=True)
class DynamicRapidBoundary:
    actor: int
    signals: tuple[DynamicRapidCountSignal, ...]
    is_last_bullet: bool = False


@dataclass(slots=True)
class _RapidActorState:
    actor: int
    ammo: int
    phase: str
    phase_end: float
    hit_count: int = 0
    pellet_count: int = 0
    dispatched_hit_count: int = 0
    dispatched_pellet_count: int = 0
    generation: int = 0
    scheduled_time: float | None = None
    signature: tuple[float, ...] | None = None
    warmup: float = 0.0
    last_shot: float = -999.0
    last_inter: float = 0.0


class DynamicRapidReloadRuntime:
    """Compressed live-reload cadence for non-clip auto/MG weapons.

    Only reload speed is dynamic in this slice. Fire rate, magazine size and shot
    shape remain statically compiled, so ordinary shots and magazine transitions
    can be advanced inside the runtime without adding one scheduler event per
    bullet. The global scheduler is needed only for reducible hit/pellet trigger
    crossings; score-only actors with no such consumers remain fully compressed.

    Reload semantics mirror Moris:
    - reload_start_delay and the reload action use speed at reload start;
    - that reload duration is then fixed even if the buff changes mid-reload;
    - post_reload_delay uses speed at reload completion;
    - clip reload is deliberately excluded because each clip re-reads speed.
    """

    __slots__ = (
        "squad",
        "effects",
        "state",
        "scheduler",
        "duration",
        "effect_filter",
        "actors",
        "_machines",
        "_hit_thresholds",
        "_pellet_thresholds",
        "_last_bullet_actors",
        "_states",
        "_score_sink",
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
        self.squad = squad
        self.effects = effects
        self.state = state
        self.scheduler = scheduler
        self.duration = float(duration)
        self.effect_filter = effect_filter
        self.actors: tuple[int, ...] = ()
        self._machines: dict[int, WeaponCadenceMachine] = {}
        self._states: dict[int, _RapidActorState] = {}
        self._score_sink: Callable[[int, int, float], None] | None = None

        hit_thresholds: dict[int, tuple[int, ...]] = {}
        pellet_thresholds: dict[int, tuple[int, ...]] = {}
        last_bullet_actors: set[int] = set()
        for actor, character in enumerate(squad.members):
            hits: set[int] = set()
            pellets: set[int] = set()
            for effect in character.effects:
                if not effect_filter(effect):
                    continue
                for rule in effect.triggers:
                    if rule.event_key == "last_bullet":
                        last_bullet_actors.add(actor)
                    if rule.mode is not TriggerMode.MODULO or not rule.trigger_count_reducible:
                        continue
                    threshold = int(rule.threshold or 0)
                    if threshold <= 0:
                        continue
                    candidates = reducible_threshold_candidates(
                        effect, squad.effects, threshold
                    )
                    if rule.event_key == "hit_count":
                        hits.update(candidates)
                    elif rule.event_key == "pellet_hit":
                        pellets.update(candidates)
            if hits:
                hit_thresholds[actor] = tuple(sorted(hits))
            if pellets:
                pellet_thresholds[actor] = tuple(sorted(pellets))
        self._hit_thresholds = hit_thresholds
        self._pellet_thresholds = pellet_thresholds
        self._last_bullet_actors = frozenset(last_bullet_actors)

    def attach_score_sink(
        self,
        actors: tuple[int, ...] | frozenset[int],
        sink: Callable[[int, int, float], None],
    ) -> None:
        if self._states:
            raise RuntimeError("Fast rapid reload score sink must be attached before weapon start")
        selected = tuple(sorted(set(int(actor) for actor in actors)))
        for actor in selected:
            if actor < 0 or actor >= len(self.squad.members):
                raise IndexError(f"actor out of range: {actor}")
            member = self.squad.members[actor]
            mode = str(member.weapon.get("fire_mode") or "auto")
            if mode not in {"auto", "auto_warmup"}:
                raise NotImplementedError(
                    "Fast dynamic rapid reload only supports auto/MG weapons: "
                    + member.name
                )
            if member.weapon.get("is_clip"):
                raise NotImplementedError(
                    "Fast dynamic rapid reload clip weapon not certified: " + member.name
                )
            self._machines[actor] = WeaponCadenceMachine(
                actor,
                member,
                duration=self.duration,
            )
        self.actors = selected
        self._score_sink = sink

    def _machine(self, actor: int) -> WeaponCadenceMachine:
        return self._machines[actor]

    def _reload_factor(self, actor: int, now: float) -> float:
        speed = self.effects.sum_stat(actor, "reload_speed_pct", now=now)
        return max(0.0, 1.0 - speed / 100.0)

    @staticmethod
    def _is_static_folded_max_ammo(effect: "CompiledEffect") -> bool:
        return (
            (effect.stat or "") in {"max_ammo_pct", "max_ammo_flat"}
            and effect.effect_type == "buff"
            and effect.target_spec.mode.value == "self"
            and effect.duration in (None, -1.0)
            and not effect.condition_rules
            and bool(effect.triggers)
            and all(rule.event_key == "battle_start" for rule in effect.triggers)
        )

    def _full_ammo(self, actor: int, now: float) -> int:
        base_full = self._machine(actor)._full_ammo()
        base_weapon = int(self.squad.members[actor].weapon["max_ammo"])
        pct_gain = 0; flat_gain = 0.0
        for stat in ("max_ammo_pct", "max_ammo_flat"):
            for effect, active in self.effects.iter_stat(stat, now=now):
                if active.target != actor or self._is_static_folded_max_ammo(effect):
                    continue
                value=float(effect.value or 0.0)*active.stacks
                if stat=="max_ammo_pct": pct_gain += _round_half_up(base_weapon*value/100.0)
                else: flat_gain += value
        return max(1, base_full+pct_gain+_round_half_up(flat_gain))

    def _signature(self, actor: int, now: float) -> tuple[float, ...]:
        mode = str(self.squad.members[actor].weapon.get("fire_mode") or "auto")
        warmup_speed = (
            self.effects.sum_stat(actor, "mg_warmup_speed_pct", now=now)
            if mode == "auto_warmup"
            else 0.0
        )
        return (
            self.effects.sum_stat(actor, "reload_speed_pct", now=now),
            warmup_speed,
            float(self._full_ammo(actor, now)),
        )

    def _hits_per_shot(self, actor: int) -> int:
        return self._machine(actor)._hits_per_shot()

    def _shot_interval(self, st: _RapidActorState) -> float:
        machine = self._machine(st.actor)
        mode = str(self.squad.members[st.actor].weapon.get("fire_mode") or "auto")
        if mode == "auto":
            return 1.0 / machine._fixed_rate()

        rate = machine._mg_rate(st.warmup)
        inter = 1.0 / rate
        cap = float(self.squad.members[st.actor].weapon.get("warmup_bullets") or 1.0)
        warmup_speed = self.effects.sum_stat(
            st.actor,
            "mg_warmup_speed_pct",
            now=st.phase_end,
        )
        warm_inc = max(0.0, 1.0 + warmup_speed / 100.0)
        st.warmup = min(cap, st.warmup + warm_inc)
        return inter

    @staticmethod
    def _crosses(before: int, after: int, thresholds: tuple[int, ...]) -> bool:
        return any(before // threshold != after // threshold for threshold in thresholds)

    def _shot_is_boundary(self, st: _RapidActorState) -> bool:
        # Keep ordinary rapid shots compressed, but materialize the magazine's
        # final physical shot when an executable post-shot last_bullet consumer
        # exists. BurstRuntime dispatches last_bullet only after this shot scores.
        if st.actor in self._last_bullet_actors and st.ammo <= 1:
            return True
        next_hit = st.hit_count + 1
        if any(next_hit % threshold == 0 for threshold in self._hit_thresholds.get(st.actor, ())):
            return True
        hits = self._hits_per_shot(st.actor)
        next_pellet = st.pellet_count + hits
        return self._crosses(
            st.pellet_count,
            next_pellet,
            self._pellet_thresholds.get(st.actor, ()),
        )

    def _after_shot(self, st: _RapidActorState, shot_time: float) -> None:
        hits = self._hits_per_shot(st.actor)
        inter = self._shot_interval(st)
        st.ammo -= 1
        st.hit_count += 1
        st.pellet_count += hits
        st.last_shot = shot_time
        st.last_inter = inter
        st.phase = "reload_wait" if st.ammo <= 0 else "firing"
        st.phase_end = shot_time + inter

    def _finish_nonshot_phase(
        self,
        st: _RapidActorState,
        transition_time: float,
    ) -> None:
        actor = st.actor
        weapon = self.squad.members[actor].weapon
        if st.phase == "reload_wait":
            factor = self._reload_factor(actor, transition_time)
            st.phase = "reloading"
            st.phase_end = transition_time + (
                float(weapon.get("reload_start_delay", 0.0))
                + float(weapon.get("reload_time", 0.0))
            ) * factor
            return
        if st.phase == "reloading":
            st.ammo = self._full_ammo(actor, transition_time)
            factor = self._reload_factor(actor, transition_time)
            next_shot = transition_time + float(
                weapon.get("post_reload_delay", 0.0)
            ) * factor
            if str(weapon.get("fire_mode") or "auto") == "auto_warmup":
                machine = self._machine(actor)
                cap = float(weapon.get("warmup_bullets") or 1.0)
                cooldown_time = max(float(weapon.get("warmup_cooldown_time") or 1.0), 1e-9)
                cool_rate = cap / cooldown_time
                idle = next_shot - st.last_shot
                if idle > st.last_inter * 1.5:
                    st.warmup = max(0.0, st.warmup - cool_rate * idle)
            st.phase = "firing"
            st.phase_end = next_shot
            return
        raise RuntimeError(f"unexpected rapid reload phase: {st.phase!r}")

    @staticmethod
    def _due(when: float, t: float, *, inclusive: bool) -> bool:
        return when <= t + _EPS if inclusive else when < t - _EPS

    def _advance_actor_to(self, actor: int, t: float, *, inclusive: bool) -> None:
        st = self._states[actor]
        score_count = 0
        score_time = 0.0
        while self._due(st.phase_end, t, inclusive=inclusive):
            when = st.phase_end
            if when > self.duration + _EPS:
                break
            if st.phase == "firing":
                if self._shot_is_boundary(st):
                    break
                self._after_shot(st, when)
                score_count += 1
                score_time = when
                continue
            self._finish_nonshot_phase(st, when)

        self.state.set_ammo(actor, st.ammo)
        if score_count:
            if self._score_sink is None:
                raise RuntimeError("Fast rapid reload actor has no score sink")
            self._score_sink(actor, score_count, score_time)

    def advance_to(self, t: float, *, inclusive: bool = False) -> None:
        for actor in self.actors:
            self._advance_actor_to(actor, t, inclusive=inclusive)

    def apply_force_reload(self, targets: tuple[int, ...], now: float) -> bool:
        selected = tuple(dict.fromkeys(int(actor) for actor in targets))
        if not selected or any(actor not in self.actors for actor in selected):
            return False

        self.advance_to(float(now), inclusive=False)
        for actor in selected:
            st = self._states.get(actor)
            if st is None:
                return False
            if st.phase == "reloading":
                continue
            weapon = self.squad.members[actor].weapon
            factor = self._reload_factor(actor, float(now))
            st.ammo = 0
            st.phase = "reloading"
            st.phase_end = float(now) + (
                float(weapon.get("reload_start_delay", 0.0))
                + float(weapon.get("reload_time", 0.0))
            ) * factor
            self._invalidate(st)
            self._plan(actor, float(now))
            self.state.set_ammo(actor, 0)
        return True

    def _predict_next_boundary(self, actor: int) -> tuple[float, int] | None:
        st = replace(self._states[actor])
        while st.phase_end <= self.duration + _EPS:
            when = st.phase_end
            if st.phase == "firing":
                if self._shot_is_boundary(st):
                    return when, st.hit_count + 1
                self._after_shot(st, when)
                continue
            self._finish_nonshot_phase(st, when)
        return None

    def _invalidate(self, st: _RapidActorState) -> None:
        st.generation += 1
        st.scheduled_time = None

    def _plan(self, actor: int, now: float) -> None:
        st = self._states[actor]
        if st.scheduled_time is not None:
            return
        row = self._predict_next_boundary(actor)
        if row is None:
            return
        when, expected = row
        when = max(float(now), float(when))
        if when > self.duration + _EPS:
            return
        st.generation += 1
        st.scheduled_time = when
        self.scheduler.schedule(
            when,
            EventKind.WEAPON_BOUNDARY,
            actor=actor,
            payload=DynamicRapidToken(actor, st.generation, expected),
        )

    def start(self, now: float = 0.0) -> None:
        for actor in self.actors:
            full = self._full_ammo(actor, now)
            st = _RapidActorState(
                actor=actor,
                ammo=full,
                phase="firing",
                phase_end=float(now),
                signature=self._signature(actor, now),
            )
            self._states[actor] = st
            self.state.set_ammo(actor, full)
            self._plan(actor, now)

    def sync(self, now: float) -> None:
        for actor in self.actors:
            st = self._states[actor]
            signature = self._signature(actor, now)
            if signature != st.signature:
                st.signature = signature
                self._invalidate(st)
            if st.scheduled_time is None:
                self._plan(actor, now)
            self.state.set_ammo(actor, st.ammo)

    @staticmethod
    def _crossing_increments(
        dispatched: int,
        actual: int,
        thresholds: tuple[int, ...],
    ) -> tuple[tuple[int, ...], int]:
        crossings: set[int] = set()
        for threshold in thresholds:
            value = ((dispatched // threshold) + 1) * threshold
            while value <= actual:
                crossings.add(value)
                value += threshold
        last = dispatched
        increments: list[int] = []
        for absolute in sorted(crossings):
            increments.append(absolute - last)
            last = absolute
        return tuple(increments), last

    def handle_boundary(self, event: ScheduledEvent) -> DynamicRapidBoundary | None:
        token = event.payload
        if not isinstance(token, DynamicRapidToken):
            return None
        st = self._states.get(token.actor)
        if st is None:
            return None
        if token.generation != st.generation:
            return None
        if st.scheduled_time is None or abs(st.scheduled_time - event.time) > 1e-7:
            return None

        self.advance_to(event.time, inclusive=False)
        st = self._states[token.actor]
        if st.phase != "firing" or abs(st.phase_end - event.time) > 1e-7:
            return None
        if st.hit_count + 1 != token.expected_hit_count:
            return None

        self._after_shot(st, float(event.time))
        st.scheduled_time = None
        self.state.set_ammo(token.actor, st.ammo)
        if self._score_sink is None:
            raise RuntimeError("Fast rapid reload actor has no score sink")
        self._score_sink(token.actor, 1, float(event.time))

        signals: list[DynamicRapidCountSignal] = []
        pellet_incs, pellet_last = self._crossing_increments(
            st.dispatched_pellet_count,
            st.pellet_count,
            self._pellet_thresholds.get(token.actor, ()),
        )
        for increment in pellet_incs:
            signals.append(DynamicRapidCountSignal("pellet_hit", increment))
        st.dispatched_pellet_count = pellet_last

        hit_incs, hit_last = self._crossing_increments(
            st.dispatched_hit_count,
            st.hit_count,
            self._hit_thresholds.get(token.actor, ()),
        )
        for increment in hit_incs:
            signals.append(DynamicRapidCountSignal("hit_count", increment))
        st.dispatched_hit_count = hit_last

        return DynamicRapidBoundary(
            token.actor,
            tuple(signals),
            is_last_bullet=st.ammo <= 0,
        )
