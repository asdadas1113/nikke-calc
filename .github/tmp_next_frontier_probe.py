from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected one replacement, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1))


def insert_before(rel: str, marker: str, block: str) -> None:
    path = ROOT / rel
    text = path.read_text()
    count = text.count(marker)
    if count != 1:
        raise RuntimeError(f"{rel}: expected one marker, found {count}: {marker[:100]!r}")
    path.write_text(text.replace(marker, block + marker, 1))


# weapon.py: generic MG cross-type defaults and suspended base-charge lifecycle.
replace_once(
    "fast_engine/engine/weapon.py",
    '    "SR": {\n',
    '''    "MG": {\n        "fire_mode": "auto_warmup",\n        "fire_rate": 1.0,\n        "fire_rate_max": 70.0,\n        "warmup_bullets": 41.39917201655967,\n        "warmup_cooldown_time": 1.0,\n        "post_fire_delay": 0.0,\n        "post_reload_delay": 0.0,\n        "reload_start_delay": 0.0,\n        "cover_during_delay": False,\n        "charge_time": 0.0,\n        "pellets": 1,\n        "muzzles": 1,\n        "is_clip": False,\n        "normal_hit_coeff": 1.0,\n        "core_base_diameter": 10.0,\n        "core_acc_slope": 0.0,\n        "core_model_n": 2.55,\n        "control": {},\n    },\n    "SR": {\n''',
)
replace_once(
    "fast_engine/engine/weapon.py",
    '        "_mode_only_actors",\n',
    '        "_mode_only_actors", "_suspended_weapon_change_actors",\n',
)
replace_once(
    "fast_engine/engine/weapon.py",
    '        self._mode_only_actors: frozenset[int] = frozenset()\n',
    '        self._mode_only_actors: frozenset[int] = frozenset()\n        self._suspended_weapon_change_actors: frozenset[int] = frozenset()\n',
)
insert_before(
    "fast_engine/engine/weapon.py",
    '    def is_mode_only_charge_active(self, actor: int, now: float) -> bool:\n',
    '''    def attach_suspended_weapon_change_actors(\n        self, actors: tuple[int, ...] | frozenset[int]\n    ) -> None:\n        """Suspend base charge progression while an owned non-charge mode is active."""\n        if self._states:\n            raise RuntimeError("Fast suspended weapon-change actors must be attached before weapon start")\n        selected = frozenset(int(actor) for actor in actors)\n        if any(actor < 0 or actor >= len(self.squad.members) for actor in selected):\n            raise IndexError("Fast suspended weapon-change actor out of range")\n        if any(\n            str(self.squad.members[actor].weapon.get("fire_mode") or "") != "charge"\n            for actor in selected\n        ):\n            raise NotImplementedError("Fast suspended weapon-change base must be charge")\n        self._suspended_weapon_change_actors = selected\n        self.actors = tuple(sorted(set(self.actors) | set(selected)))\n\n''',
)
replace_once(
    "fast_engine/engine/weapon.py",
    '        st = self._states[actor]\n        while True:\n',
    '        st = self._states[actor]\n        if actor in self._suspended_weapon_change_actors and st.weapon_change_id is not None:\n            return\n        while True:\n',
)
replace_once(
    "fast_engine/engine/weapon.py",
    '        src = self._states[actor]\n        st = replace(src)\n',
    '        src = self._states[actor]\n        if actor in self._suspended_weapon_change_actors and src.weapon_change_id is not None:\n            return None\n        st = replace(src)\n',
)
insert_before(
    "fast_engine/engine/weapon.py",
    '            while st.phase != "charging" and st.phase_end <= now + _EPS:\n',
    '''            if actor in self._suspended_weapon_change_actors:\n                current_wc_id = self._weapon_change_id(actor, now)\n                was_active = st.weapon_change_id is not None\n                is_active = current_wc_id is not None\n                if is_active:\n                    if not was_active or current_wc_id != st.weapon_change_id:\n                        st.weapon_change_id = current_wc_id\n                        st.pending_weapon_change_refill = False\n                        self._invalidate(st)\n                    continue\n                if was_active:\n                    # Moris freezes the base charge state while the temporary\n                    # rapid weapon owns CharState.tick. Mode exit restores a\n                    # live-full base magazine and resumes an already-matured\n                    # phase on the first outer frame observing raw expiry.\n                    st.weapon_change_id = None\n                    st.pending_weapon_change_refill = False\n                    st.ammo = self._full_ammo(actor, now)\n                    resume = self._observe_phase_boundary(float(now))\n                    if st.phase_end <= resume + _EPS:\n                        st.phase_end = resume\n                    st.signature = self._signature(actor, now)\n                    self._invalidate(st)\n                    self._plan(actor, now)\n                    self.state.set_ammo(actor, st.ammo)\n                    continue\n\n''',
)

