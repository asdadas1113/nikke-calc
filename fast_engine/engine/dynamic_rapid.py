from __future__ import annotations

from typing import Sequence

from .dynamic_reload import DynamicRapidReloadRuntime, _RapidActorState
from .weapon import _EPS


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

    __slots__ = ("_cover_until",)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cover_until: dict[int, float] = {}

    def _cover_end(self, actor: int) -> float:
        return float(self._cover_until.get(actor, -1.0))

    def _signature(self, actor: int, now: float) -> tuple:
        # A bullet-lifetime activation/removal changes whether every shot must be
        # materialized. Include its generation/remaining state so ordinary
        # weapon sync invalidates any stale compressed boundary immediately.
        return super()._signature(actor, now) + self.effects.dynamic_bullet_signature(
            actor, now=now
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

    def _postpone_firing_for_cover(self, st: _RapidActorState) -> bool:
        until = self._cover_end(st.actor)
        if st.phase == "firing" and st.phase_end < until - _EPS:
            # Moris exits cover at the anchor frame and then may fire on that
            # same frame. Therefore equality is not covered; only times strictly
            # before ``until`` are postponed.
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
        super()._after_shot(st, shot_time)

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
            st.ammo = self._machine(actor)._full_ammo()
            factor = self._reload_factor(actor, transition_time)
            st.phase = "firing"
            st.phase_end = transition_time + float(
                weapon.get("post_reload_delay", 0.0)
            ) * factor
            return
        raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")

    def _advance_actor_to(self, actor: int, t: float, *, inclusive: bool) -> None:
        st = self._states[actor]
        score_count = 0
        score_time = 0.0
        while self._due(st.phase_end, t, inclusive=inclusive):
            if self._postpone_firing_for_cover(st):
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
            if self._postpone_firing_for_cover(probe):
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

            full = self._machine(actor)._full_ammo()
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
        return tuple(entered)
