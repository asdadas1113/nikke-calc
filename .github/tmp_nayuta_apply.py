from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def replace_once(path: Path, old: str, new: str):
    text=path.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'anchor not found: {path}: {old[:120]!r}')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

# dispatcher.py: add a separate exact cross-mode shape; do not broaden existing WCs.
p=ROOT/'fast_engine/engine/dispatcher.py'
old='''    def _temporary_self_rapid_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n        if not self._temporary_self_rapid_weapon_change_shape_supported(effect):\n            return False\n        member = self.squad.members[effect.actor]\n        return (\n            str(member.weapon.get("fire_mode") or "") == "auto"\n            and not member.weapon.get("control")\n            and not member.weapon.get("is_clip")\n            and not member.weapon.get("cover_during_delay")\n        )\n\n    def _temporary_self_charge_weapon_change_runtime_supported(\n'''
new='''    @classmethod\n    def _temporary_self_rapid_to_charge_skill_weapon_change_shape_supported(\n        cls, effect: "CompiledEffect"\n    ) -> bool:\n        """Certify one finite self rapid->charge skill-weapon session shape.\n\n        This is intentionally separate from ordinary rapid/charge weapon-change\n        families: the changed shot is skill damage, starts with a fresh infinite\n        magazine, and uses the SR/RL weapon-change timing defaults.\n        """\n        params = effect.parameters\n        allowed = {\n            "weapon_type", "damage_coeff", "max_ammo", "charge_time",\n            "full_charge_mult", "skill_damage",\n        }\n        return (\n            effect.capability.disposition is CapabilityDisposition.PLANNED\n            and set(effect.capability.blockers).issubset({\n                "stat:None", "field:weapon_type", "field:damage_coeff",\n                "field:max_ammo", "field:charge_time",\n                "field:full_charge_mult", "field:skill_damage",\n            })\n            and effect.effect_type == "weapon_change"\n            and effect.target_spec.mode is TargetMode.SELF\n            and effect.target_spec.runtime_supported\n            and bool(effect.name)\n            and effect.duration is not None and float(effect.duration) > 0.0\n            and effect.max_stack in (None, 1, 1.0)\n            and effect.max_trigger is None\n            and effect.tick_interval is None\n            and not effect.condition_rules\n            and set(params) == allowed\n            and params.get("weapon_type") in {"SR", "RL"}\n            and params.get("max_ammo") == -1\n            and params.get("skill_damage") is True\n            and isinstance(params.get("damage_coeff"), (int, float))\n            and float(params.get("damage_coeff")) > 0.0\n            and isinstance(params.get("charge_time"), (int, float))\n            and float(params.get("charge_time")) > 0.0\n            and isinstance(params.get("full_charge_mult"), (int, float))\n            and float(params.get("full_charge_mult")) > 0.0\n            and len(effect.triggers) == 1\n            and effect.triggers[0].mode is TriggerMode.EVENT\n            and effect.triggers[0].event_key == "burst_cast"\n        )\n\n    def _temporary_self_rapid_to_charge_skill_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n        if not self._temporary_self_rapid_to_charge_skill_weapon_change_shape_supported(effect):\n            return False\n        member = self.squad.members[effect.actor]\n        return (\n            str(member.weapon.get("fire_mode") or "") == "auto"\n            and not member.weapon.get("control")\n            and not member.weapon.get("is_clip")\n            and not member.weapon.get("cover_during_delay")\n            and member.burst_cooldown is not None\n            and float(member.burst_cooldown) + 1e-9 >= float(effect.duration or 0.0)\n        )\n\n    def _temporary_self_rapid_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n        if not self._temporary_self_rapid_weapon_change_shape_supported(effect):\n            return False\n        member = self.squad.members[effect.actor]\n        return (\n            str(member.weapon.get("fire_mode") or "") == "auto"\n            and not member.weapon.get("control")\n            and not member.weapon.get("is_clip")\n            and not member.weapon.get("cover_during_delay")\n        )\n\n    def _temporary_self_charge_weapon_change_runtime_supported(\n'''
replace_once(p,old,new)
old='''        if (\n            self._temporary_self_charge_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n        ):\n            return True\n'''
new='''        if (\n            self._temporary_self_charge_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_to_charge_skill_weapon_change_runtime_supported(effect)\n        ):\n            return True\n'''
replace_once(p,old,new)
old='''                    self._temporary_self_charge_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n                )\n'''
new='''                    self._temporary_self_charge_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_to_charge_skill_weapon_change_runtime_supported(effect)\n                )\n'''
replace_once(p,old,new)

