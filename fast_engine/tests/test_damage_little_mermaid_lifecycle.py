from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.enemy_replacement import certified_enemy_received_damage_replacements
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import (
    StaticNormalAttackObserver,
    _certified_squad_ammo_effect_ids,
    score_static_squad,
    static_score_blockers,
)
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.triggers import TriggerIndex


class LittleMermaidLifecycleTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        moris=spec.build_squad(list(snapshot.SQUADS['레이드_델타']['members']))
        squad=compile_moris_squad(moris)
        actor=next(i for i,m in enumerate(squad.members) if m.name=='리틀 머메이드')
        by_name={e.name:e for e in squad.members[actor].effects if e.name}
        return moris,squad,actor,by_name

    @staticmethod
    def _replace_effect(squad,effect_id,new_effect):
        members=list(squad.members)
        owner=squad.effects[effect_id].actor
        members[owner]=replace(
            members[owner],
            effects=tuple(new_effect if e.effect_id==effect_id else e for e in members[owner].effects),
        )
        effects=tuple(e for m in members for e in m.effects)
        return CompiledSquad(tuple(members),TriggerIndex.from_effects(effects,actor_count=len(members)))

    def test_public_delta_has_no_blockers_and_exact_owned_ids(self):
        _moris,squad,actor,by_name=self._fixture()
        self.assertEqual(static_score_blockers(squad),())
        rows=certified_enemy_received_damage_replacements(squad)
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row.actor,actor)
        self.assertEqual(row.source_effect_id,by_name['거품'].effect_id)
        self.assertEqual(row.replacement_effect_id,by_name['터진 거품'].effect_id)
        self.assertEqual(row.remover_effect_id,by_name['터진 거품 3'].effect_id)
        self.assertEqual(row.threshold,50)
        self.assertEqual(_certified_squad_ammo_effect_ids(squad),frozenset({by_name['거품 난사'].effect_id}))

    def test_moris_and_fast_replace_source_at_fiftieth_hit(self):
        moris,squad,_actor,by_name=self._fixture()
        result=simulate(moris,config={'duration':3.0,'rng_mode':'expected'},verbose=True)
        moris_new=[float(x.t) for x in result.log.buff_events if x.name=='터진 거품' and x.kind=='activate']
        moris_old_end=[float(x.t) for x in result.log.buff_events if x.name=='거품' and x.kind=='expire']
        self.assertEqual(len(moris_new),1); self.assertEqual(len(moris_old_end),1)

        fast_new=[]; fast_remove=[]
        orig_activate=ActiveEffectStore.activate_group
        orig_remove=ActiveEffectStore.remove_named_state
        def traced_activate(store,effect,targets,now,scheduler):
            out=orig_activate(store,effect,targets,now,scheduler)
            if effect.effect_id==by_name['터진 거품'].effect_id and out:
                fast_new.append(float(now))
            return out
        def traced_remove(store,target,name,*,now):
            out=orig_remove(store,target,name,now=now)
            if name=='거품' and out:
                fast_remove.append(float(now))
            return out
        policy=compile_burst_policy(moris,squad,{'duration':3.0,'rng_mode':'expected'})
        with patch.object(ActiveEffectStore,'activate_group',new=traced_activate), patch.object(ActiveEffectStore,'remove_named_state',new=traced_remove):
            score_static_squad(squad,policy,EnemyStaticProfile(duration=3.0,core_px=0.0),duration=3.0)
        self.assertEqual(len(fast_new),1); self.assertEqual(len(fast_remove),1)
        self.assertAlmostEqual(fast_new[0],moris_new[0],places=9)
        self.assertAlmostEqual(fast_remove[0],moris_old_end[0],places=9)
        self.assertAlmostEqual(fast_new[0],2.05,places=9)

    def test_global_500_crossing_matches_moris_and_is_pre_normal_shot(self):
        moris,squad,_actor,by_name=self._fixture()
        policy=compile_burst_policy(moris,squad,{'duration':8.1,'rng_mode':'expected'})
        crossings=[]; order=[]
        orig_team=TriggerDispatcher.dispatch_team_hit
        orig_activate=SimpleDamageScoreSink.activate
        orig_score=StaticNormalAttackObserver._score_dynamic_reload_block
        def traced_team(dispatcher,event_key,**kwargs):
            if event_key=='squad_ammo_consume': crossings.append(float(kwargs['time']))
            return orig_team(dispatcher,event_key,**kwargs)
        def traced_activate(sink,effect,**kwargs):
            if effect.effect_id==by_name['거품 난사'].effect_id:
                order.append(('skill',float(kwargs['now'])))
            return orig_activate(sink,effect,**kwargs)
        def traced_score(observer,actor,count,time):
            if crossings and abs(float(time)-crossings[-1])<1e-9 and count==1:
                order.append(('normal',float(time)))
            return orig_score(observer,actor,count,time)
        with patch.object(TriggerDispatcher,'dispatch_team_hit',new=traced_team), patch.object(SimpleDamageScoreSink,'activate',new=traced_activate), patch.object(StaticNormalAttackObserver,'_score_dynamic_reload_block',new=traced_score):
            fast=score_static_squad(squad,policy,EnemyStaticProfile(duration=8.1,core_px=0.0),duration=8.1)
        self.assertEqual(len(crossings),3)
        expected=(4.133333333333324,6.033333333333317,7.93333333333331)
        for actual,want in zip(crossings,expected): self.assertAlmostEqual(actual,want,places=9)
        first=[kind for kind,t in order if abs(t-crossings[0])<1e-9]
        self.assertGreaterEqual(len(first),2)
        self.assertEqual(first[:2],['skill','normal'])
        self.assertLess(fast.events_processed,500)

    def test_sequential_damage_keeps_exact_ten_hit_spec(self):
        _moris,squad,_actor,by_name=self._fixture()
        ids=_certified_squad_ammo_effect_ids(squad)
        sink=SimpleDamageScoreSink(
            squad,EnemyStaticProfile(duration=1.0),
            certified_squad_ammo_effect_ids=ids,
        )
        effect=by_name['거품 난사']
        self.assertTrue(sink.supports(effect))
        self.assertEqual(sink.specs[effect.effect_id].hit_count,10)

    def test_neighboring_replacement_shapes_fail_closed(self):
        _moris,squad,_actor,by_name=self._fixture()
        replacement=by_name['터진 거품']
        bad=self._replace_effect(squad,replacement.effect_id,replace(replacement,value=float(replacement.value)+1.0))
        self.assertFalse(certified_enemy_received_damage_replacements(bad))
        self.assertIn('normal_state:리틀 머메이드:터진 거품 3:remove_named_buff',static_score_blockers(bad))

        remover=by_name['터진 거품 3']
        bad2=self._replace_effect(squad,remover.effect_id,replace(remover,parameters={'target_effect':'터진 거품'}))
        self.assertFalse(certified_enemy_received_damage_replacements(bad2))

    def test_wider_squad_ammo_family_stays_closed(self):
        _moris,squad,_actor,by_name=self._fixture()
        barrage=by_name['거품 난사']
        extra=by_name['세이렌 송']
        # A second non-NOP squad-ammo consumer invalidates the narrow ownership proof.
        rule=replace(barrage.triggers[0],threshold=250.0,raw='squad_ammo_consume:250')
        widened=replace(extra,triggers=(rule,))
        bad=self._replace_effect(squad,extra.effect_id,widened)
        self.assertFalse(_certified_squad_ammo_effect_ids(bad))
        self.assertIn('skill_damage:리틀 머메이드:거품 난사:sequential_damage:10',static_score_blockers(bad))


if __name__=='__main__':
    unittest.main()
