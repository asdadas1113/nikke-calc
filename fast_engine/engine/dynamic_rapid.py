from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Sequence

from .dynamic_reload import (
    DynamicRapidBoundary,
    DynamicRapidCountSignal,
    DynamicRapidReloadRuntime,
    _RapidActorState,
)
from .scheduler import EventKind, ScheduledEvent
from .frame_lattice import moris_observed_tick
from .weapon import _EPS


@dataclass(frozen=True, slots=True)
class DynamicSquadAmmoToken:
    generation: int
    actor: int
    expected_hit_count: int
    expected_global_count: int
    count_increment: int


def is_supported_rapid_cover_control(member) -> bool:
    """Return whether Fast can execute this actor's current cover control exactly.

    This first control slice is deliberately narrow: non-clip auto/MG weapons,
    with no cover-during-delay special case, and exactly one control policy —
    ``cover.policy == own_full_burst`` with an optional non-negative ``extend``.
    Other controls remain fail-closed.
    """

    weapon = member.weapon
    mode = str(weapon.get("fire_mode") or "")
    if mode not in {"auto", "auto_warmup"}:
        return False
    if weapon.get("is_clip") or weapon.get("cover_during_delay"):
        return False

    control = weapon.get("control") or {}
    if not isinstance(control, dict) or set(control) != {"cover"}:
        return False
    cover = control.get("cover")
    if not isinstance(cover, dict):
        return False
    if cover.get("policy") != "own_full_burst":
        return False
    if set(cover) - {"policy", "extend"}:
        return False
    try:
        extend = float(cover.get("extend", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    return extend >= 0.0


class DynamicRapidCadenceRuntime(DynamicRapidReloadRuntime):
    """Compressed rapid cadence with live reload speed and burst-cover control.

    The base runtime owns physical auto/MG shots, reload state, and reducible
    hit/pellet boundaries. This subclass adds the first certified player-control
    interval without introducing per-frame work:

    - an actor that cast in the current burst cycle enters cover when full burst
      starts;
    - cover lasts through ``full_burst_end + extend``;
    - entering cover with a partial magazine starts a manual reload immediately
      (no empty-magazine reload-start delay), while an already-running reload is
      left untouched;
    - shots are suppressed until cover ends, and no missed-shot debt is replayed;
    - MG warmup cools once at the next real shot, using the whole idle interval;
    - while a live ``duration_bullets`` state targets this actor, each physical
      shot becomes a temporary scheduler boundary so the consuming shot can be
      scored before the state is removed.

    Exact ``event:cover`` consumers are intentionally excluded by score
    certification for this slice. Full-reload/last-bullet/raw-hit consumers are
    likewise gated elsewhere.
    """

    __slots__ = (
        "_cover_until", "_weapon_block_until", "_squad_ammo_thresholds",
        "_squad_ammo_generation", "_squad_ammo_scheduled_time",
        "_squad_ammo_dispatched_count",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cover_until: dict[int, float] = {}
        self._weapon_block_until: Callable[[int, float], float | None] | None = None
        self._squad_ammo_thresholds: tuple[int, ...] = ()
        self._squad_ammo_generation = 0
        self._squad_ammo_scheduled_time: float | None = None
        self._squad_ammo_dispatched_count = 0

    def attach_score_sink(
        self,
        actors: tuple[int, ...] | frozenset[int],
        sink: Callable[[int, int, float], None],
    ) -> None:
        selected = tuple(sorted(set(int(actor) for actor in actors)))
        # Registration must happen before any duration_bullets activation so the
        # effect store knows not to schedule a stale static Nth-shot expiry.
        self.effects.enable_dynamic_bullet_lifetime_targets(selected)
        super().attach_score_sink(selected, sink)

    def attach_squad_ammo_thresholds(self, thresholds: tuple[int, ...]) -> None:
        if self._states:
            raise RuntimeError("Fast squad-ammo thresholds must be attached before weapon start")
        values=tuple(sorted({int(value) for value in thresholds if int(value)>0}))
        if values and set(self.actors) != set(range(len(self.squad.members))):
            raise NotImplementedError("Fast squad-ammo first slice requires every squad actor on rapid runtime")
        self._squad_ammo_thresholds=values

    def _next_squad_ammo_target(self, current: int) -> int | None:
        if not self._squad_ammo_thresholds:
            return None
        return min(((current // threshold) + 1) * threshold for threshold in self._squad_ammo_thresholds)

    def _probe_next_physical_shot(self, st: _RapidActorState) -> float | None:
        while st.phase_end <= self.duration + _EPS:
            if self._postpone_firing_for_block(st):
                continue
            if st.phase == "firing":
                return float(st.phase_end)
            self._finish_nonshot_phase(st, float(st.phase_end))
        return None

    def _predict_next_squad_ammo_boundary(self) -> tuple[float, int, int, int] | None:
        if not self._squad_ammo_thresholds or not self.actors:
            return None
        probes={actor: replace(self._states[actor]) for actor in self.actors}
        current=sum(st.hit_count for st in probes.values())
        target=self._next_squad_ammo_target(current)
        if target is None:
            return None
        while current < target:
            candidates=[]
            for actor,st in probes.items():
                when=self._probe_next_physical_shot(st)
                if when is not None:
                    candidates.append((when,actor))
            if not candidates:
                return None
            when,actor=min(candidates)
            if when > self.duration + _EPS:
                return None
            st=probes[actor]
            self._after_shot(st,when)
            current += 1
            if current == target:
                return when,actor,st.hit_count,target
        return None

    def _plan_squad_ammo(self, now: float) -> None:
        if not self._squad_ammo_thresholds or self._squad_ammo_scheduled_time is not None:
            return
        row=self._predict_next_squad_ammo_boundary()
        if row is None:
            return
        when,actor,expected,target=row
        when=max(float(now),float(when))
        if when > self.duration + _EPS:
            return
        increment=target-self._squad_ammo_dispatched_count
        if increment <= 0:
            return
        self._squad_ammo_scheduled_time=when
        self.scheduler.schedule(
            when,EventKind.PRE_SHOT_BOUNDARY,actor=actor,
            payload=DynamicSquadAmmoToken(
                self._squad_ammo_generation,actor,expected,target,increment
            ),
        )

    def refresh_squad_ammo_plan(self, now: float) -> None:
        if not self._squad_ammo_thresholds:
            return
        self._squad_ammo_generation += 1
        self._squad_ammo_scheduled_time=None
        self._plan_squad_ammo(now)

    def _cover_end(self, actor: int) -> float:
        return float(self._cover_until.get(actor, -1.0))

    def attach_weapon_block_until(
        self, callback: Callable[[int, float], float | None]
    ) -> None:
        self._weapon_block_until = callback

    def _weapon_block_end(self, actor: int, now: float) -> float:
        until = self._cover_end(actor)
        if self._weapon_block_until is not None:
            control_end = self._weapon_block_until(actor, now)
            if control_end is not None:
                until = max(until, float(control_end))
        return until

    def _signature(self, actor: int, now: float) -> tuple:
        # Bullet lifetime and weapon-block activation/removal both invalidate a
        # stale compressed boundary without materializing individual shots.
        return (
            super()._signature(actor, now)
            + self.effects.dynamic_bullet_signature(actor, now=now)
            + (self._weapon_block_end(actor, now),)
        )

    def _shot_is_boundary(self, st: _RapidActorState) -> bool:
        if self.effects.has_dynamic_bullet_lifetime(st.actor, now=st.phase_end):
            return True
        return super()._shot_is_boundary(st)

    def consume_post_shot_bullet_lifetimes(self, actor: int, now: float) -> tuple[int, ...]:
        """Consume dynamic bullet states after hit signals, before last-bullet."""

        if actor not in self.actors:
            return ()
        return self.effects.consume_dynamic_bullet(actor, now=now, count=1)

    def _postpone_firing_for_block(self, st: _RapidActorState) -> bool:
        until = self._weapon_block_end(st.actor, st.phase_end)
        if st.phase == "firing" and st.phase_end < until - _EPS:
            # Control intervals are half-open. Equality is therefore available:
            # the first real shot may occur exactly at the unblock timestamp.
            st.phase_end = until
            return True
        return False

    def _cool_warmup_before_shot(self, st: _RapidActorState, shot_time: float) -> None:
        weapon = self.squad.members[st.actor].weapon
        if str(weapon.get("fire_mode") or "") != "auto_warmup":
            return
        if st.warmup <= 0.0:
            return
        idle = float(shot_time) - st.last_shot
        if idle <= 0.0:
            return
        inter = st.last_inter or (1.0 / max(self._machine(st.actor)._mg_rate(st.warmup), 0.01))
        if idle <= inter * 1.5:
            return
        cap = float(weapon.get("warmup_bullets") or 1.0)
        cooldown_time = max(float(weapon.get("warmup_cooldown_time") or 1.0), 1e-9)
        cool_rate = cap / cooldown_time
        st.warmup = max(0.0, st.warmup - cool_rate * idle)

    def _after_shot(self, st: _RapidActorState, shot_time: float) -> None:
        # Moris cools MG warmup in _tick_auto immediately before the next real
        # shot. Doing it here handles ordinary reloads and long cover intervals
        # uniformly and avoids double-cooling when a reload completes in cover.
        self._cool_warmup_before_shot(st, shot_time)
        if not self._squad_ammo_thresholds:
            super()._after_shot(st, shot_time)
            return

        # Exact squad-ammo ownership needs physical shot timestamps, not merely
        # continuous-rate damage integration. Moris advances next_fire_time from
        # the *nominal* previous deadline, then the outer 60 Hz loop observes that
        # deadline on its first qualifying tick. Do not feed the observed shot
        # time back into the next deadline or a 24/s weapon drifts by half a frame.
        hits = self._hits_per_shot(st.actor)
        inter = self._shot_interval(st)
        st.ammo -= 1
        st.hit_count += 1
        st.pellet_count += hits
        st.last_shot = float(shot_time)
        st.last_inter = inter
        st.fire_deadline = float(st.fire_deadline) + inter
        st.phase = "reload_wait" if st.ammo <= 0 else "firing"
        st.phase_end = moris_observed_tick(
            st.fire_deadline, horizon=self.duration
        )

    def _finish_nonshot_phase(
        self,
        st: _RapidActorState,
        transition_time: float,
    ) -> None:
        actor = st.actor
        weapon = self.squad.members[actor].weapon
        if not self._squad_ammo_thresholds:
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
                st.phase = "firing"
                st.phase_end = transition_time + float(
                    weapon.get("post_reload_delay", 0.0)
                ) * factor
                return
            raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")

        # Empty-magazine reload is noticed only on an outer Moris tick. Reload
        # completion and post-reload delay are likewise observed on ticks. The
        # first shot after completion resets next_fire_time to that observed tick.
        if st.phase == "reload_wait":
            factor = self._reload_factor(actor, transition_time)
            deadline = float(transition_time) + (
                float(weapon.get("reload_start_delay", 0.0))
                + float(weapon.get("reload_time", 0.0))
            ) * factor
            st.phase = "reloading"
            st.phase_end = moris_observed_tick(deadline, horizon=self.duration)
            return
        if st.phase == "reloading":
            st.ammo = self._full_ammo(actor, transition_time)
            factor = self._reload_factor(actor, transition_time)
            deadline = float(transition_time) + float(
                weapon.get("post_reload_delay", 0.0)
            ) * factor
            first_shot = moris_observed_tick(deadline, horizon=self.duration)
            st.phase = "firing"
            st.phase_end = first_shot
            st.fire_deadline = first_shot
            return
        raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")

    def _advance_actor_to(self, actor: int, t: float, *, inclusive: bool) -> None:
        st = self._states[actor]
        score_count = 0
        score_time = 0.0
        while self._due(st.phase_end, t, inclusive=inclusive):
            if self._postpone_firing_for_block(st):
                continue
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
                raise RuntimeError("Fast rapid cadence actor has no score sink")
            self._score_sink(actor, score_count, score_time)

    def _predict_next_boundary(self, actor: int) -> tuple[float, int] | None:
        st = self._states[actor]
        # Keep the base runtime's cheap copy-only prediction contract.
        from dataclasses import replace

        probe = replace(st)
        while probe.phase_end <= self.duration + _EPS:
            if self._postpone_firing_for_block(probe):
                continue
            when = probe.phase_end
            if probe.phase == "firing":
                if self._shot_is_boundary(probe):
                    return when, probe.hit_count + 1
                self._after_shot(probe, when)
                continue
            self._finish_nonshot_phase(probe, when)
        return None

    def begin_full_burst(
        self,
        now: float,
        casted: Sequence[bool],
        full_burst_end: float,
    ) -> tuple[int, ...]:
        """Enter supported actors into own-full-burst cover at ``now``.

        BurstRuntime calls this only after every full_burst_start effect has been
        delivered, so a reload begun by entering cover sees the same-start-frame
        reload-speed state Moris sees in CharState.tick.
        """

        entered: list[int] = []
        for actor in self.actors:
            if actor >= len(casted) or not casted[actor]:
                continue
            member = self.squad.members[actor]
            if not is_supported_rapid_cover_control(member):
                continue

            cover = member.weapon["control"]["cover"]
            until = float(full_burst_end) + float(cover.get("extend", 0.0) or 0.0)
            if until <= now + _EPS:
                continue

            # BurstRuntime has already advanced all weapons to ``now`` exclusive,
            # but keeping this local makes the method safe for direct unit tests.
            self._advance_actor_to(actor, now, inclusive=False)
            st = self._states[actor]
            self._cover_until[actor] = max(self._cover_end(actor), until)

            full = self._full_ammo(actor, now)
            if st.phase != "reloading" and st.ammo < full:
                # Manual cover reload: no reload_start_delay. The reload action
                # itself snapshots live reload speed at cover entry and remains
                # fixed even if that buff changes before completion.
                factor = self._reload_factor(actor, now)
                st.phase = "reloading"
                st.phase_end = float(now) + float(member.weapon.get("reload_time", 0.0)) * factor
            elif st.phase == "firing" and st.phase_end < now:
                st.phase_end = float(now)

            self._invalidate(st)
            self._plan(actor, now)
            self.state.set_ammo(actor, st.ammo)
            entered.append(actor)
        if entered:
            self.refresh_squad_ammo_plan(now)
        return tuple(entered)

    def start(self, now: float = 0.0) -> None:
        super().start(now)
        self._plan_squad_ammo(now)

    def sync(self, now: float) -> None:
        before=tuple((actor,self._states[actor].generation) for actor in self.actors if actor in self._states)
        super().sync(now)
        after=tuple((actor,self._states[actor].generation) for actor in self.actors if actor in self._states)
        if before != after:
            self.refresh_squad_ammo_plan(now)
        elif self._squad_ammo_scheduled_time is None:
            self._plan_squad_ammo(now)

    def apply_force_reload(self, targets: tuple[int, ...], now: float) -> bool:
        changed=super().apply_force_reload(targets,now)
        if changed:
            self.refresh_squad_ammo_plan(now)
        return changed

    def handle_pre_shot_boundary(self, event: ScheduledEvent) -> DynamicRapidBoundary | None:
        token=event.payload
        if not isinstance(token,DynamicSquadAmmoToken):
            return None
        if token.generation != self._squad_ammo_generation:
            return None
        if self._squad_ammo_scheduled_time is None or abs(self._squad_ammo_scheduled_time-event.time)>1e-7:
            return None

        # Moris weapon actors fire in roster order. Consume same-frame physical
        # shots belonging to earlier actors, but stop immediately before the
        # threshold-crossing actor's own shot.
        for actor in self.actors:
            self._advance_actor_to(
                actor,event.time,inclusive=actor < token.actor
            )
        st=self._states.get(token.actor)
        if st is None or st.phase != "firing" or abs(st.phase_end-event.time)>1e-7:
            self.refresh_squad_ammo_plan(event.time)
            return None
        before=sum(state.hit_count for state in self._states.values())
        if st.hit_count + 1 != token.expected_hit_count or before + 1 != token.expected_global_count:
            self.refresh_squad_ammo_plan(event.time)
            return None

        self._after_shot(st,float(event.time))
        self.state.set_ammo(token.actor,st.ammo)
        self._invalidate(st)  # invalidate any same-shot local token
        self._squad_ammo_scheduled_time=None
        self._squad_ammo_dispatched_count=token.expected_global_count

        signals=[]
        pellet_incs,pellet_last=self._crossing_increments(
            st.dispatched_pellet_count,st.pellet_count,
            self._pellet_thresholds.get(token.actor,()),
        )
        signals.extend(DynamicRapidCountSignal("pellet_hit",inc) for inc in pellet_incs)
        st.dispatched_pellet_count=pellet_last
        hit_incs,hit_last=self._crossing_increments(
            st.dispatched_hit_count,st.hit_count,
            self._hit_thresholds.get(token.actor,()),
        )
        signals.extend(DynamicRapidCountSignal("hit_count",inc) for inc in hit_incs)
        st.dispatched_hit_count=hit_last
        return DynamicRapidBoundary(
            token.actor,tuple(signals),is_last_bullet=st.ammo<=0,
            pre_signals=(DynamicRapidCountSignal("squad_ammo_consume",token.count_increment),),
            score_pending=True,
        )

    def score_pending_shot(self, actor: int, now: float) -> None:
        if self._score_sink is None:
            raise RuntimeError("Fast rapid cadence actor has no score sink")
        self._score_sink(actor,1,float(now))