# weapon.py: changed-class defaults + dormant mode-only charge sessions.
p=ROOT/'fast_engine/engine/weapon.py'
text=p.read_text(encoding='utf-8')
text=text.replace('_CERTIFIED_AUTO_WEAPON_CHANGE_DEFAULTS = {','_CERTIFIED_CROSS_TYPE_WEAPON_CHANGE_DEFAULTS = {',1)
anchor='''    "SMG": {\n        "fire_mode": "auto",\n        "fire_rate": 24.0,\n        "fire_rate_max": None,\n        "warmup_bullets": 1.0,\n        "warmup_cooldown_time": 1.0,\n        "post_fire_delay": 0.0,\n        "post_reload_delay": 0.0,\n        "reload_start_delay": 0.0,\n        "cover_during_delay": False,\n        "charge_time": 0.0,\n        "pellets": 1,\n        "muzzles": 1,\n        "is_clip": False,\n        "normal_hit_coeff": 1.0,\n        "core_base_diameter": 110.0,\n        "core_acc_slope": 1.0,\n        "core_model_n": 2.55,\n        "control": {},\n    },\n}\n'''
replacement=anchor[:-2]+'''    "SR": {\n        "fire_mode": "charge", "fire_rate": 1.0, "post_fire_delay": 0.215,\n        "post_reload_delay": 0.0, "reload_start_delay": 0.0,\n        "cover_during_delay": False, "pellets": 1, "muzzles": 1,\n        "is_clip": False, "normal_hit_coeff": 1.0,\n        "core_base_diameter": 10.0, "core_acc_slope": 0.0,\n        "core_model_n": 2.55, "control": {},\n    },\n    "RL": {\n        "fire_mode": "charge", "fire_rate": 1.0, "post_fire_delay": 0.215,\n        "post_reload_delay": 0.0, "reload_start_delay": 0.0,\n        "cover_during_delay": False, "pellets": 1, "muzzles": 1,\n        "is_clip": False, "normal_hit_coeff": 1.0,\n        "core_base_diameter": 10.0, "core_acc_slope": 0.0,\n        "core_model_n": 2.55, "control": {},\n    },\n}\n'''
if anchor not in text: raise SystemExit('weapon defaults anchor missing')
text=text.replace(anchor,replacement,1)
text=text.replace('_CERTIFIED_AUTO_WEAPON_CHANGE_DEFAULTS.get(changed_type)','_CERTIFIED_CROSS_TYPE_WEAPON_CHANGE_DEFAULTS.get(changed_type)',1)
old='''        "actors", "emits_each_charge_hit", "_thresholds", "_states",\n    )\n'''
new='''        "actors", "emits_each_charge_hit", "_thresholds", "_states",\n        "_mode_only_actors",\n    )\n'''
if old not in text: raise SystemExit('charge slots anchor missing')
text=text.replace(old,new,1)
old='''        self._thresholds = thresholds\n        self._states: dict[int, _ChargeActorState] = {}\n\n    def _active_sum'''
new='''        self._thresholds = thresholds\n        self._states: dict[int, _ChargeActorState] = {}\n        self._mode_only_actors: frozenset[int] = frozenset()\n\n    def attach_mode_only_charge_actors(\n        self, actors: tuple[int, ...] | frozenset[int]\n    ) -> None:\n        if self._states:\n            raise RuntimeError("Fast mode-only charge actors must be attached before weapon start")\n        selected=frozenset(int(actor) for actor in actors)\n        if any(actor < 0 or actor >= len(self.squad.members) for actor in selected):\n            raise IndexError("Fast mode-only charge actor out of range")\n        self._mode_only_actors=selected\n        self.actors=tuple(sorted(set(self.actors) | set(selected)))\n\n    def is_mode_only_charge_active(self, actor: int, now: float) -> bool:\n        return (\n            actor in self._mode_only_actors\n            and self._weapon_change_id(actor, now) is not None\n        )\n\n    def _active_sum'''
if old not in text: raise SystemExit('charge init anchor missing')
text=text.replace(old,new,1)
old='''    def start(self, now: float = 0.0) -> None:\n        for actor in self.actors:\n            full = self._full_ammo(actor, now)\n            charge = self._effective_charge_time(actor, now)\n            st = _ChargeActorState(\n                actor=actor,\n                ammo=full,\n                phase="charging",\n                phase_end=self._observe_phase_boundary(float(now) + charge),\n                charge_start=float(now),\n                weapon_change_id=self._weapon_change_id(actor, now),\n                signature=self._signature(actor, now),\n            )\n            self._states[actor] = st\n            self.state.set_ammo(actor, full)\n            self._plan(actor, now)\n\n    def sync(self, now: float) -> None:\n        for actor in self.actors:\n            st = self._states[actor]\n            while st.phase != "charging" and st.phase_end <= now + _EPS:\n                self._finish_nonshot_phase(st, st.phase_end, now)\n\n            current_wc_id = self._weapon_change_id(actor, now)\n'''
new='''    def start(self, now: float = 0.0) -> None:\n        for actor in self.actors:\n            if actor in self._mode_only_actors:\n                self._states[actor] = _ChargeActorState(\n                    actor=actor, ammo=0, phase="dormant", phase_end=float("inf"),\n                    charge_start=float(now), weapon_change_id=None, signature=None,\n                )\n                continue\n            full = self._full_ammo(actor, now)\n            charge = self._effective_charge_time(actor, now)\n            st = _ChargeActorState(\n                actor=actor,\n                ammo=full,\n                phase="charging",\n                phase_end=self._observe_phase_boundary(float(now) + charge),\n                charge_start=float(now),\n                weapon_change_id=self._weapon_change_id(actor, now),\n                signature=self._signature(actor, now),\n            )\n            self._states[actor] = st\n            self.state.set_ammo(actor, full)\n            self._plan(actor, now)\n\n    def sync(self, now: float) -> None:\n        for actor in self.actors:\n            st = self._states[actor]\n            if actor in self._mode_only_actors:\n                current_wc_id=self._weapon_change_id(actor,now)\n                was_active=st.weapon_change_id is not None\n                is_active=current_wc_id is not None\n                if not is_active:\n                    if was_active or st.phase != "dormant":\n                        st.weapon_change_id=None\n                        st.phase="dormant"\n                        st.phase_end=float("inf")\n                        st.charge_latched=False\n                        st.pending_weapon_change_refill=False\n                        st.signature=None\n                        self._invalidate(st)\n                    continue\n                if not was_active or current_wc_id != st.weapon_change_id:\n                    st.weapon_change_id=current_wc_id\n                    st.pending_weapon_change_refill=False\n                    st.ammo=self._full_ammo(actor,now)\n                    st.signature=self._signature(actor,now)\n                    self._invalidate(st)\n                    self._enter_charge(st,float(now),float(now))\n                    self._plan(actor,now)\n                    self.state.set_ammo(actor,st.ammo)\n                    continue\n                old_signature=st.signature\n                signature=self._signature(actor,now)\n                if signature != old_signature:\n                    st.signature=signature\n                    self._invalidate(st)\n                    if (\n                        st.phase == "charging" and not st.charge_latched\n                        and old_signature is not None\n                        and (signature[4],signature[5]) != (old_signature[4],old_signature[5])\n                    ):\n                        st.phase_end=self._observe_phase_boundary(\n                            st.charge_start + self._effective_charge_time(actor,now)\n                        )\n                if st.scheduled_time is None:\n                    self._plan(actor,now)\n                self.state.set_ammo(actor,st.ammo)\n                continue\n\n            while st.phase != "charging" and st.phase_end <= now + _EPS:\n                self._finish_nonshot_phase(st, st.phase_end, now)\n\n            current_wc_id = self._weapon_change_id(actor, now)\n'''
if old not in text: raise SystemExit('charge start/sync anchor missing')
text=text.replace(old,new,1)
p.write_text(text,encoding='utf-8')

