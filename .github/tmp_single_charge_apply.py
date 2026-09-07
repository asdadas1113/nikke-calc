from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    if old not in s:
        raise SystemExit(f"anchor missing in {path}: {old[:120]!r}")
    s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")


# Dispatcher: exact runtime shape for a self rapid -> one ordinary SR full-charge shot.
p = "fast_engine/engine/dispatcher.py"
anchor = '''    @classmethod\n    def _temporary_self_rapid_to_charge_skill_weapon_change_shape_supported(\n        cls, effect: "CompiledEffect"\n    ) -> bool:\n'''
insert = '''    @classmethod\n    def _temporary_self_rapid_to_single_charge_weapon_change_shape_supported(\n        cls, effect: "CompiledEffect"\n    ) -> bool:\n        """Certify one self rapid -> ordinary SR shot consumed by bullet lifetime.\n\n        The mode has no time duration: Moris enters a one-round SR session on\n        ``burst_cast`` and removes the weapon change only after that full-charge\n        normal attack has been scored and its post-shot signals have fired.\n        """\n        params = effect.parameters\n        required = {\n            "weapon_type", "damage_coeff", "max_ammo", "charge_time",\n            "full_charge_mult", "duration_bullets",\n        }\n        allowed = required | {"favorite"}\n        favorite = params.get("favorite")\n        return (\n            effect.capability.disposition is CapabilityDisposition.PLANNED\n            and set(effect.capability.blockers) == {\n                "stat:None", "field:weapon_type", "field:damage_coeff",\n                "field:max_ammo", "field:charge_time",\n                "field:full_charge_mult", "field:duration_bullets",\n            }\n            and effect.effect_type == "weapon_change"\n            and effect.target_spec.mode is TargetMode.SELF\n            and effect.target_spec.runtime_supported\n            and bool(effect.name)\n            and effect.duration is None\n            and effect.max_stack in (None, 1, 1.0)\n            and effect.max_trigger is None\n            and effect.tick_interval is None\n            and not effect.condition_rules\n            and required.issubset(params)\n            and set(params).issubset(allowed)\n            and (favorite is None or float(favorite) == 1.0)\n            and params.get("weapon_type") == "SR"\n            and params.get("max_ammo") == 1\n            and params.get("duration_bullets") == 1\n            and "skill_damage" not in params\n            and isinstance(params.get("damage_coeff"), (int, float))\n            and float(params.get("damage_coeff")) > 0.0\n            and isinstance(params.get("charge_time"), (int, float))\n            and float(params.get("charge_time")) > 0.0\n            and isinstance(params.get("full_charge_mult"), (int, float))\n            and float(params.get("full_charge_mult")) > 0.0\n            and len(effect.triggers) == 1\n            and effect.triggers[0].mode is TriggerMode.EVENT\n            and effect.triggers[0].event_key == "burst_cast"\n        )\n\n''' + anchor
replace_once(p, anchor, insert)

anchor = '''    def _temporary_self_rapid_to_charge_skill_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n'''
insert = '''    def _temporary_self_rapid_to_single_charge_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n        if not self._temporary_self_rapid_to_single_charge_weapon_change_shape_supported(effect):\n            return False\n        member = self.squad.members[effect.actor]\n        return (\n            str(member.weapon.get("fire_mode") or "") == "auto"\n            and not member.weapon.get("control")\n            and not member.weapon.get("is_clip")\n            and not member.weapon.get("cover_during_delay")\n        )\n\n''' + anchor
replace_once(p, anchor, insert)

replace_once(
    p,
    '''            self._temporary_self_charge_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_to_charge_skill_weapon_change_runtime_supported(effect)\n''',
    '''            self._temporary_self_charge_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_to_single_charge_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_to_charge_skill_weapon_change_runtime_supported(effect)\n''',
)
replace_once(
    p,
    '''                    self._temporary_self_charge_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_to_charge_skill_weapon_change_runtime_supported(effect)\n''',
    '''                    self._temporary_self_charge_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_to_single_charge_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_to_charge_skill_weapon_change_runtime_supported(effect)\n''',
)