# dynamic_reload.py: dormant mode-only rapid actors and effective MG cadence.
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    '        "_effective_weapon_actors",\n',
    '        "_effective_weapon_actors",\n        "_mode_only_rapid_actors",\n',
)
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    '        self._effective_weapon_actors: frozenset[int] = frozenset()\n',
    '        self._effective_weapon_actors: frozenset[int] = frozenset()\n        self._mode_only_rapid_actors: frozenset[int] = frozenset()\n',
)
insert_before(
    "fast_engine/engine/dynamic_reload.py",
    '    def attach_effective_weapon(\n',
    '''    def attach_mode_only_rapid_actors(\n        self, actors: tuple[int, ...] | frozenset[int]\n    ) -> None:\n        if self._states:\n            raise RuntimeError("Fast mode-only rapid actors must be attached before weapon start")\n        selected = frozenset(int(actor) for actor in actors)\n        if any(actor < 0 or actor >= len(self.squad.members) for actor in selected):\n            raise IndexError("Fast mode-only rapid actor out of range")\n        self._mode_only_rapid_actors = selected\n\n''',
)
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    '''            mode = str(member.weapon.get("fire_mode") or "auto")\n            if mode not in {"auto", "auto_warmup"}:\n                raise NotImplementedError(\n                    "Fast dynamic rapid reload only supports auto/MG weapons: "\n                    + member.name\n                )\n''',
    '''            mode = str(member.weapon.get("fire_mode") or "auto")\n            if mode not in {"auto", "auto_warmup"} and actor not in self._mode_only_rapid_actors:\n                raise NotImplementedError(\n                    "Fast dynamic rapid reload only supports auto/MG or owned mode-only rapid weapons: "\n                    + member.name\n                )\n''',
)
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    '''    def _shot_interval(self, st: _RapidActorState) -> float:\n        machine = self._machine(st.actor)\n        weapon = self._weapon(st.actor, st.phase_end)\n        mode = str(weapon.get("fire_mode") or "auto")\n        if mode == "auto":\n            base_rate = max(float(self.squad.members[st.actor].weapon.get("fire_rate") or 1.0), 1e-9)\n            static_factor = machine._fixed_rate() / base_rate\n            rate = min(60.0, max(0.01, float(weapon.get("fire_rate") or base_rate) * static_factor))\n            return 1.0 / rate\n\n        rate = machine._mg_rate(st.warmup)\n        inter = 1.0 / rate\n        cap = float(self.squad.members[st.actor].weapon.get("warmup_bullets") or 1.0)\n        warmup_speed = self.effects.sum_stat(\n            st.actor,\n            "mg_warmup_speed_pct",\n            now=st.phase_end,\n        )\n        warm_inc = max(0.0, 1.0 + warmup_speed / 100.0)\n        st.warmup = min(cap, st.warmup + warm_inc)\n        return inter\n''',
    '''    def _shot_interval(self, st: _RapidActorState) -> float:\n        machine = self._machine(st.actor)\n        weapon = self._weapon(st.actor, st.phase_end)\n        mode = str(weapon.get("fire_mode") or "auto")\n        static_factor = max(0.01, 1.0 + machine.mods.attack_speed_pct / 100.0)\n        if mode == "auto":\n            rate = min(\n                60.0,\n                max(0.01, float(weapon.get("fire_rate") or 1.0) * static_factor),\n            )\n            return 1.0 / rate\n        if mode != "auto_warmup":\n            raise NotImplementedError(f"Fast rapid effective fire_mode={mode!r}")\n\n        fr_min = float(weapon.get("fire_rate") or 1.0)\n        fr_max = float(weapon.get("fire_rate_max") or fr_min)\n        cap = float(weapon.get("warmup_bullets") or 1.0)\n        base = fr_min + (fr_max - fr_min) * min(st.warmup, cap) / cap\n        rate = min(60.0, max(0.01, base * static_factor))\n        inter = 1.0 / rate\n        warmup_speed = self.effects.sum_stat(\n            st.actor,\n            "mg_warmup_speed_pct",\n            now=st.phase_end,\n        )\n        warm_inc = max(0.0, 1.0 + warmup_speed / 100.0)\n        st.warmup = min(cap, st.warmup + warm_inc)\n        return inter\n''',
)
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    '''    def start(self, now: float = 0.0) -> None:\n        for actor in self.actors:\n            full = self._full_ammo(actor, now)\n            st = _RapidActorState(\n                actor=actor,\n                ammo=full,\n                phase="firing",\n                phase_end=float(now),\n                fire_deadline=float(now),\n                signature=self._signature(actor, now),\n            )\n            self._states[actor] = st\n            self.state.set_ammo(actor, full)\n            self._plan(actor, now)\n''',
    '''    def start(self, now: float = 0.0) -> None:\n        for actor in self.actors:\n            if actor in self._mode_only_rapid_actors:\n                self._states[actor] = _RapidActorState(\n                    actor=actor, ammo=0, phase="dormant", phase_end=float("inf"),\n                    fire_deadline=float("inf"), signature=None,\n                )\n                continue\n            full = self._full_ammo(actor, now)\n            st = _RapidActorState(\n                actor=actor,\n                ammo=full,\n                phase="firing",\n                phase_end=float(now),\n                fire_deadline=float(now),\n                signature=self._signature(actor, now),\n            )\n            self._states[actor] = st\n            self.state.set_ammo(actor, full)\n            self._plan(actor, now)\n''',
)
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    '''    def sync(self, now: float) -> None:\n        for actor in self.actors:\n            st = self._states[actor]\n            signature = self._signature(actor, now)\n''',
    '''    def sync(self, now: float) -> None:\n        for actor in self.actors:\n            st = self._states[actor]\n            if actor in self._mode_only_rapid_actors:\n                continue\n            signature = self._signature(actor, now)\n''',
)