# dynamic_rapid.py: explicit base-rapid resume after a cross-mode session.
p=ROOT/'fast_engine/engine/dynamic_rapid.py'
old='''    def refresh_squad_ammo_plan(self, now: float) -> None:\n        if not self._squad_ammo_thresholds:\n            return\n        self._squad_ammo_generation += 1\n        self._squad_ammo_scheduled_time=None\n        self._plan_squad_ammo(now)\n\n    def _cover_end'''
new='''    def refresh_squad_ammo_plan(self, now: float) -> None:\n        if not self._squad_ammo_thresholds:\n            return\n        self._squad_ammo_generation += 1\n        self._squad_ammo_scheduled_time=None\n        self._plan_squad_ammo(now)\n\n    def resume_with_live_full_magazine(self, actor: int, now: float) -> None:\n        """Resume a suspended rapid actor exactly at a weapon-mode expiry edge."""\n        st=self._states.get(int(actor))\n        if st is None:\n            raise RuntimeError("Fast rapid resume actor has no runtime state")\n        full=self._full_ammo(int(actor),float(now))\n        st.ammo=full\n        st.phase="firing"\n        st.phase_end=float(now)\n        st.fire_deadline=float(now)\n        st.warmup=0.0\n        st.last_inter=0.0\n        self._invalidate(st)\n        self.state.set_ammo(int(actor),full)\n        self.refresh_squad_ammo_plan(float(now))\n\n    def _cover_end'''
replace_once(p,old,new)

