from __future__ import annotations

import unittest
from dataclasses import replace

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import CompiledEffect, CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.tests.test_damage_dynamic_reload_scoring import _capability, _member


def _max_effect(effect_id: int, value: float, *, duration: float = 10.0) -> CompiledEffect:
    return CompiledEffect(
        effect_id=effect_id, actor=0, actor_effect_index=effect_id,
        source="synthetic", source_tag="skill", name=f"live max {effect_id}",
        effect_type="buff", stat="max_ammo_pct",
        polarity="beneficial" if value >= 0 else "harmful",
        target="self", target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(), condition_rules=(),
        triggers=(TriggerRule("full_burst_start", "full_burst_start", TriggerMode.EVENT),),
        value=value, duration=duration, max_stack=1.0, max_trigger=None,
        tick_interval=None, parameters={}, capability=_capability("max_ammo_pct"),
    )


def _charge_squad(effects: tuple[CompiledEffect, ...], *, max_ammo: int = 2) -> CompiledSquad:
    member=_member(effects, fire_mode="charge", weapon_type="SR")
    member=replace(member, weapon={**member.weapon, "max_ammo": max_ammo})
    return CompiledSquad((member,), TriggerIndex.from_effects(effects, actor_count=1))


def _runtime(squad: CompiledSquad, *, duration: float = 10.0) -> BurstRuntime:
    runtime=BurstRuntime(
        squad, BurstPolicy(duration=duration, first_burst_time=20.0),
        EnemyStaticProfile(defense=0.0, duration=duration, core_px=0.0),
    )
    runtime.weapons.attach_score_shot_sink((0,), lambda _actor, _time: None)
    return runtime


class DynamicChargeMaxAmmoSemanticsTests(unittest.TestCase):
    def test_charge_max_ammo_quantizes_each_live_percentage_source_before_sum(self):
        e0=_max_effect(0,25.0); e1=_max_effect(1,25.0)
        squad=_charge_squad((e0,e1),max_ammo=2); runtime=_runtime(squad)
        runtime.dispatcher.effects.activate(e0,0,0.0,runtime.scheduler)
        runtime.dispatcher.effects.activate(e1,0,0.0,runtime.scheduler)
        runtime.weapons.start(0.0)
        self.assertEqual(runtime.weapons._full_ammo(0,0.0),4)
        self.assertEqual(runtime.state.actors[0].ammo,4)

    def test_charge_live_cap_drop_clamps_current_ammo_outside_reload(self):
        effect=_max_effect(0,-50.0); squad=_charge_squad((effect,),max_ammo=14)
        runtime=_runtime(squad); runtime.weapons.start(0.0); st=runtime.weapons._states[0]
        self.assertEqual(st.ammo,14)
        runtime.dispatcher.effects.activate(effect,0,1.0,runtime.scheduler)
        runtime.weapons.sync(1.0)
        self.assertEqual(runtime.weapons._full_ammo(0,1.0),7)
        self.assertEqual(st.ammo,7)
        self.assertEqual(runtime.state.actors[0].ammo,7)

    def test_charge_reload_finish_uses_live_post_expiry_cap(self):
        effect=_max_effect(0,-50.0,duration=1.5); squad=_charge_squad((effect,),max_ammo=14)
        runtime=_runtime(squad,duration=4.0)
        runtime.dispatcher.effects.activate(effect,0,0.0,runtime.scheduler)
        runtime.weapons.start(0.0); st=runtime.weapons._states[0]
        st.ammo=0; st.phase="reloading"; st.phase_end=2.0
        runtime.weapons.sync(2.0)
        self.assertEqual(st.ammo,14)
        self.assertNotEqual(st.phase,"reloading")

    def test_privaty_public_pairs_remain_fail_closed_behind_recipient_dependencies(self):
        names=("스쿼드2","레이드_아니스서머메이든","레이드_라피앨리스","레이드_트리나홍련")
        for name in names:
            with self.subTest(name=name):
                case=snapshot.SQUADS[name]
                compiled=compile_moris_squad(spec.build_squad(list(case["members"])))
                blockers=static_score_blockers(compiled)
                self.assertIn("cadence:프리바티:EX 매거진 2:reload_speed_pct",blockers)
                self.assertIn("cadence:프리바티:EX 매거진 3:max_ammo_pct",blockers)

    def test_privaty_first_full_burst_clamps_snow_charge_magazine_like_moris(self):
        case=snapshot.SQUADS["스쿼드2"]
        compiled=compile_moris_squad(spec.build_squad(list(case["members"])))
        snow=next(i for i,m in enumerate(compiled.members) if m.name=="스노우 화이트 : 헤비암즈")
        privaty=next(i for i,m in enumerate(compiled.members) if m.name=="프리바티")
        runtime=BurstRuntime(
            compiled, BurstPolicy(duration=20.0,first_burst_time=30.0),
            EnemyStaticProfile(defense=0.0,duration=20.0,core_px=0.0),
        )
        runtime.weapons.attach_score_shot_sink((snow,),lambda _actor,_time:None)
        runtime.weapons.start(0.0); st=runtime.weapons._states[snow]
        st.ammo=12; runtime.state.set_ammo(snow,12)
        runtime.dispatcher.dispatch(BurstSignal(3.4,"full_burst_start",privaty,privaty))
        runtime.weapons.sync(3.4)
        self.assertEqual(runtime.weapons._full_ammo(snow,3.4),11)
        self.assertEqual(st.ammo,11)


if __name__ == "__main__": unittest.main()
