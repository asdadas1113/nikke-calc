from __future__ import annotations
from pathlib import Path

root=Path(__file__).resolve().parents[1]
weapon=root/'fast_engine/engine/weapon.py'
text=weapon.read_text(encoding='utf-8')
old='''    def _full_ammo(self, actor: int, now: float) -> int:\n        weapon = self.effective_weapon(actor, now)\n        base = int(weapon["max_ammo"])\n        if base < 0:\n            return 999999\n        pct = self._active_sum(actor, "max_ammo_pct", now)\n        flat = self._active_sum(actor, "max_ammo_flat", now)\n        return max(\n            1,\n            base\n            + _round_half_up(base * pct / 100.0)\n            + _round_half_up(flat),\n        )\n'''
new='''    def _full_ammo(self, actor: int, now: float) -> int:\n        weapon = self.effective_weapon(actor, now)\n        base = int(weapon["max_ammo"])\n        if base < 0:\n            return 999999\n\n        def static_folded(effect) -> bool:\n            return (\n                (effect.stat or "") in {"max_ammo_pct", "max_ammo_flat"}\n                and effect.effect_type == "buff"\n                and effect.target_spec.mode.value == "self"\n                and effect.duration in (None, -1.0)\n                and not effect.condition_rules\n                and bool(effect.triggers)\n                and all(rule.event_key == "battle_start" for rule in effect.triggers)\n            )\n\n        # Static cadence already owns permanent self sources.  Preserve the same\n        # source-by-source Moris quantization, then add only live sources from the\n        # active store so battle-start equipment/collection effects are not counted\n        # twice when a temporary max-ammo effect appears.\n        pct_gain = 0\n        flat_gain = 0.0\n        for effect in self.squad.members[actor].effects:\n            if not static_folded(effect):\n                continue\n            value = float(effect.value or 0.0)\n            if (effect.stat or "") == "max_ammo_pct":\n                pct_gain += _round_half_up(base * value / 100.0)\n            else:\n                flat_gain += value\n\n        for stat in ("max_ammo_pct", "max_ammo_flat"):\n            for effect, active in self.effects.iter_stat(stat, now=now):\n                if active.target != actor or static_folded(effect):\n                    continue\n                value = float(effect.value or 0.0) * active.stacks\n                if stat == "max_ammo_pct":\n                    pct_gain += _round_half_up(base * value / 100.0)\n                else:\n                    flat_gain += value\n        return max(1, base + pct_gain + _round_half_up(flat_gain))\n'''
if old not in text:
    raise SystemExit('charge _full_ammo anchor not found')
text=text.replace(old,new,1)
old2='''            if signature != old_signature:\n                st.signature = signature\n                if not wc_changed:\n                    self._invalidate(st)\n                    if (\n                        st.phase == "charging"\n                        and not st.charge_latched\n                        and old_signature is not None\n                        and (signature[4], signature[5])\n                        != (old_signature[4], old_signature[5])\n                    ):\n                        st.phase_end = self._observe_phase_boundary(\n                            st.charge_start + self._effective_charge_time(actor, now)\n                        )\n            if st.scheduled_time is None:\n'''
new2='''            if signature != old_signature:\n                st.signature = signature\n                if not wc_changed:\n                    self._invalidate(st)\n                    if (\n                        st.phase == "charging"\n                        and not st.charge_latched\n                        and old_signature is not None\n                        and (signature[4], signature[5])\n                        != (old_signature[4], old_signature[5])\n                    ):\n                        st.phase_end = self._observe_phase_boundary(\n                            st.charge_start + self._effective_charge_time(actor, now)\n                        )\n\n            # Moris clamps a reduced live magazine immediately whenever the\n            # actor is not inside an active reload. Reloading is the one\n            # exception: completion refills from the live cap at finish.\n            full = self._full_ammo(actor, now)\n            if st.phase != "reloading" and st.ammo > full:\n                st.ammo = full\n                self._invalidate(st)\n\n            if st.scheduled_time is None:\n'''
if old2 not in text:
    raise SystemExit('charge sync anchor not found')
text=text.replace(old2,new2,1)
weapon.write_text(text,encoding='utf-8')

test=root/'fast_engine/tests/test_dynamic_charge_max_ammo_semantics.py'
test.write_text(r'''from __future__ import annotations

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
''',encoding='utf-8')
print('staged charge max-ammo semantics + regression')