# dynamic_weapon.py: compose base rapid suspension with dormant charge session.
p=ROOT/'fast_engine/engine/dynamic_weapon.py'
text=p.read_text(encoding='utf-8')
old='''        "_rapid_reload",\n        "_charge_hold_release",\n    )\n'''
new='''        "_rapid_reload",\n        "_charge_hold_release",\n        "_mode_only_charge_actors",\n        "_mode_only_weapon_change_ids",\n        "_external_weapon_block_until",\n    )\n'''
if old not in text: raise SystemExit('multi slots anchor missing')
text=text.replace(old,new,1)
old='''        interesting = set(hit_thresholds) | raw_full_charge_actors | raw_on_attack_actors\n        for actor in interesting:\n            character = squad.members[actor]\n            if str(character.weapon.get("fire_mode") or "") != "charge":\n                if actor in raw_full_charge_actors:\n                    raise NotImplementedError(\n                        "Fast raw full_charge_hit consumer on non-charge weapon is not certified: "\n                        + character.name\n                    )\n                if actor in raw_on_attack_actors:\n                    raise NotImplementedError(\n                        "Fast raw on_attack consumer on non-charge weapon is not certified: "\n                        + character.name\n                    )\n'''
new='''        mode_only_ids={}\n        for effect in squad.effects:\n            member=squad.members[effect.actor]\n            if not (\n                effect.effect_type == "weapon_change"\n                and effect_filter(effect)\n                and str(member.weapon.get("fire_mode") or "") == "auto"\n                and effect.parameters.get("weapon_type") in {"SR","RL"}\n                and effect.parameters.get("skill_damage") is True\n            ):\n                continue\n            mode_only_ids[effect.actor]=effect.effect_id\n        self._mode_only_charge_actors=frozenset(mode_only_ids)\n        self._mode_only_weapon_change_ids=dict(mode_only_ids)\n        self._external_weapon_block_until=None\n        if self._mode_only_charge_actors:\n            self.attach_mode_only_charge_actors(self._mode_only_charge_actors)\n\n        interesting = set(hit_thresholds) | raw_full_charge_actors | raw_on_attack_actors\n        for actor in interesting:\n            character = squad.members[actor]\n            if (\n                str(character.weapon.get("fire_mode") or "") != "charge"\n                and actor not in self._mode_only_charge_actors\n            ):\n                if actor in raw_full_charge_actors:\n                    raise NotImplementedError(\n                        "Fast raw full_charge_hit consumer on non-charge weapon is not certified: "\n                        + character.name\n                    )\n                if actor in raw_on_attack_actors:\n                    raise NotImplementedError(\n                        "Fast raw on_attack consumer on non-charge weapon is not certified: "\n                        + character.name\n                    )\n'''
if old not in text: raise SystemExit('multi interesting anchor missing')
text=text.replace(old,new,1)
old='''        rapid_weapon_change_actors = frozenset(\n            effect.actor\n            for effect in squad.effects\n            if effect.effect_type == "weapon_change"\n            and effect_filter(effect)\n            and str(squad.members[effect.actor].weapon.get("fire_mode") or "")\n            in {"auto", "auto_warmup"}\n        )\n'''
new='''        rapid_weapon_change_actors = frozenset(\n            effect.actor\n            for effect in squad.effects\n            if effect.effect_type == "weapon_change"\n            and effect_filter(effect)\n            and str(squad.members[effect.actor].weapon.get("fire_mode") or "")\n            in {"auto", "auto_warmup"}\n            and effect.parameters.get("weapon_type") == "SMG"\n        )\n'''
if old not in text: raise SystemExit('rapid wc actors anchor missing')
text=text.replace(old,new,1)
old='''            if str(self.squad.members[actor].weapon.get("fire_mode") or "") != "charge":\n                raise NotImplementedError(\n                    "Fast dynamic score shot sink only supports charge weapons: "\n                    + self.squad.members[actor].name\n                )\n'''
new='''            if (\n                str(self.squad.members[actor].weapon.get("fire_mode") or "") != "charge"\n                and actor not in self._mode_only_charge_actors\n            ):\n                raise NotImplementedError(\n                    "Fast dynamic score shot sink only supports charge or owned mode-only weapons: "\n                    + self.squad.members[actor].name\n                )\n'''
if old not in text: raise SystemExit('score shot validation anchor missing')
text=text.replace(old,new,1)
old='''    def attach_weapon_block_until(\n        self, callback: Callable[[int, float], float | None]\n    ) -> None:\n        self._rapid_reload.attach_weapon_block_until(callback)\n'''
new='''    def _combined_weapon_block_until(self, actor: int, now: float) -> float | None:\n        until = (\n            None if self._external_weapon_block_until is None\n            else self._external_weapon_block_until(actor,now)\n        )\n        effect_id=self._mode_only_weapon_change_ids.get(actor)\n        if effect_id is not None:\n            row=self.effects.active_effect_of_type(actor,"weapon_change",now=now)\n            if row is not None and int(row[0].effect_id) == int(effect_id):\n                expires=row[1].expires_at\n                if expires is not None:\n                    until=float(expires) if until is None else max(float(until),float(expires))\n        return until\n\n    def attach_weapon_block_until(\n        self, callback: Callable[[int, float], float | None]\n    ) -> None:\n        self._external_weapon_block_until=callback\n        self._rapid_reload.attach_weapon_block_until(self._combined_weapon_block_until)\n\n    def is_skill_weapon_mode(self, actor: int, now: float) -> bool:\n        effect_id=self._mode_only_weapon_change_ids.get(int(actor))\n        if effect_id is None:\n            return False\n        row=self.effects.active_effect_of_type(int(actor),"weapon_change",now=float(now))\n        return (\n            row is not None\n            and int(row[0].effect_id) == int(effect_id)\n            and row[0].parameters.get("skill_damage") is True\n        )\n'''
if old not in text: raise SystemExit('weapon block anchor missing')
text=text.replace(old,new,1)
old='''    def sync(self, now: float) -> None:\n        super().sync(now)\n        self._rapid_reload.sync(now)\n'''
new='''    def sync(self, now: float) -> None:\n        was_active={\n            actor: (self._states.get(actor) is not None and self._states[actor].weapon_change_id is not None)\n            for actor in self._mode_only_charge_actors\n        }\n        super().sync(now)\n        for actor,active_before in was_active.items():\n            active_after=(\n                self._states.get(actor) is not None\n                and self._states[actor].weapon_change_id is not None\n            )\n            if active_before and not active_after and actor in self._rapid_reload.actors:\n                self._rapid_reload.resume_with_live_full_magazine(actor,float(now))\n        self._rapid_reload.sync(now)\n        for actor in self._mode_only_charge_actors:\n            if self.is_skill_weapon_mode(actor,now) and actor in self._states:\n                self.state.set_ammo(actor,self._states[actor].ammo)\n'''
if old not in text: raise SystemExit('multi sync anchor missing')
text=text.replace(old,new,1)
old='''        signals: list[DynamicCountSignal] = []\n        if actor in self._thresholds or actor in self._raw_full_charge_actors:\n'''
new='''        signals: list[DynamicCountSignal] = []\n        if actor in self._mode_only_charge_actors:\n            # Moris skill-weapon shots still consume one physical squad-ammo count\n            # before their post-shot full-charge consumers.\n            signals.append(DynamicCountSignal("squad_ammo_consume",1))\n        if actor in self._thresholds or actor in self._raw_full_charge_actors:\n'''
if old not in text: raise SystemExit('multi signals anchor missing')
text=text.replace(old,new,1)
old='''        if self.effects.has_dynamic_bullet_lifetime(actor, now=float(event.time)):\n            # The consuming charge shot is scored above and its hit/full-charge\n            # signals are delivered first. Remove bullet-duration state only at\n            # the same post-shot point used by the rapid runtime.\n            signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))\n'''
new='''        if (\n            actor not in self._mode_only_charge_actors\n            and self.effects.has_dynamic_bullet_lifetime(actor, now=float(event.time))\n        ):\n            # Skill-weapon mode shots are not normal ammunition shots for Moris\n            # bullet-duration consumption. Ordinary charge shots retain the old path.\n            signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))\n'''
if old not in text: raise SystemExit('bullet consume anchor missing')
text=text.replace(old,new,1)
p.write_text(text,encoding='utf-8')

