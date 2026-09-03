from __future__ import annotations

from pathlib import Path


def apply() -> None:
    p = Path("fast_engine/engine/dynamic_reload.py")
    text = p.read_text()
    text = text.replace(
        "from .scheduler import EventKind, EventScheduler, ScheduledEvent\n",
        "from .frame_lattice import moris_next_tick, moris_observed_tick\n"
        "from .scheduler import EventKind, EventScheduler, ScheduledEvent\n",
        1,
    )
    text = text.replace(
        "    phase_end: float\n    hit_count: int = 0\n",
        "    phase_end: float\n    nominal_end: float | None = None\n    hit_count: int = 0\n",
        1,
    )

    old = '''    def _after_shot(self, st: _RapidActorState, shot_time: float) -> None:
        hits = self._hits_per_shot(st.actor)
        inter = self._shot_interval(st)
        st.ammo -= 1
        st.hit_count += 1
        st.pellet_count += hits
        st.last_shot = shot_time
        st.last_inter = inter
        st.phase = "reload_wait" if st.ammo <= 0 else "firing"
        st.phase_end = shot_time + inter
'''
    new = '''    def _after_shot(self, st: _RapidActorState, shot_time: float) -> None:
        hits = self._hits_per_shot(st.actor)
        inter = self._shot_interval(st)
        st.ammo -= 1
        st.hit_count += 1
        st.pellet_count += hits
        st.last_shot = shot_time
        st.last_inter = inter
        st.phase = "reload_wait" if st.ammo <= 0 else "firing"
        mode = str(self.squad.members[st.actor].weapon.get("fire_mode") or "auto")
        if mode == "auto_warmup":
            base = shot_time if st.nominal_end is None else st.nominal_end
            nominal = base + inter
            if nominal <= shot_time:
                st.nominal_end = shot_time
                st.phase_end = moris_next_tick(shot_time, horizon=self.duration)
            else:
                st.nominal_end = nominal
                st.phase_end = moris_observed_tick(nominal, horizon=self.duration)
        else:
            st.phase_end = shot_time + inter
'''
    assert old in text
    text = text.replace(old, new, 1)

    old = '''        if st.phase == "reload_wait":
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
'''
    new = '''        mode = str(weapon.get("fire_mode") or "auto")
        if st.phase == "reload_wait":
            factor = self._reload_factor(actor, transition_time)
            st.phase = "reloading"
            deadline = transition_time + (
                float(weapon.get("reload_start_delay", 0.0))
                + float(weapon.get("reload_time", 0.0))
            ) * factor
            if mode == "auto_warmup":
                st.nominal_end = deadline
                st.phase_end = moris_observed_tick(deadline, horizon=self.duration)
            else:
                st.phase_end = deadline
            return
        if st.phase == "reloading":
            st.ammo = self._full_ammo(actor, transition_time)
            factor = self._reload_factor(actor, transition_time)
            next_shot = transition_time + float(
                weapon.get("post_reload_delay", 0.0)
            ) * factor
            if mode == "auto_warmup":
                if next_shot > transition_time:
                    next_shot = moris_observed_tick(next_shot, horizon=self.duration)
                cap = float(weapon.get("warmup_bullets") or 1.0)
                cooldown_time = max(float(weapon.get("warmup_cooldown_time") or 1.0), 1e-9)
                cool_rate = cap / cooldown_time
                idle = next_shot - st.last_shot
                if idle > st.last_inter * 1.5:
                    st.warmup = max(0.0, st.warmup - cool_rate * idle)
                st.nominal_end = next_shot
            st.phase = "firing"
            st.phase_end = next_shot
            return
'''
    assert old in text
    text = text.replace(old, new, 1)

    old = '''            st.phase = "reloading"
            st.phase_end = float(now) + (
                float(weapon.get("reload_start_delay", 0.0))
                + float(weapon.get("reload_time", 0.0))
            ) * factor
            self._invalidate(st)
'''
    new = '''            st.phase = "reloading"
            deadline = float(now) + (
                float(weapon.get("reload_start_delay", 0.0))
                + float(weapon.get("reload_time", 0.0))
            ) * factor
            if str(weapon.get("fire_mode") or "auto") == "auto_warmup":
                st.nominal_end = deadline
                st.phase_end = moris_observed_tick(deadline, horizon=self.duration)
            else:
                st.phase_end = deadline
            self._invalidate(st)
'''
    assert old in text
    text = text.replace(old, new, 1)

    old = '''            st = _RapidActorState(
                actor=actor,
                ammo=full,
                phase="firing",
                phase_end=float(now),
                signature=self._signature(actor, now),
            )
'''
    new = '''            st = _RapidActorState(
                actor=actor, ammo=full, phase="firing", phase_end=float(now),
                nominal_end=float(now), signature=self._signature(actor, now),
            )
'''
    assert old in text
    text = text.replace(old, new, 1)
    p.write_text(text)

    p = Path("fast_engine/engine/dynamic_rapid.py")
    text = p.read_text()
    text = text.replace(
        "from .dynamic_reload import DynamicRapidReloadRuntime, _RapidActorState\n",
        "from .dynamic_reload import DynamicRapidReloadRuntime, _RapidActorState\n"
        "from .frame_lattice import moris_observed_tick\n",
        1,
    )
    old = '''    def _finish_nonshot_phase(
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
            st.phase = "firing"
            st.phase_end = transition_time + float(
                weapon.get("post_reload_delay", 0.0)
            ) * factor
            return
        raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")
'''
    new = '''    def _finish_nonshot_phase(
        self,
        st: _RapidActorState,
        transition_time: float,
    ) -> None:
        actor = st.actor
        weapon = self.squad.members[actor].weapon
        mode = str(weapon.get("fire_mode") or "auto")
        if st.phase == "reload_wait":
            factor = self._reload_factor(actor, transition_time)
            st.phase = "reloading"
            deadline = transition_time + (
                float(weapon.get("reload_start_delay", 0.0))
                + float(weapon.get("reload_time", 0.0))
            ) * factor
            if mode == "auto_warmup":
                st.nominal_end = deadline
                st.phase_end = moris_observed_tick(deadline, horizon=self.duration)
            else:
                st.phase_end = deadline
            return
        if st.phase == "reloading":
            st.ammo = self._full_ammo(actor, transition_time)
            factor = self._reload_factor(actor, transition_time)
            next_shot = transition_time + float(
                weapon.get("post_reload_delay", 0.0)
            ) * factor
            if mode == "auto_warmup":
                if next_shot > transition_time:
                    next_shot = moris_observed_tick(next_shot, horizon=self.duration)
                # Moris resets next_fire_time to the actual reload-completion
                # frame before the first post-reload shot. Do not carry the old
                # magazine's nominal debt across a reload boundary.
                st.nominal_end = next_shot
            st.phase = "firing"
            st.phase_end = next_shot
            return
        raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")
'''
    assert old in text
    text = text.replace(old, new, 1)
    p.write_text(text)


if __name__ == "__main__":
    apply()