# Score proof: own exactly the two public one-shot shapes and their one-shot pierce sibling.
p = "fast_engine/engine/score.py"
anchor = '''def _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(\n    squad: CompiledSquad, effect\n) -> bool:\n'''
insert = '''def _temporary_self_rapid_to_single_charge_weapon_change_score_supported(\n    squad: CompiledSquad, effect\n) -> bool:\n    if not TriggerDispatcher._temporary_self_rapid_to_single_charge_weapon_change_shape_supported(effect):\n        return False\n    actor = effect.actor\n    member = squad.members[actor]\n    if not (\n        str(member.weapon.get("fire_mode") or "") == "auto"\n        and not member.weapon.get("control")\n        and not member.weapon.get("is_clip")\n        and not member.weapon.get("cover_during_delay")\n        and effect.name\n    ):\n        return False\n\n    related = tuple(\n        other for other in squad.effects\n        if other.effect_type == "weapon_change"\n        and actor in _possible_ally_targets(squad, other)\n    )\n    if len(related) != 1 or related[0].effect_id != effect.effect_id:\n        return False\n\n    companions = tuple(\n        other for other in squad.members[actor].effects\n        if other.effect_id != effect.effect_id\n        and other.effect_type == "buff"\n        and (other.stat or "") == "pierce_enabled"\n        and len(other.triggers) == 1\n        and other.triggers[0].mode is TriggerMode.EVENT\n        and other.triggers[0].event_key == "burst_cast"\n    )\n    if len(companions) != 1:\n        return False\n    companion = companions[0]\n    favorite = companion.parameters.get("favorite")\n    if not (\n        companion.capability.disposition is CapabilityDisposition.PLANNED\n        and set(companion.capability.blockers) == {\n            "category:state_trigger", "stat:pierce_enabled",\n            "field:duration_bullets",\n        }\n        and companion.target_spec.mode is TargetMode.SELF\n        and companion.target_spec.runtime_supported\n        and companion.value is None\n        and companion.duration is None\n        and companion.max_stack in (None, 1, 1.0)\n        and companion.max_trigger is None\n        and companion.tick_interval is None\n        and set(companion.parameters).issubset({"favorite", "duration_bullets"})\n        and companion.parameters.get("duration_bullets") == 1\n        and (favorite is None or float(favorite) == 1.0)\n        and not companion.condition_rules\n        and is_direct_damage_buff_runtime_supported(companion)\n    ):\n        return False\n\n    # Do not silently widen named-state ownership around the mode.\n    name = effect.name\n    for other in squad.effects:\n        if other.effect_id == effect.effect_id:\n            continue\n        if (\n            any(rule.key == name for rule in other.condition_rules)\n            or any((rule.event_key or "") == f"event:state_end:{name}" for rule in other.triggers)\n            or other.parameters.get("target_effect") == name\n            or other.parameters.get("scaling_ref") == name\n        ):\n            return False\n\n    # New raw post-shot event families are not part of this checkpoint. Existing\n    # reducible hit_count crossings remain handled by the charge cadence runtime.\n    if any(\n        TriggerDispatcher.is_executable_effect(other)\n        and any(rule.event_key in {"full_charge_hit", "on_attack"} for rule in other.triggers)\n        for other in squad.members[actor].effects\n    ):\n        return False\n    return True\n\n\ndef _rapid_to_single_charge_actor_score_safe(squad: CompiledSquad, actor: int) -> bool:\n    rows = tuple(\n        effect for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and actor in _possible_ally_targets(squad, effect)\n    )\n    return (\n        len(rows) == 1\n        and _temporary_self_rapid_to_single_charge_weapon_change_score_supported(\n            squad, rows[0]\n        )\n    )\n\n\n''' + anchor
replace_once(p, anchor, insert)

replace_once(
    p,
    '''            _temporary_self_rapid_weapon_change_score_supported(squad, weapon_changes[0])\n            or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad, weapon_changes[0])\n''',
    '''            _temporary_self_rapid_weapon_change_score_supported(squad, weapon_changes[0])\n            or _temporary_self_rapid_to_single_charge_weapon_change_score_supported(squad, weapon_changes[0])\n            or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad, weapon_changes[0])\n''',
)
replace_once(
    p,
    '''        static_bullet_lifetime_cadence_safe(squad, actor)\n        or _charge_actor_score_safe(squad, actor)\n        for actor in targets\n''',
    '''        static_bullet_lifetime_cadence_safe(squad, actor)\n        or _charge_actor_score_safe(squad, actor)\n        or _rapid_to_single_charge_actor_score_safe(squad, actor)\n        for actor in targets\n''',
)
replace_once(
    p,
    '''    cross={\n        effect.actor for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n    }\n''',
    '''    cross={\n        effect.actor for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and (\n            _temporary_self_rapid_to_single_charge_weapon_change_score_supported(squad,effect)\n            or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n        )\n    }\n''',
)
replace_once(
    p,
    '''            _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n            or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n''',
    '''            _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n            or _temporary_self_rapid_to_single_charge_weapon_change_score_supported(squad,effect)\n            or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n''',
)
replace_once(
    p,
    '''                _temporary_self_charge_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n''',
    '''                _temporary_self_charge_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_to_single_charge_weapon_change_score_supported(squad,effect)\n                or _temporary_self_rapid_to_charge_skill_weapon_change_score_supported(squad,effect)\n''',
)