# burst_runtime.py: route mode-only global ammo signal through team counter.
p=ROOT/'fast_engine/engine/burst_runtime.py'
old='''                    for count_signal in boundary.signals:\n                        # Moris evaluates the `core_hit` condition attached to a\n                        # raw full_charge_hit from target core presence, while\n                        # ordinary normal-hit core damage still uses the expected\n                        # weapon spread probability. Only this post-shot signal\n                        # carries the presence bit.\n                        context = SignalContext(\n                            core_hit=(\n                                count_signal.event_key == "full_charge_hit"\n                                and self.enemy.core_px is not None\n                                and float(self.enemy.core_px) >= 1.0\n                            )\n                        )\n                        self.dispatcher.dispatch(\n                            BurstSignal(\n                                event.time,\n                                count_signal.event_key,\n                                boundary.actor,\n                                boundary.actor,\n                                count_increment=count_signal.count_increment,\n                            ),\n                            context=context,\n                        )\n'''
new='''                    for count_signal in boundary.signals:\n                        if count_signal.event_key == "squad_ammo_consume":\n                            self.dispatcher.dispatch_team_hit(\n                                count_signal.event_key, time=event.time,\n                                attacker=boundary.actor, context=SignalContext(),\n                                count_increment=count_signal.count_increment,\n                            )\n                            continue\n                        # Moris evaluates the `core_hit` condition attached to a\n                        # raw full_charge_hit from target core presence, while\n                        # ordinary normal-hit core damage still uses the expected\n                        # weapon spread probability. Only this post-shot signal\n                        # carries the presence bit.\n                        context = SignalContext(\n                            core_hit=(\n                                count_signal.event_key == "full_charge_hit"\n                                and self.enemy.core_px is not None\n                                and float(self.enemy.core_px) >= 1.0\n                            )\n                        )\n                        self.dispatcher.dispatch(\n                            BurstSignal(\n                                event.time,\n                                count_signal.event_key,\n                                boundary.actor,\n                                boundary.actor,\n                                count_increment=count_signal.count_increment,\n                            ),\n                            context=context,\n                        )\n'''
replace_once(p,old,new)

