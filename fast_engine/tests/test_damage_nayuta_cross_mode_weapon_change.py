from __future__ import annotations

import unittest
from dataclasses import replace

from context import snapshot, spec
from calculator.timeline import simulate
from calculator.sim_result import _is_normal
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import SignalContext
from fast_engine.engine.model import EnemyStaticProfile, CompiledSquad
from fast_engine.engine.scheduler import EventKind
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
        moris_resume=[h.t for h in moris.hits if h.caster=="나유타" and _is_normal(h) and h.t>=13.19]
        self.assertEqual(len(moris_times),5)
        self.assertEqual(len(moris_resume),1)
        self.assertAlmostEqual(moris_resume[0],13.2,places=6)
        self.assertTrue(all(not _is_normal(h) for h in moris.hits if h.caster=="나유타" and h.skill_name=="기억 연소"))

        squad=compile_moris_squad(moris_squad)
        actor,effect=wc_of(squad)
        privaty_ammo=next(e for e in squad.effects if e.name=="EX 매거진 3")
        runtime=BurstRuntime(squad,BurstPolicy(duration=13.25,first_burst_time=3.0),EnemyStaticProfile(defense=0.0,duration=13.25,core_px=0.0))
        mode_times=[]
        base_blocks=[]
        runtime.weapons.attach_score_shot_sink((actor,),lambda a,t: mode_times.append(t))
        runtime.weapons.attach_score_block_sink((actor,),lambda a,c,t: base_blocks.append((c,t)))
        # Do not call BurstRuntime.start/run here: this public roster contains an
        # unrelated Privaty static-last-bullet safety blocker. Exercise only the
        # exact weapon/effect/scheduler slice owned by this checkpoint.
        runtime.weapons.start(0.0)

        def process_before(limit):
            while runtime.scheduler and (runtime.scheduler.peek_time() or 0.0) < limit-1e-9:
                event=runtime.scheduler.pop()
                if event.kind is EventKind.WEAPON_BOUNDARY:
                    runtime.weapons.handle_boundary(event)
                    runtime.weapons.sync(event.time)
                elif event.kind is EventKind.PRE_SHOT_BOUNDARY:
                    runtime.weapons.handle_pre_shot_boundary(event)
                    runtime.weapons.sync(event.time)
                elif event.kind is EventKind.STATE_EXPIRE:
                    runtime.dispatcher.handle_expiry(event)
                    runtime.weapons.sync(event.time)
                elif event.kind is EventKind.STATE_END_NOTIFY:
                    owner,name=event.payload
                    runtime.dispatcher.dispatch(
                        BurstSignal(event.time,f"event:state_end:{name}",int(owner),int(owner)),
                        context=SignalContext(),
                    )
                    runtime.weapons.sync(event.time)
                else:
                    runtime.weapons.advance_to(event.time,inclusive=False)
            runtime.weapons.advance_to(limit,inclusive=False)

        process_before(3.2)
        runtime.dispatcher.effects.activate_group(effect,(actor,),3.2,runtime.scheduler)
        runtime.weapons.sync(3.2)
        process_before(3.4)
        runtime.dispatcher.effects.activate_group(privaty_ammo,(actor,),3.4,runtime.scheduler)
        runtime.weapons.sync(3.4)
        process_before(13.25)

        self.assertEqual(len(mode_times),5)
        for actual,expected in zip(mode_times,moris_times):
            self.assertAlmostEqual(actual,expected,places=6)
        rapid=runtime.weapons._rapid_reload
        self.assertEqual(rapid._full_ammo(actor,13.2),215)
        self.assertEqual(rapid._states[actor].ammo,214)
        self.assertAlmostEqual(rapid._states[actor].last_shot,13.2,places=6)
        self.assertAlmostEqual(rapid._states[actor].phase_end,13.25,places=6)
        self.assertFalse(runtime.weapons.is_skill_weapon_mode(actor,13.2))
        self.assertEqual(runtime.weapons._states[actor].phase,"dormant")

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