# Rapid cadence: after the changed shot Moris resumes the base weapon on the next
# repeated-add frame with exactly one restored round, not pre-entry ammo/full ammo.
p = "fast_engine/engine/dynamic_rapid.py"
replace_once(
    p,
    'from .frame_lattice import moris_observed_tick\n',
    'from .frame_lattice import moris_next_tick, moris_observed_tick\n',
)
anchor = '''    def _cover_end(self, actor: int) -> float:\n'''
insert = '''    def resume_after_single_charge(self, actor: int, now: float) -> None:\n        """Resume base rapid on the next Moris frame with one restored round."""\n        st = self._states.get(int(actor))\n        if st is None:\n            raise RuntimeError("Fast rapid resume actor has no runtime state")\n        self._moris_frame_observed_actors.add(int(actor))\n        first = moris_next_tick(float(now), horizon=self.duration)\n        st.ammo = 1\n        st.phase = "firing"\n        st.phase_end = first\n        st.fire_deadline = first\n        st.warmup = 0.0\n        st.last_inter = 0.0\n        self._invalidate(st)\n        self.state.set_ammo(int(actor), 1)\n        self.refresh_squad_ammo_plan(float(now))\n\n''' + anchor
replace_once(p, anchor, insert)

# Composite weapon runtime: discover the ordinary single-charge mode separately,
# consume its bullet lifetime after its changed shot, then use the exact resume.
p = "fast_engine/engine/dynamic_weapon.py"
replace_once(
    p,
    '''        "_mode_only_charge_actors",\n        "_mode_only_weapon_change_ids",\n''',
    '''        "_mode_only_charge_actors",\n        "_mode_only_single_charge_actors",\n        "_mode_only_weapon_change_ids",\n''',
)
old = '''        mode_only_ids={}\n        for effect in squad.effects:\n            member=squad.members[effect.actor]\n            if not (\n                effect.effect_type == "weapon_change"\n                and effect_filter(effect)\n                and str(member.weapon.get("fire_mode") or "") == "auto"\n                and effect.parameters.get("weapon_type") in {"SR","RL"}\n                and effect.parameters.get("skill_damage") is True\n            ):\n                continue\n            mode_only_ids[effect.actor]=effect.effect_id\n        self._mode_only_charge_actors=frozenset(mode_only_ids)\n        self._mode_only_weapon_change_ids=dict(mode_only_ids)\n'''
new = '''        mode_only_ids={}\n        single_charge_actors=set()\n        for effect in squad.effects:\n            member=squad.members[effect.actor]\n            params=effect.parameters\n            if not (\n                effect.effect_type == "weapon_change"\n                and effect_filter(effect)\n                and str(member.weapon.get("fire_mode") or "") == "auto"\n            ):\n                continue\n            skill_mode=(\n                params.get("weapon_type") in {"SR","RL"}\n                and params.get("skill_damage") is True\n            )\n            single_mode=(\n                params.get("weapon_type") == "SR"\n                and params.get("max_ammo") == 1\n                and params.get("duration_bullets") == 1\n                and "skill_damage" not in params\n            )\n            if not (skill_mode or single_mode):\n                continue\n            mode_only_ids[effect.actor]=effect.effect_id\n            if single_mode:\n                single_charge_actors.add(effect.actor)\n        self._mode_only_charge_actors=frozenset(mode_only_ids)\n        self._mode_only_single_charge_actors=frozenset(single_charge_actors)\n        self._mode_only_weapon_change_ids=dict(mode_only_ids)\n'''
replace_once(p, old, new)
replace_once(
    p,
    '''            if active_before and not active_after and actor in self._rapid_reload.actors:\n                self._rapid_reload.resume_with_live_full_magazine(actor,float(now))\n''',
    '''            if active_before and not active_after and actor in self._rapid_reload.actors:\n                if actor in self._mode_only_single_charge_actors:\n                    self._rapid_reload.resume_after_single_charge(actor,float(now))\n                else:\n                    self._rapid_reload.resume_with_live_full_magazine(actor,float(now))\n''',
)
replace_once(
    p,
    '''        if (\n            actor not in self._mode_only_charge_actors\n            and self.effects.has_dynamic_bullet_lifetime(actor, now=float(event.time))\n        ):\n            # Skill-weapon mode shots are not normal ammunition shots for Moris\n            # bullet-duration consumption. Ordinary charge shots retain the old path.\n            signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))\n''',
    '''        if (\n            not self.is_skill_weapon_mode(actor, float(event.time))\n            and self.effects.has_dynamic_bullet_lifetime(actor, now=float(event.time))\n        ):\n            # Ordinary charge shots consume duration_bullets after their damage\n            # and post-shot signals. Skill-weapon shots remain excluded.\n            signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))\n''',
)