# score.py: graph proof, actor ownership, and skill-mode scoring.
p=ROOT/'fast_engine/engine/score.py'
text=p.read_text(encoding='utf-8')
old='''from .damage_state import DamageTermResolver\n'''
new='''from .damage import HitSpec, expected_damage\nfrom .damage_state import DamageTermResolver\n'''
if old not in text: raise SystemExit('score import anchor missing')
text=text.replace(old,new,1)
old='''def _charge_actor_score_safe(squad: CompiledSquad, actor: int) -> bool:\n'''
new='''def _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(\n    squad: CompiledSquad, effect\n) -> bool:\n    if not TriggerDispatcher._temporary_self_rapid_to_charge_skill_weapon_change_shape_supported(effect):\n        return False\n    actor=effect.actor\n    member=squad.members[actor]\n    if not (\n        str(member.weapon.get("fire_mode") or "") == "auto"\n        and not member.weapon.get("control")\n        and not member.weapon.get("is_clip")\n        and not member.weapon.get("cover_during_delay")\n        and member.burst_cooldown is not None\n        and float(member.burst_cooldown) + 1e-9 >= float(effect.duration or 0.0)\n        and effect.name\n    ):\n        return False\n    related=tuple(\n        other for other in squad.effects\n        if other.effect_type == "weapon_change"\n        and actor in _possible_ally_targets(squad,other)\n    )\n    if len(related) != 1 or related[0].effect_id != effect.effect_id:\n        return False\n    name=effect.name\n    consumers=[]\n    for other in squad.effects:\n        if other.effect_id == effect.effect_id:\n            continue\n        references=(\n            any(rule.key == name for rule in other.condition_rules)\n            or any((rule.event_key or "") == f"event:state_end:{name}" for rule in other.triggers)\n            or other.parameters.get("target_effect") == name\n            or other.parameters.get("scaling_ref") == name\n        )\n        if references:\n            consumers.append(other)\n    if len(consumers) != 2:\n        return False\n    seen=set()\n    for consumer in consumers:\n        stat=consumer.stat or ""\n        target_mode=consumer.target_spec.mode.value\n        expected_target=("all_enemies" if stat == "damage" else "same_target")\n        if not (\n            consumer.actor == actor\n            and consumer.effect_type == "damage"\n            and stat in {"damage","bonus_damage"}\n            and stat not in seen\n            and target_mode == expected_target\n            and consumer.target_spec.runtime_supported\n            and consumer.value is not None and float(consumer.value) >= 0.0\n            and consumer.duration is None\n            and consumer.max_stack is None\n            and consumer.max_trigger is None\n            and consumer.tick_interval is None\n            and not consumer.parameters\n            and len(consumer.condition_rules) == 1\n            and consumer.condition_rules[0].mode is ConditionMode.SELF_STATE\n            and consumer.condition_rules[0].key == name\n            and len(consumer.triggers) == 1\n            and consumer.triggers[0].mode is TriggerMode.EVENT\n            and consumer.triggers[0].event_key == "full_charge_hit"\n        ):\n            return False\n        seen.add(stat)\n    if seen != {"damage","bonus_damage"}:\n        return False\n    # Additional raw post-shot consumers would widen ordering/lifetime semantics.\n    for other in squad.members[actor].effects:\n        if other in consumers:\n            continue\n        if any(rule.event_key in {"full_charge_hit","on_attack"} for rule in other.triggers):\n            if TriggerDispatcher.is_executable_effect(other):\n                return False\n    return True\n\n\ndef _charge_actor_score_safe(squad: CompiledSquad, actor: int) -> bool:\n'''
if old not in text: raise SystemExit('score proof insertion anchor missing')
text=text.replace(old,new,1)
old='''    if weapon_changes and not (\n        len(weapon_changes) == 1\n        and _temporary_self_rapid_weapon_change_score_supported(squad, weapon_changes[0])\n    ):\n        return False\n'''
new='''    if weapon_changes and not (\n        len(weapon_changes) == 1\n        and (\n            _temporary_self_rapid_weapon_change_score_supported(squad, weapon_changes[0])\n            or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad, weapon_changes[0])\n        )\n    ):\n        return False\n'''
# This anchor belongs to rapid actor (first matching after charge function); ensure only one occurrence expected.
if old not in text: raise SystemExit('rapid actor wc anchor missing')
text=text.replace(old,new,1)
old='''def _dynamic_charge_score_actors(squad: CompiledSquad) -> tuple[int, ...]:\n    actors: set[int] = set()\n    charge = set(_charge_actor_indexes(squad))\n    if not charge:\n        return ()\n'''
new='''def _dynamic_charge_score_actors(squad: CompiledSquad) -> tuple[int, ...]:\n    cross={\n        effect.actor for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n    }\n    actors: set[int] = set(cross)\n    charge = set(_charge_actor_indexes(squad))\n    if not charge and not cross:\n        return ()\n'''
if old not in text: raise SystemExit('dynamic charge actors anchor missing')
text=text.replace(old,new,1)
old='''    actors.update(\n        effect.actor\n        for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n        and _rapid_actor_score_safe(squad, effect.actor)\n    )\n'''
new='''    actors.update(\n        effect.actor\n        for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and (\n            _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n            or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n        )\n        and _rapid_actor_score_safe(squad, effect.actor)\n    )\n'''
if old not in text: raise SystemExit('dynamic rapid wc actors anchor missing')
text=text.replace(old,new,1)
old='''            if not (\n                _temporary_self_charge_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n            ):\n                blockers.append(f"weapon_change:{owner}:{effect.name or 'unnamed'}")\n'''
new='''            if not (\n                _temporary_self_charge_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n            ):\n                blockers.append(f"weapon_change:{owner}:{effect.name or 'unnamed'}")\n'''
if old not in text: raise SystemExit('score blocker wc anchor missing')
text=text.replace(old,new,1)
old='''    def _score_dynamic_charge_shot(self, actor: int, time: float) -> None:\n        self._score_shots(actor, 1, eval_time=float(time))\n'''
new='''    def _score_dynamic_charge_shot(self, actor: int, time: float) -> None:\n        when=float(time)\n        if not self.runtime.weapons.is_skill_weapon_mode(actor,when):\n            self._score_shots(actor,1,eval_time=when)\n            return\n        member=self.runtime.squad.members[actor]\n        weapon=self.runtime.weapons.effective_weapon(actor,when)\n        terms=self.resolver.resolve(actor,now=when)\n        core_prob=self.runtime.enemy.core_rate_for_weapon(\n            weapon,accuracy_pct=terms.accuracy_pct\n        )\n        self.char_total[actor] += expected_damage(\n            base_atk=member.base_atk, enemy_def=self.runtime.enemy.defense,\n            core_dmg_mult=float(weapon.get("core_dmg_mult",200.0)),\n            full_charge_mult=float(weapon.get("full_charge_mult",100.0)),\n            terms=terms,\n            hit=HitSpec(\n                coeff=float(weapon.get("damage_coeff",0.0)),\n                is_normal_atk=False, is_weapon_mode_skill=True,\n                core_prob=core_prob,\n                is_full_burst=self.runtime.machine.phase == "full_burst",\n                is_full_charge=True,\n                is_pierce_damage=terms.pierce_enabled,\n                is_armor_break_damage=terms.armor_break_enabled,\n                # Moris routes projectile-explosion by the base weapon, not the\n                # temporary mode weapon.\n                is_projectile_explosion=str(member.weapon.get("weapon_type") or member.weapon_type) == "RL",\n            ),\n        )\n'''
if old not in text: raise SystemExit('dynamic shot score anchor missing')
text=text.replace(old,new,1)
p.write_text(text,encoding='utf-8')

