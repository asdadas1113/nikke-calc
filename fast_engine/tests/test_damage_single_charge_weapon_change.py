from __future__ import annotations

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

    def test_squad2_resolves_only_privaty_reload_recipient_dependency(self):
        blockers=static_normal_score_blockers(compiled("스쿼드2"))
        self.assertNotIn("cadence:프리바티:EX 매거진 2:reload_speed_pct",blockers)
        self.assertIn("cadence:프리바티:EX 매거진 3:max_ammo_pct",blockers)

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