# Focused regression module.
Path("fast_engine/tests/test_damage_single_charge_weapon_change.py").write_text(r'''from __future__ import annotations

import unittest
from dataclasses import replace

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import SignalContext
from fast_engine.engine.damage_state import DamageTermResolver
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.scheduler import EventKind
from fast_engine.engine.score import (
    _temporary_self_rapid_to_single_charge_weapon_change_score_supported,
    static_normal_score_blockers,
)
from fast_engine.engine.triggers import TriggerIndex

CASES = (
    ("스쿼드2", "츠바이", "과충전 공식", "과충전 공식 2", 3.05, 4.266666666666657, 4.2833333333333234),
    ("레이드_헬름아쿠아스노우", "스노우 화이트", "세븐스 드워프 : I", "세븐스 드워프 : I 2", 3.35, 8.35, 8.366666666666662),
)


def compiled(team: str):
    return compile_moris_squad(spec.build_squad(list(snapshot.SQUADS[team]["members"])))


def owned(squad, actor_name, mode_name, pierce_name):
    actor = squad.names.index(actor_name)
    mode = next(e for e in squad.members[actor].effects if e.name == mode_name)
    pierce = next(e for e in squad.members[actor].effects if e.name == pierce_name)
    return actor, mode, pierce


def replace_effect(squad, effect_id, new_effect):
    members=[]; effects=[]
    for member in squad.members:
        rows=tuple(new_effect if e.effect_id==effect_id else e for e in member.effects)
        members.append(replace(member,effects=rows)); effects.extend(rows)
    effects=tuple(sorted(effects,key=lambda e:e.effect_id))
    return CompiledSquad(tuple(members),TriggerIndex.from_effects(effects,actor_count=len(members)))


class SingleChargeWeaponChangeTests(unittest.TestCase):
    def test_two_public_single_charge_shapes_are_owned(self):
        for team,actor_name,mode_name,pierce_name,*_ in CASES:
            with self.subTest(team=team):
                squad=compiled(team)
                actor,mode,pierce=owned(squad,actor_name,mode_name,pierce_name)
                self.assertTrue(_temporary_self_rapid_to_single_charge_weapon_change_score_supported(squad,mode))
                blockers=static_normal_score_blockers(squad)
                self.assertNotIn(f"weapon_change:{actor_name}:{mode_name}",blockers)
                self.assertNotIn(f"normal_delivery:{actor_name}:{pierce_name}:pierce_enabled",blockers)
                self.assertEqual(mode.parameters["duration_bullets"],1)
                self.assertEqual(pierce.parameters["duration_bullets"],1)

    def test_public_owned_scope_is_exact(self):
        got=[]
        for team,case in snapshot.SQUADS.items():
            members=tuple(case["members"])
            if len(members)!=5 or any(str(x).startswith("test_") for x in members):
                continue
            squad=compile_moris_squad(spec.build_squad(list(members)))
            for effect in squad.effects:
                if effect.effect_type=="weapon_change" and _temporary_self_rapid_to_single_charge_weapon_change_score_supported(squad,effect):
                    got.append((team,squad.members[effect.actor].name,effect.name))
        self.assertEqual(tuple(got),tuple((x[0],x[1],x[2]) for x in CASES))

    def test_one_charge_shot_consumes_mode_and_pierce_then_resumes_one_round_next_frame(self):
        for team,actor_name,mode_name,pierce_name,cast,shot,resume in CASES:
            with self.subTest(team=team):
                squad=compiled(team)
                actor,mode,pierce=owned(squad,actor_name,mode_name,pierce_name)
                runtime=BurstRuntime(
                    squad,
                    BurstPolicy(duration=resume+0.02,first_burst_time=3.0),
                    EnemyStaticProfile(defense=0.0,duration=resume+0.02,core_px=0.0),
                )
                changed=[]; pierce_seen=[]; base=[]
                resolver=DamageTermResolver(squad,runtime.dispatcher.effects,runtime.state,runtime.enemy)
                def shot_sink(a,t):
                    changed.append(t)
                    pierce_seen.append(resolver.resolve(a,now=t).pierce_enabled)
                runtime.weapons.attach_score_shot_sink((actor,),shot_sink)
                runtime.weapons.attach_score_block_sink((actor,),lambda a,c,t: base.append((c,t)))
                runtime.weapons.start(0.0)

                def drain(limit):
                    while runtime.scheduler and (runtime.scheduler.peek_time() or 0.0) <= limit + 1e-9:
                        event=runtime.scheduler.pop()
                        runtime.weapons.advance_to(event.time,inclusive=False)
                        if event.kind is EventKind.WEAPON_BOUNDARY:
                            row=runtime.weapons.handle_boundary(event)
                            if row is not None:
                                for signal in row.pre_signals:
                                    runtime.dispatcher.dispatch(BurstSignal(event.time,signal.event_key,row.actor,row.actor,count_increment=signal.count_increment),context=SignalContext())
                                for signal in row.signals:
                                    runtime.dispatcher.dispatch(BurstSignal(event.time,signal.event_key,row.actor,row.actor,count_increment=signal.count_increment),context=SignalContext())
                        elif event.kind is EventKind.PRE_SHOT_BOUNDARY:
                            row=runtime.weapons.handle_pre_shot_boundary(event)
                            if row is not None:
                                for signal in row.pre_signals:
                                    runtime.dispatcher.dispatch(BurstSignal(event.time,signal.event_key,row.actor,row.actor,count_increment=signal.count_increment),context=SignalContext())
                                if row.score_pending:
                                    runtime.weapons.score_pending_shot(row.actor,event.time)
                                for signal in row.signals:
                                    runtime.dispatcher.dispatch(BurstSignal(event.time,signal.event_key,row.actor,row.actor,count_increment=signal.count_increment),context=SignalContext())
                        elif event.kind is EventKind.STATE_EXPIRE:
                            runtime.dispatcher.handle_expiry(event)
                        elif event.kind is EventKind.STATE_END_NOTIFY:
                            owner,name=event.payload
                            runtime.dispatcher.dispatch(BurstSignal(event.time,f"event:state_end:{name}",int(owner),int(owner)),context=SignalContext())
                        runtime.weapons.sync(event.time)
                    runtime.weapons.advance_to(limit,inclusive=True)

                drain(cast)
                runtime.dispatcher.effects.activate_group(mode,(actor,),cast,runtime.scheduler)
                runtime.dispatcher.effects.activate_group(pierce,(actor,),cast,runtime.scheduler)
                runtime.weapons.sync(cast)
                self.assertFalse(runtime.weapons.is_skill_weapon_mode(actor,cast))
                drain(resume+0.001)

                self.assertEqual(len(changed),1)
                self.assertAlmostEqual(changed[0],shot,places=6)
                self.assertEqual(pierce_seen,[True])
                self.assertFalse(runtime.dispatcher.effects.has_named_state(actor,mode_name,now=shot+1e-8))
                self.assertFalse(runtime.dispatcher.effects.has_named_state(actor,pierce_name,now=shot+1e-8))
                rapid=runtime.weapons._rapid_reload._states[actor]
                self.assertAlmostEqual(rapid.last_shot,resume,places=6)
                self.assertEqual(rapid.ammo,0)

    def test_neighboring_shapes_fail_closed(self):
        squad=compiled("레이드_헬름아쿠아스노우")
        actor,mode,pierce=owned(squad,"스노우 화이트","세븐스 드워프 : I","세븐스 드워프 : I 2")
        bad_modes=(
            replace(mode,parameters={**mode.parameters,"duration_bullets":2}),
            replace(mode,parameters={**mode.parameters,"max_ammo":2}),
            replace(mode,parameters={**mode.parameters,"weapon_type":"RL"}),
            replace(mode,parameters={**mode.parameters,"skill_damage":True}),
            replace(mode,parameters={**mode.parameters,"extra":1}),
            replace(mode,duration=10.0),
        )
        for bad in bad_modes:
            with self.subTest(params=bad.parameters,duration=bad.duration):
                bad_squad=replace_effect(squad,mode.effect_id,bad)
                self.assertFalse(_temporary_self_rapid_to_single_charge_weapon_change_score_supported(bad_squad,bad))
        bad_pierce=replace(pierce,parameters={"duration_bullets":2})
        bad_squad=replace_effect(squad,pierce.effect_id,bad_pierce)
        live=next(e for e in bad_squad.members[actor].effects if e.name==mode.name)
        self.assertFalse(_temporary_self_rapid_to_single_charge_weapon_change_score_supported(bad_squad,live))


if __name__ == "__main__":
    unittest.main()
''',encoding="utf-8")

print("staged generic rapid-to-single-charge weapon-change runtime + score proof + tests")