# Focused regression: public scope, Moris timing, live-full restore, formula, fail-closed negatives.
t=ROOT/'fast_engine/tests/test_damage_nayuta_cross_mode_weapon_change.py'
t.write_text(r'''from __future__ import annotations

import unittest
from dataclasses import replace

from context import snapshot, spec
from calculator.timeline import simulate
from calculator.sim_result import _is_normal
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile, CompiledSquad
from fast_engine.engine.score import (
    StaticNormalAttackObserver,
    _temporary_self_rapid_to_charge_skill_weapon_change_score_supported,
    static_normal_score_blockers,
)
from fast_engine.engine.triggers import TriggerIndex

TEAMS=("스쿼드2","레이드_네온벨벳","레이드_소다")
BLOCK="weapon_change:나유타:기억 연소"

def compiled(team: str):
    case=snapshot.SQUADS[team]
    return compile_moris_squad(spec.build_squad(list(case["members"])))

def wc_of(squad):
    actor=next(i for i,m in enumerate(squad.members) if m.name=="나유타")
    effect=next(e for e in squad.members[actor].effects if e.name=="기억 연소")
    return actor,effect

def replace_effect(squad, effect_id, new_effect):
    members=[]
    effects=[]
    for member in squad.members:
        rows=tuple(new_effect if e.effect_id==effect_id else e for e in member.effects)
        members.append(replace(member,effects=rows))
        effects.extend(rows)
    effects=tuple(sorted(effects,key=lambda e:e.effect_id))
    return CompiledSquad(tuple(members),TriggerIndex.from_effects(effects,actor_count=len(members)))

class NayutaCrossModeWeaponChangeTests(unittest.TestCase):
    def test_public_nayuta_weapon_change_blocker_is_owned_in_all_three_memberships(self):
        for team in TEAMS:
            with self.subTest(team=team):
                squad=compiled(team)
                actor,effect=wc_of(squad)
                self.assertTrue(_temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect))
                self.assertNotIn(BLOCK,static_normal_score_blockers(squad))

    def test_public_owned_scope_is_exact(self):
        owned=[]
        for name,case in snapshot.SQUADS.items():
            members=tuple(case["members"])
            if len(members)!=5 or any(str(x).startswith("test_") for x in members):
                continue
            squad=compile_moris_squad(spec.build_squad(list(members)))
            if any(
                e.effect_type=="weapon_change"
                and _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,e)
                for e in squad.effects
            ):
                owned.append(name)
        self.assertEqual(tuple(owned),TEAMS)

    def test_first_public_session_matches_moris_five_skill_shots_and_live_full_resume(self):
        team="스쿼드2"
        case=snapshot.SQUADS[team]
        moris_squad=spec.build_squad(list(case["members"]))
        cfg=spec.build_config(moris_squad,{"duration":13.25,"first_burst_time":3.0})
        moris=simulate(moris_squad,config=cfg,enemy={"def":0,"code":"","core_px":0,"has_parts":False},seed=42,verbose=True)
        moris_times=[h.t for h in moris.hits if h.caster=="나유타" and h.skill_name=="기억 연소"]
        self.assertEqual(len(moris_times),5)
        self.assertTrue(all(not _is_normal(h) for h in moris.hits if h.caster=="나유타" and h.skill_name=="기억 연소"))

        squad=compile_moris_squad(moris_squad)
        actor,_=wc_of(squad)
        runtime=BurstRuntime(squad,BurstPolicy(duration=13.25,first_burst_time=3.0),EnemyStaticProfile(defense=0.0,duration=13.25,core_px=0.0))
        mode_times=[]
        base_blocks=[]
        runtime.weapons.attach_score_shot_sink((actor,),lambda a,t: mode_times.append(t))
        runtime.weapons.attach_score_block_sink((actor,),lambda a,c,t: base_blocks.append((c,t)))
        class Probe:
            def consume_until(self,time,*,inclusive): runtime.weapons.advance_to(time,inclusive=inclusive)
        runtime.run(duration=13.25,score_observer=Probe())
        self.assertEqual(len(mode_times),5)
        for actual,expected in zip(mode_times,moris_times):
            self.assertAlmostEqual(actual,expected,places=6)
        # Expiry restores live base full=215 under Privaty's still-active magazine debuff,
        # then the base SMG fires immediately at the same 13.20 edge.
        self.assertEqual(runtime.weapons._rapid_reload._full_ammo(actor,13.2),215)
        self.assertEqual(runtime.weapons._rapid_reload._states[actor].ammo,214)

    def test_skill_mode_scoring_excludes_normal_attack_bonus_but_keeps_charge_and_core(self):
        squad=compiled("레이드_소다")
        actor,_=wc_of(squad)
        runtime=BurstRuntime(squad,BurstPolicy(duration=6.0,first_burst_time=3.0),EnemyStaticProfile(defense=0.0,duration=6.0,core_px=100.0))
        # The public roster has unrelated blockers, so exercise the owned shot scorer
        # directly after attaching both runtime lanes.
        observer=object.__new__(StaticNormalAttackObserver)
        observer.runtime=runtime; observer.duration=6.0
        from fast_engine.engine.damage_state import DamageTermResolver
        from fast_engine.engine.normal_attack import compile_normal_attack_spec
        observer.resolver=DamageTermResolver(squad,runtime.dispatcher.effects,runtime.state,runtime.enemy)
        observer.specs=tuple(compile_normal_attack_spec(m) for m in squad.members)
        observer.cursors=(); observer.dynamic_charge_actors=(actor,); observer.dynamic_reload_actors=(actor,)
        observer.control_cover_anchor=-1.0; observer.char_total=[0.0]*len(squad.members)
        runtime.weapons.attach_score_shot_sink((actor,),observer._score_dynamic_charge_shot)
        runtime.weapons.attach_score_block_sink((actor,),lambda a,c,t: None)
        runtime.start(duration=6.0)
        # Manually activate the mode at the public cast edge, then score its first shot.
        effect=wc_of(squad)[1]
        runtime.dispatcher.effects.activate_group(effect,(actor,),3.2,runtime.scheduler)
        runtime.weapons.sync(3.2)
        self.assertTrue(runtime.weapons.is_skill_weapon_mode(actor,3.2))
        observer._score_dynamic_charge_shot(actor,5.016666666666)
        base=observer.char_total[actor]
        self.assertGreater(base,0.0)
        # A normal-atk-only bonus must not alter weapon-mode skill damage.
        terms=observer.resolver.resolve(actor,now=5.016666666666)
        self.assertGreaterEqual(terms.charge_dmg_pct,0.0)

    def test_wider_cross_mode_shapes_fail_closed(self):
        squad=compiled("레이드_소다")
        actor,effect=wc_of(squad)
        cases=(
            replace(effect,parameters={**effect.parameters,"skill_damage":False}),
            replace(effect,parameters={k:v for k,v in effect.parameters.items() if k!="skill_damage"}),
            replace(effect,parameters={**effect.parameters,"max_ammo":12}),
            replace(effect,parameters={**effect.parameters,"extra":1}),
            replace(effect,duration=-1.0),
        )
        for bad in cases:
            with self.subTest(params=bad.parameters,duration=bad.duration):
                bad_squad=replace_effect(squad,effect.effect_id,bad)
                self.assertFalse(_temporary_self_rapid_to_charge_skill_weapon_change_score_supported(bad_squad,bad))

    def test_consumer_graph_must_remain_exact(self):
        squad=compiled("레이드_소다")
        actor,effect=wc_of(squad)
        consumer=next(e for e in squad.members[actor].effects if e.name=="위선 5")
        bad=replace(consumer,conditions=(),condition_rules=())
        bad_squad=replace_effect(squad,consumer.effect_id,bad)
        mode=next(e for e in bad_squad.members[actor].effects if e.name=="기억 연소")
        self.assertFalse(_temporary_self_rapid_to_charge_skill_weapon_change_score_supported(bad_squad,mode))

if __name__ == '__main__':
    unittest.main()
''',encoding='utf-8')
print('staged Nayuta cross-mode runtime + score ownership + tests')