# dynamic_rapid.py: source-frame entry, whole-hit phase seed, residual flush.
insert_before(
    "fast_engine/engine/dynamic_rapid.py",
    '\ndef is_supported_rapid_cover_control(member) -> bool:\n',
    '''\n@dataclass(frozen=True, slots=True)\nclass DynamicRapidResidualToken:\n    actor: int\n    count_increment: int\n\n''',
)
replace_once(
    "fast_engine/engine/dynamic_rapid.py",
    '        "_squad_ammo_dispatched_count", "_moris_frame_observed_actors",\n',
    '        "_squad_ammo_dispatched_count", "_moris_frame_observed_actors",\n        "_event_count_getter",\n',
)
replace_once(
    "fast_engine/engine/dynamic_rapid.py",
    '        self._moris_frame_observed_actors: set[int] = set()\n',
    '        self._moris_frame_observed_actors: set[int] = set()\n        self._event_count_getter: Callable[[int, str], int] | None = None\n',
)
insert_before(
    "fast_engine/engine/dynamic_rapid.py",
    '    def attach_score_sink(\n',
    '''    def attach_event_count_getter(\n        self, callback: Callable[[int, str], int]\n    ) -> None:\n        self._event_count_getter = callback\n\n    def sync_mode_only_rapid(self, now: float) -> None:\n        """Synchronize owned charge->rapid sessions before base-charge resume."""\n        for actor in self._mode_only_rapid_actors:\n            st = self._states.get(actor)\n            if st is None:\n                continue\n            weapon = self._weapon(actor, float(now))\n            is_active = (\n                weapon.get("_weapon_change_effect_id") is not None\n                and str(weapon.get("fire_mode") or "") in {"auto", "auto_warmup"}\n            )\n            was_active = st.phase != "dormant"\n            if is_active:\n                signature = self._signature(actor, float(now))\n                if not was_active:\n                    if self._event_count_getter is None:\n                        raise RuntimeError("Fast mode-only rapid actor has no event-count getter")\n                    source = moris_observed_tick(\n                        float(now), horizon=self.duration, epsilon=1e-9\n                    )\n                    seed = int(self._event_count_getter(actor, "hit_count"))\n                    st.ammo = self._full_ammo(actor, float(now))\n                    st.phase = "firing"\n                    st.phase_end = source\n                    st.fire_deadline = source\n                    st.hit_count = seed\n                    st.dispatched_hit_count = seed\n                    st.pellet_count = 0\n                    st.dispatched_pellet_count = 0\n                    st.warmup = 0.0\n                    st.last_shot = -999.0\n                    st.last_inter = 0.0\n                    st.signature = signature\n                    self._invalidate(st)\n                    self._plan(actor, source)\n                    self.state.set_ammo(actor, st.ammo)\n                elif signature != st.signature:\n                    st.signature = signature\n                    self._invalidate(st)\n                    self._plan(actor, float(now))\n                continue\n\n            if not was_active:\n                continue\n            residual = st.hit_count - st.dispatched_hit_count\n            if residual < 0:\n                raise RuntimeError("Fast mode-only rapid hit-count phase regressed")\n            if residual:\n                self.scheduler.schedule(\n                    float(now), EventKind.WEAPON_BOUNDARY, actor=actor,\n                    payload=DynamicRapidResidualToken(actor, residual),\n                )\n                st.dispatched_hit_count = st.hit_count\n            st.ammo = 0\n            st.phase = "dormant"\n            st.phase_end = float("inf")\n            st.fire_deadline = float("inf")\n            st.signature = None\n            st.warmup = 0.0\n            st.last_inter = 0.0\n            self._invalidate(st)\n            self.state.set_ammo(actor, 0)\n\n''',
)
replace_once(
    "fast_engine/engine/dynamic_rapid.py",
    '''    def _cool_warmup_before_shot(self, st: _RapidActorState, shot_time: float) -> None:\n        weapon = self.squad.members[st.actor].weapon\n        if str(weapon.get("fire_mode") or "") != "auto_warmup":\n            return\n''',
    '''    def _cool_warmup_before_shot(self, st: _RapidActorState, shot_time: float) -> None:\n        weapon = self._weapon(st.actor, float(shot_time))\n        if str(weapon.get("fire_mode") or "") != "auto_warmup":\n            return\n''',
)
replace_once(
    "fast_engine/engine/dynamic_rapid.py",
    '        inter = st.last_inter or (1.0 / max(self._machine(st.actor)._mg_rate(st.warmup), 0.01))\n',
    '''        if st.last_inter:\n            inter = st.last_inter\n        else:\n            machine = self._machine(st.actor)\n            factor = max(0.01, 1.0 + machine.mods.attack_speed_pct / 100.0)\n            fr_min = float(weapon.get("fire_rate") or 1.0)\n            fr_max = float(weapon.get("fire_rate_max") or fr_min)\n            cap = float(weapon.get("warmup_bullets") or 1.0)\n            base = fr_min + (fr_max - fr_min) * min(st.warmup, cap) / cap\n            inter = 1.0 / min(60.0, max(0.01, base * factor))\n''',
)
insert_before(
    "fast_engine/engine/dynamic_rapid.py",
    '    def begin_full_burst(\n',
    '''    def handle_boundary(self, event: ScheduledEvent) -> DynamicRapidBoundary | None:\n        token = event.payload\n        if isinstance(token, DynamicRapidResidualToken):\n            if token.count_increment <= 0:\n                return None\n            return DynamicRapidBoundary(\n                token.actor,\n                (DynamicRapidCountSignal("hit_count", token.count_increment),),\n            )\n        return super().handle_boundary(event)\n\n''',
)

