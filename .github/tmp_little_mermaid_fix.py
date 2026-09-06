from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"{label} anchor not found")
    p.write_text(text.replace(old, new, 1))


def patch_rapid_state() -> None:
    replace_once(
        "fast_engine/engine/dynamic_reload.py",
        '''class _RapidActorState:\n    actor: int\n    ammo: int\n    phase: str\n    phase_end: float\n    hit_count: int = 0\n''',
        '''class _RapidActorState:\n    actor: int\n    ammo: int\n    phase: str\n    phase_end: float\n    # Moris keeps a nominal auto-fire deadline separate from the 60 Hz tick on\n    # which that deadline is observed. The field is inert for ordinary Fast\n    # rapid slices and is used only by the certified squad-ammo lifecycle.\n    fire_deadline: float = 0.0\n    hit_count: int = 0\n''',
        "rapid nominal deadline field",
    )


def patch_rapid_lattice() -> None:
    p = Path("fast_engine/engine/dynamic_rapid.py")
    text = p.read_text()
    if "from .frame_lattice import moris_observed_tick\n" not in text:
        anchor = "from .scheduler import EventKind, ScheduledEvent\n"
        if anchor not in text:
            raise SystemExit("rapid lattice import anchor not found")
        text = text.replace(
            anchor,
            anchor + "from .frame_lattice import moris_observed_tick\n",
            1,
        )

    old = '''    def _after_shot(self, st: _RapidActorState, shot_time: float) -> None:\n        # Moris cools MG warmup in _tick_auto immediately before the next real\n        # shot. Doing it here handles ordinary reloads and long cover intervals\n        # uniformly and avoids double-cooling when a reload completes in cover.\n        self._cool_warmup_before_shot(st, shot_time)\n        super()._after_shot(st, shot_time)\n'''
    new = '''    def _after_shot(self, st: _RapidActorState, shot_time: float) -> None:\n        # Moris cools MG warmup in _tick_auto immediately before the next real\n        # shot. Doing it here handles ordinary reloads and long cover intervals\n        # uniformly and avoids double-cooling when a reload completes in cover.\n        self._cool_warmup_before_shot(st, shot_time)\n        if not self._squad_ammo_thresholds:\n            super()._after_shot(st, shot_time)\n            return\n\n        # Exact squad-ammo ownership needs physical shot timestamps, not merely\n        # continuous-rate damage integration. Moris advances next_fire_time from\n        # the *nominal* previous deadline, then the outer 60 Hz loop observes that\n        # deadline on its first qualifying tick. Do not feed the observed shot\n        # time back into the next deadline or a 24/s weapon drifts by half a frame.\n        hits = self._hits_per_shot(st.actor)\n        inter = self._shot_interval(st)\n        st.ammo -= 1\n        st.hit_count += 1\n        st.pellet_count += hits\n        st.last_shot = float(shot_time)\n        st.last_inter = inter\n        st.fire_deadline = float(st.fire_deadline) + inter\n        st.phase = "reload_wait" if st.ammo <= 0 else "firing"\n        st.phase_end = moris_observed_tick(\n            st.fire_deadline, horizon=self.duration\n        )\n'''
    if old not in text:
        raise SystemExit("rapid after-shot anchor not found")
    text = text.replace(old, new, 1)

    old = '''    def _finish_nonshot_phase(\n        self,\n        st: _RapidActorState,\n        transition_time: float,\n    ) -> None:\n        actor = st.actor\n        weapon = self.squad.members[actor].weapon\n        if st.phase == "reload_wait":\n            factor = self._reload_factor(actor, transition_time)\n            st.phase = "reloading"\n            st.phase_end = transition_time + (\n                float(weapon.get("reload_start_delay", 0.0))\n                + float(weapon.get("reload_time", 0.0))\n            ) * factor\n            return\n        if st.phase == "reloading":\n            st.ammo = self._full_ammo(actor, transition_time)\n            factor = self._reload_factor(actor, transition_time)\n            st.phase = "firing"\n            st.phase_end = transition_time + float(\n                weapon.get("post_reload_delay", 0.0)\n            ) * factor\n            return\n        raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")\n'''
    new = '''    def _finish_nonshot_phase(\n        self,\n        st: _RapidActorState,\n        transition_time: float,\n    ) -> None:\n        actor = st.actor\n        weapon = self.squad.members[actor].weapon\n        if not self._squad_ammo_thresholds:\n            if st.phase == "reload_wait":\n                factor = self._reload_factor(actor, transition_time)\n                st.phase = "reloading"\n                st.phase_end = transition_time + (\n                    float(weapon.get("reload_start_delay", 0.0))\n                    + float(weapon.get("reload_time", 0.0))\n                ) * factor\n                return\n            if st.phase == "reloading":\n                st.ammo = self._full_ammo(actor, transition_time)\n                factor = self._reload_factor(actor, transition_time)\n                st.phase = "firing"\n                st.phase_end = transition_time + float(\n                    weapon.get("post_reload_delay", 0.0)\n                ) * factor\n                return\n            raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")\n\n        # Empty-magazine reload is noticed only on an outer Moris tick. Reload\n        # completion and post-reload delay are likewise observed on ticks. The\n        # first shot after completion resets next_fire_time to that observed tick.\n        if st.phase == "reload_wait":\n            factor = self._reload_factor(actor, transition_time)\n            deadline = float(transition_time) + (\n                float(weapon.get("reload_start_delay", 0.0))\n                + float(weapon.get("reload_time", 0.0))\n            ) * factor\n            st.phase = "reloading"\n            st.phase_end = moris_observed_tick(deadline, horizon=self.duration)\n            return\n        if st.phase == "reloading":\n            st.ammo = self._full_ammo(actor, transition_time)\n            factor = self._reload_factor(actor, transition_time)\n            deadline = float(transition_time) + float(\n                weapon.get("post_reload_delay", 0.0)\n            ) * factor\n            first_shot = moris_observed_tick(deadline, horizon=self.duration)\n            st.phase = "firing"\n            st.phase_end = first_shot\n            st.fire_deadline = first_shot\n            return\n        raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")\n'''
    if old not in text:
        raise SystemExit("rapid nonshot anchor not found")
    text = text.replace(old, new, 1)
    p.write_text(text)


def patch_pre_shot_scoring() -> None:
    replace_once(
        "fast_engine/engine/burst_runtime.py",
        '''        def score_before_event(event) -> None:\n            if score_observer is None:\n                return\n            score_observer.consume_until(event.time, inclusive=False)\n            if event.phase >= 30:\n                score_observer.consume_until(event.time, inclusive=True)\n''',
        '''        def score_before_event(event) -> None:\n            if score_observer is None:\n                return\n            score_observer.consume_until(event.time, inclusive=False)\n            # PRE_SHOT_BOUNDARY exists specifically to run after ammo decrement\n            # but before the threshold-crossing normal attack is scored. Consuming\n            # =t here would advance that shot and stale its token before dispatch.\n            if event.phase >= 30 and event.kind is not EventKind.PRE_SHOT_BOUNDARY:\n                score_observer.consume_until(event.time, inclusive=True)\n''',
        "pre-shot score ordering",
    )


patch_rapid_state()
patch_rapid_lattice()
patch_pre_shot_scoring()