# dispatcher.py: exact charge->finite infinite-MG shape and read-only count access.
insert_before(
    "fast_engine/engine/dispatcher.py",
    '    @classmethod\n    def _temporary_self_rapid_to_single_charge_weapon_change_shape_supported(\n',
    '''    @classmethod\n    def _temporary_self_charge_to_rapid_weapon_change_shape_supported(\n        cls, effect: "CompiledEffect"\n    ) -> bool:\n        """Certify one finite self charge -> ordinary infinite-MG session."""\n        params = effect.parameters\n        return (\n            effect.capability.disposition is CapabilityDisposition.PLANNED\n            and set(effect.capability.blockers) == {\n                "stat:None", "field:weapon_type", "field:damage_coeff",\n                "field:max_ammo",\n            }\n            and effect.effect_type == "weapon_change"\n            and effect.target_spec.mode is TargetMode.SELF\n            and effect.target_spec.runtime_supported\n            and bool(effect.name)\n            and effect.duration is not None and float(effect.duration) > 0.0\n            and effect.max_stack in (None, 1, 1.0)\n            and effect.max_trigger is None\n            and effect.tick_interval is None\n            and not effect.condition_rules\n            and set(params) == {"weapon_type", "damage_coeff", "max_ammo"}\n            and params.get("weapon_type") == "MG"\n            and params.get("max_ammo") == -1\n            and isinstance(params.get("damage_coeff"), (int, float))\n            and float(params.get("damage_coeff")) > 0.0\n            and len(effect.triggers) == 1\n            and effect.triggers[0].mode is TriggerMode.EVENT\n            and effect.triggers[0].event_key == "burst_cast"\n        )\n\n''',
)
insert_before(
    "fast_engine/engine/dispatcher.py",
    '    def _temporary_self_rapid_to_single_charge_weapon_change_runtime_supported(\n',
    '''    def _temporary_self_charge_to_rapid_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n        if not self._temporary_self_charge_to_rapid_weapon_change_shape_supported(effect):\n            return False\n        member = self.squad.members[effect.actor]\n        return (\n            str(member.weapon.get("fire_mode") or "") == "charge"\n            and not member.weapon.get("control")\n            and not member.weapon.get("is_clip")\n        )\n\n''',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''            self._temporary_self_charge_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n''',
    '''            self._temporary_self_charge_weapon_change_runtime_supported(effect)\n            or self._temporary_self_charge_to_rapid_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n''',
)
insert_before(
    "fast_engine/engine/dispatcher.py",
    '    def control_block_until(self, actor: int, now: float) -> float | None:\n',
    '''    def event_count(self, owner: int, event_key: str) -> int:\n        """Read one actor-scoped trigger count without mutating dispatcher state."""\n        return int(self._event_counts.get((int(owner), str(event_key)), 0))\n\n''',
)

# dynamic_weapon.py: register the actor on both sparse cadence runtimes.
replace_once(
    "fast_engine/engine/dynamic_weapon.py",
    '        "_mode_only_weapon_change_ids",\n',
    '        "_mode_only_weapon_change_ids",\n        "_mode_only_rapid_actors",\n',
)
insert_before(
    "fast_engine/engine/dynamic_weapon.py",
    '        self._external_weapon_block_until=None\n',
    '''        mode_only_rapid_ids = {\n            effect.actor: effect.effect_id\n            for effect in squad.effects\n            if effect.effect_type == "weapon_change"\n            and effect_filter(effect)\n            and str(squad.members[effect.actor].weapon.get("fire_mode") or "") == "charge"\n            and effect.parameters.get("weapon_type") == "MG"\n            and effect.parameters.get("max_ammo") == -1\n        }\n        self._mode_only_rapid_actors = frozenset(mode_only_rapid_ids)\n        if self._mode_only_rapid_actors:\n            self.attach_suspended_weapon_change_actors(self._mode_only_rapid_actors)\n''',
)
replace_once(
    "fast_engine/engine/dynamic_weapon.py",
    '''        self._rapid_reload = DynamicRapidCadenceRuntime(\n            squad,\n            effects,\n            state,\n            scheduler,\n            duration=duration,\n            effect_filter=effect_filter,\n        )\n        rapid_weapon_change_actors = frozenset(\n''',
    '''        self._rapid_reload = DynamicRapidCadenceRuntime(\n            squad,\n            effects,\n            state,\n            scheduler,\n            duration=duration,\n            effect_filter=effect_filter,\n        )\n        if self._mode_only_rapid_actors:\n            self._rapid_reload.attach_mode_only_rapid_actors(self._mode_only_rapid_actors)\n        rapid_weapon_change_actors = frozenset(\n''',
)
replace_once(
    "fast_engine/engine/dynamic_weapon.py",
    '''            and effect.parameters.get("weapon_type") == "SMG"\n        )\n        if rapid_weapon_change_actors:\n''',
    '''            and effect.parameters.get("weapon_type") == "SMG"\n        ) | self._mode_only_rapid_actors\n        if rapid_weapon_change_actors:\n''',
)
insert_before(
    "fast_engine/engine/dynamic_weapon.py",
    '    def _combined_weapon_block_until(self, actor: int, now: float) -> float | None:\n',
    '''    def attach_event_count_getter(\n        self, callback: Callable[[int, str], int]\n    ) -> None:\n        self._rapid_reload.attach_event_count_getter(callback)\n\n''',
)
replace_once(
    "fast_engine/engine/dynamic_weapon.py",
    '''    def sync(self, now: float) -> None:\n        was_active={\n''',
    '''    def sync(self, now: float) -> None:\n        # Flush compressed MG hit-count residual before base charge resume.\n        self._rapid_reload.sync_mode_only_rapid(float(now))\n        was_active={\n''',
)

# burst_runtime.py: read-only count phase bridge.
replace_once(
    "fast_engine/engine/burst_runtime.py",
    '        self.weapons.attach_weapon_block_until(self.dispatcher.control_block_until)\n',
    '        self.weapons.attach_weapon_block_until(self.dispatcher.control_block_until)\n        self.weapons.attach_event_count_getter(self.dispatcher.event_count)\n',
)

# score.py: exact proof and dual-runtime actor routing; wider modes stay closed.
insert_before(
    "fast_engine/engine/score.py",
    'def _temporary_self_rapid_to_single_charge_weapon_change_score_supported(\n',
    '''def _temporary_self_charge_to_rapid_weapon_change_score_supported(\n    squad: CompiledSquad, effect\n) -> bool:\n    if not TriggerDispatcher._temporary_self_charge_to_rapid_weapon_change_shape_supported(effect):\n        return False\n    actor = effect.actor\n    member = squad.members[actor]\n    if not (\n        str(member.weapon.get("fire_mode") or "") == "charge"\n        and not member.weapon.get("control")\n        and not member.weapon.get("is_clip")\n        and effect.name\n    ):\n        return False\n    if (\n        member.weapon.get("cover_during_delay")\n        and _reload_speed_positive_upper_bound(squad, actor) >= 100.0 - 1e-9\n    ):\n        return False\n    related = tuple(\n        other for other in squad.effects\n        if other.effect_type == "weapon_change"\n        and actor in _possible_ally_targets(squad, other)\n    )\n    if len(related) != 1 or related[0].effect_id != effect.effect_id:\n        return False\n    name = effect.name\n    for other in squad.effects:\n        if other.effect_id == effect.effect_id:\n            continue\n        if (\n            any(rule.key == name for rule in other.condition_rules)\n            or any((rule.event_key or "") == f"event:state_end:{name}" for rule in other.triggers)\n            or other.parameters.get("target_effect") == name\n            or other.parameters.get("scaling_ref") == name\n        ):\n            return False\n    forbidden = {\n        "pellet_hit", "on_attack", "crit_hit", "core_hit",\n        "last_bullet", "last_bullet_fire", "full_reload", "event:full_reload",\n        "squad_ammo_consume",\n    }\n    for other in squad.members[actor].effects:\n        for rule in other.triggers:\n            key = rule.event_key or ""\n            if key == "hit_count":\n                if not (\n                    rule.mode is TriggerMode.MODULO\n                    and rule.trigger_count_reducible\n                    and int(rule.threshold or 0) > 0\n                ):\n                    return False\n            elif key in forbidden and TriggerDispatcher.is_executable_effect(other):\n                return False\n    if any(\n        TriggerDispatcher.is_executable_effect(other)\n        and any(rule.event_key == "squad_body_hit" for rule in other.triggers)\n        for other in squad.effects\n    ):\n        return False\n    return True\n\n\n''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''        len(weapon_changes) == 1\n        and _temporary_self_charge_weapon_change_score_supported(squad, weapon_changes[0])\n''',
    '''        len(weapon_changes) == 1\n        and (\n            _temporary_self_charge_weapon_change_score_supported(squad, weapon_changes[0])\n            or _temporary_self_charge_to_rapid_weapon_change_score_supported(squad, weapon_changes[0])\n        )\n''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''        if effect.effect_type == "weapon_change":\n            if not (\n                _temporary_self_charge_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n''',
    '''        if effect.effect_type == "weapon_change":\n            if not (\n                _temporary_self_charge_weapon_change_score_supported(squad, effect)\n                or _temporary_self_charge_to_rapid_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''        if effect.effect_type == "weapon_change"\n        and _temporary_self_charge_weapon_change_score_supported(squad, effect)\n    )\n    return tuple(sorted(actors))\n''',
    '''        if effect.effect_type == "weapon_change"\n        and (\n            _temporary_self_charge_weapon_change_score_supported(squad, effect)\n            or _temporary_self_charge_to_rapid_weapon_change_score_supported(squad, effect)\n        )\n    )\n    return tuple(sorted(actors))\n''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''    actors.update(\n        effect.actor\n        for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and (\n            _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n''',
    '''    actors.update(\n        effect.actor\n        for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and _temporary_self_charge_to_rapid_weapon_change_score_supported(squad, effect)\n    )\n    actors.update(\n        effect.actor\n        for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and (\n            _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n''',
)

# Existing regression: Velvet graduates; Modernia remains the wider witness.
replace_once(
    "fast_engine/tests/test_damage_moran_weapon_change_lifecycle.py",
    '''    def test_unowned_class_changing_weapon_changes_remain_blocked(self):\n        for name, blocker in (\n            ("레이드_네온벨벳", "weapon_change:벨벳:깔끔한 마무리"),\n            ("레이드_작열짬", "weapon_change:모더니아:섬멸 모드"),\n        ):\n            with self.subTest(name=name):\n                case = snapshot.SQUADS[name]\n                compiled = compile_moris_squad(spec.build_squad(list(case["members"])))\n                self.assertIn(blocker, static_score_blockers(compiled))\n''',
    '''    def test_unowned_class_changing_weapon_changes_remain_blocked(self):\n        name = "레이드_작열짬"\n        blocker = "weapon_change:모더니아:섬멸 모드"\n        case = snapshot.SQUADS[name]\n        compiled = compile_moris_squad(spec.build_squad(list(case["members"])))\n        self.assertIn(blocker, static_score_blockers(compiled))\n''',
)

# Focused checkpoint regression file.
(ROOT / "fast_engine/tests/test_damage_charge_to_rapid_weapon_change.py").write_text(r'''from __future__ import annotations

from dataclasses import replace
import unittest

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dynamic_rapid import DynamicRapidResidualToken
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import (
    _temporary_self_charge_to_rapid_weapon_change_score_supported,
    static_score_blockers,
)
from fast_engine.engine.weapon import DynamicWeaponToken

TEAM = "레이드_네온벨벳"


class ChargeToRapidWeaponChangeTest(unittest.TestCase):
    def _compiled(self):
        case = snapshot.SQUADS[TEAM]
        return compile_moris_squad(spec.build_squad(list(case["members"])))

    @staticmethod
    def _producer(compiled):
        return next(
            effect for effect in compiled.effects
            if effect.effect_type == "weapon_change"
            and compiled.members[effect.actor].name == "벨벳"
        )

    def _runtime(self, duration=20.0):
        compiled = self._compiled()
        effect = self._producer(compiled)
        actor = effect.actor
        enemy = EnemyStaticProfile(defense=31784.0, duration=duration, core_px=0.0)
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=duration, first_burst_time=3.0),
            enemy,
            damage_sink=SimpleDamageScoreSink(compiled, enemy),
        )
        charge_times = []
        runtime.weapons.attach_score_shot_sink(
            (actor,), lambda _a, t: charge_times.append(float(t))
        )
        runtime.weapons.attach_score_block_sink((actor,), lambda *_: None)
        runtime.weapons.start(0.0)
        return compiled, effect, actor, runtime, charge_times

    def _enter_first_mode(self, runtime, actor):
        charge = runtime.weapons._states[actor]
        charge.full_charge_count = 2
        charge.dispatched_count = 2
        charge.ammo = 12
        charge.phase = "charging"
        charge.charge_start = 2.8
        charge.phase_end = 3.8
        runtime.weapons._invalidate(charge)
        runtime.dispatcher.dispatch(
            BurstSignal(3.0, "hit_count", actor, actor, count_increment=2)
        )
        runtime.dispatcher.dispatch(BurstSignal(3.2, "burst_cast", actor, actor))
        runtime.weapons.sync(3.2)
        return charge

    def test_exact_public_shape_owned_and_modernia_stays_blocked(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        self.assertTrue(
            _temporary_self_charge_to_rapid_weapon_change_score_supported(compiled, effect)
        )
        self.assertNotIn("weapon_change:벨벳:깔끔한 마무리", static_score_blockers(compiled))
        case = snapshot.SQUADS["레이드_작열짬"]
        modernia = compile_moris_squad(spec.build_squad(list(case["members"])))
        self.assertIn("weapon_change:모더니아:섬멸 모드", static_score_blockers(modernia))

    def test_effective_mg_view_and_whole_hit_phase_seed(self):
        compiled, effect, actor, runtime, _ = self._runtime()
        charge = self._enter_first_mode(runtime, actor)
        changed = runtime.weapons.effective_weapon(actor, 3.2)
        self.assertEqual(changed["weapon_type"], "MG")
        self.assertEqual(changed["fire_mode"], "auto_warmup")
        self.assertEqual(changed["fire_rate"], 1.0)
        self.assertEqual(changed["fire_rate_max"], 70.0)
        self.assertAlmostEqual(changed["warmup_bullets"], 41.39917201655967)
        self.assertEqual(changed["max_ammo"], -1)
        self.assertEqual(changed["damage_coeff"], 7.0)
        self.assertTrue(changed["_moris_frame_observed"])
        rapid = runtime.weapons._rapid_reload
        st = rapid._states[actor]
        self.assertEqual((st.hit_count, st.dispatched_hit_count), (2, 2))
        self.assertEqual(st.ammo, 999999)
        self.assertAlmostEqual(st.phase_end, 3.2, places=8)
        self.assertEqual(charge.phase, "charging")
        self.assertAlmostEqual(charge.phase_end, 3.8, places=8)

    def test_first_session_matches_moris_451_shots_and_first_hit50(self):
        _, _, actor, runtime, _ = self._runtime()
        self._enter_first_mode(runtime, actor)
        rapid = runtime.weapons._rapid_reload
        st = rapid._states[actor]
        row = rapid._predict_next_boundary(actor)
        self.assertIsNotNone(row)
        when, expected = row
        self.assertEqual(expected, 50)
        self.assertAlmostEqual(when, 6.466666666666649, places=8)
        probe = replace(st)
        times = []
        while probe.phase_end < 13.2 - 1e-9:
            times.append(probe.phase_end)
            rapid._after_shot(probe, probe.phase_end)
        self.assertEqual(len(times), 451)
        self.assertAlmostEqual(times[0], 3.1999999999999935, places=8)
        self.assertAlmostEqual(times[-1], 13.183333333333568, places=8)
        self.assertEqual(probe.hit_count, 453)

    def test_exit_flushes_residual_before_live_full_same_frame_sr_resume(self):
        _, effect, actor, runtime, charge_times = self._runtime()
        charge = self._enter_first_mode(runtime, actor)
        rapid = runtime.weapons._rapid_reload
        st = rapid._states[actor]
        st.hit_count = 453
        st.dispatched_hit_count = 450
        st.ammo = 999548
        st.phase = "firing"
        st.phase_end = 13.2
        expiry = next(
            event for event in runtime.scheduler._heap
            if getattr(event.payload, "effect_id", None) == effect.effect_id
        )
        runtime.dispatcher.handle_expiry(expiry)
        runtime.weapons.sync(expiry.time)
        residual = next(
            event for event in runtime.scheduler._heap
            if isinstance(event.payload, DynamicRapidResidualToken)
        )
        resumed = next(
            event for event in runtime.scheduler._heap
            if isinstance(event.payload, DynamicWeaponToken)
            and event.payload.actor == actor
            and event.time >= 13.2 - 1e-8
        )
        self.assertLess(residual.time, resumed.time)
        self.assertAlmostEqual(resumed.time, 13.200000000000236, places=8)
        self.assertEqual(charge.ammo, 14)
        boundary = runtime.weapons.handle_boundary(residual)
        self.assertEqual(
            [(x.event_key, x.count_increment) for x in boundary.signals],
            [("hit_count", 3)],
        )
        runtime.dispatcher.dispatch(
            BurstSignal(residual.time, "hit_count", actor, actor, count_increment=3)
        )
        self.assertEqual(runtime.dispatcher.event_count(actor, "hit_count"), 453)
        shot = runtime.weapons.handle_boundary(resumed)
        self.assertIsNotNone(shot)
        self.assertEqual(charge.ammo, 13)
        self.assertEqual(charge_times, [resumed.time])

    def test_raw_second_expiry_reanchors_to_next_outer_tick(self):
        _, effect, actor, runtime, _ = self._runtime(duration=30.0)
        charge = runtime.weapons._states[actor]
        charge.weapon_change_id = effect.effect_id
        charge.phase = "charging"
        charge.charge_start = 14.733333333333695
        charge.phase_end = 15.733333333333695
        charge.ammo = 13
        runtime.weapons._invalidate(charge)
        runtime.weapons.sync(25.733333333333697)
        self.assertAlmostEqual(charge.phase_end, 25.74999999999982, places=8)
        self.assertEqual(charge.ammo, 14)

    def test_neighboring_wider_modes_fail_closed(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        variants = (
            replace(effect, duration=None),
            replace(effect, duration=0.0),
            replace(effect, parameters={**effect.parameters, "max_ammo": 300}),
            replace(effect, parameters={**effect.parameters, "weapon_type": "SMG"}),
            replace(effect, parameters={**effect.parameters, "skill_damage": True}),
            replace(effect, parameters={**effect.parameters, "favorite": 1}),
        )
        for candidate in variants:
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    _temporary_self_charge_to_rapid_weapon_change_score_supported(
                        compiled, candidate
                    )
                )


if __name__ == "__main__":
    unittest.main()
''')

print("Velvet staging patch applied")
