from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition, EffectCapability, EffectCategory
from fast_engine.engine.model import CompiledEffect, CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import StaticNormalAttackObserver, static_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.tests.test_damage_dynamic_reload_scoring import _member


def _cap(stat: str, *, name: str = "ammo refill") -> EffectCapability:
    return EffectCapability(
        character="synthetic-reload",
        index=0,
        source="synthetic",
        name=name,
        effect_type="instant",
        stat=stat,
        category=EffectCategory.CADENCE_TIMELINE,
        timing_families=("burst",),
        condition_families=(),
        target_family="ally_static",
        advanced_fields=(),
        disposition=CapabilityDisposition.READY,
        blockers=(),
    )


def _ammo_effect(*, stat: str = "ammo_charge_flat", value: float = 1.0, name: str = "refill") -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name=name,
        effect_type="instant",
        stat=stat,
        polarity="beneficial",
        target="self",
        target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("burst_cast", "burst_cast", TriggerMode.EVENT),),
        value=value,
        duration=None,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=_cap(stat, name=name),
    )


def _weapon_count_ammo_effect(*, reducible: bool = True) -> CompiledEffect:
    rule = (
        TriggerRule("hit_count:2", "hit_count", TriggerMode.MODULO, threshold=2.0, trigger_count_reducible=True)
        if reducible
        else TriggerRule("hit_count", "hit_count", TriggerMode.EVENT)
    )
    return CompiledEffect(
        effect_id=0, actor=0, actor_effect_index=0, source="synthetic", source_tag="skill",
        name="count refill", effect_type="instant", stat="ammo_charge_flat", polarity="beneficial",
        target="self", target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(), condition_rules=(), triggers=(rule,), value=2.0, duration=None, max_stack=None,
        max_trigger=None, tick_interval=None, parameters={},
        capability=EffectCapability(
            character="synthetic-reload", index=0, source="synthetic", name="count refill",
            effect_type="instant", stat="ammo_charge_flat", category=EffectCategory.CADENCE_TIMELINE,
            timing_families=("weapon_hit",), condition_families=(), target_family="ally_static",
            advanced_fields=(), disposition=CapabilityDisposition.PLANNED, blockers=("timing:weapon_hit",),
        ),
    )


def _named_consumer(effect_id: int = 1) -> CompiledEffect:
    return CompiledEffect(
        effect_id=effect_id,
        actor=0,
        actor_effect_index=1,
        source="synthetic",
        source_tag="skill",
        name="named followup",
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("event:refill", "event:refill", TriggerMode.EVENT),),
        value=10.0,
        duration=5.0,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=EffectCapability(
            character="synthetic-reload",
            index=1,
            source="synthetic",
            name="named followup",
            effect_type="buff",
            stat="atk_pct",
            category=EffectCategory.HIT_FORMULA,
            timing_families=("named_event",),
            condition_families=(),
            target_family="ally_static",
            advanced_fields=(),
            disposition=CapabilityDisposition.PLANNED,
            blockers=("timing:named_event",),
        ),
    )


def _squad(effects: tuple[CompiledEffect, ...], *, fire_mode: str = "auto") -> CompiledSquad:
    member = _member(effects, fire_mode=fire_mode, weapon_type="AR" if fire_mode == "auto" else "SR")
    return CompiledSquad((member,), TriggerIndex.from_effects(effects, actor_count=1))


class DynamicAmmoChargeTests(unittest.TestCase):
    def _runtime(self, effect: CompiledEffect):
        squad = _squad((effect,))
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=5.0, first_burst_time=30.0),
            EnemyStaticProfile(defense=100.0, duration=5.0),
        )
        observer = StaticNormalAttackObserver(runtime, duration=5.0)
        runtime.start(duration=5.0)
        return runtime, observer

    def test_refill_before_reload_start_preserves_next_fire_probe(self):
        runtime, observer = self._runtime(_ammo_effect())
        runtime.weapons.advance_to(0.75, inclusive=False)
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.phase, "reload_wait")
        self.assertEqual(st.ammo, 0)
        before = observer.char_total[0]
        self.assertTrue(runtime.weapons.apply_ammo_charge("ammo_charge_flat", (0,), 1.0, 0.75))
        self.assertEqual(st.phase, "firing")
        self.assertEqual(st.ammo, 1)
        runtime.weapons.advance_to(1.01, inclusive=True)
        self.assertGreater(observer.char_total[0], before)

    def test_refill_during_reload_does_not_cancel_reload(self):
        runtime, _observer = self._runtime(_ammo_effect())
        runtime.weapons.advance_to(1.25, inclusive=False)
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.phase, "reloading")
        self.assertTrue(runtime.weapons.apply_ammo_charge("ammo_charge_flat", (0,), 1.0, 1.25))
        self.assertEqual(st.phase, "reloading")
        self.assertEqual(st.ammo, 1)

    def test_percent_refill_uses_python_round_and_caps_at_full(self):
        runtime, _observer = self._runtime(_ammo_effect(stat="ammo_charge_pct", value=33.26))
        runtime.weapons.advance_to(0.01, inclusive=True)
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.ammo, 1)
        self.assertTrue(runtime.weapons.apply_ammo_charge("ammo_charge_pct", (0,), 33.26, 0.1))
        # max ammo 2 -> round(0.6652) == 1, capped at 2
        self.assertEqual(st.ammo, 2)

    def test_reducible_hit_count_refill_replans_rapid_cadence(self):
        effect = _weapon_count_ammo_effect()
        squad = _squad((effect,))
        self.assertNotIn("cadence:synthetic-reload:count refill:ammo_charge_flat", static_score_blockers(squad))
        runtime = BurstRuntime(squad, BurstPolicy(duration=2.1, first_burst_time=30.0), EnemyStaticProfile(defense=0.0, duration=2.1))
        observer = StaticNormalAttackObserver(runtime, duration=2.1)
        result = runtime.run(duration=2.1, score_observer=observer)
        observer.finish(events_processed=result.events_processed)
        self.assertEqual(runtime.weapons._rapid_reload._states[0].hit_count, 5)
        self.assertEqual(runtime.dispatcher._activation_counts.get(0, 0), 2)

    def test_nonreducible_hit_count_refill_stays_fail_closed(self):
        effect = _weapon_count_ammo_effect(reducible=False)
        self.assertIn("cadence:synthetic-reload:count refill:ammo_charge_flat", static_score_blockers(_squad((effect,))))

    def test_named_event_consumer_keeps_ammo_effect_fail_closed(self):
        refill = _ammo_effect()
        followup = _named_consumer()
        squad = _squad((refill, followup))
        blockers = static_score_blockers(squad)
        self.assertIn("cadence:synthetic-reload:refill:ammo_charge_flat", blockers)

    def test_public_asuka_ludmilla_weapon_count_ammo_blocker_is_removed(self):
        names = ["리틀 머메이드", "나가", "크라운", "아스카 : WILLE", "루드밀라 : 윈터 오너"]
        compiled = __import__("fast_engine.engine.compiler", fromlist=["compile_moris_squad"]).compile_moris_squad(build_squad(names))
        blockers = static_score_blockers(compiled)
        self.assertNotIn("cadence:루드밀라 : 윈터 오너:여왕의 시선 3:ammo_charge_flat", blockers)
        self.assertNotIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)
        self.assertNotIn("skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)

    def test_public_squad1_little_mermaid_ammo_blocker_is_removed(self):
        names = ["리틀 머메이드", "크라운", "라피 : 레드 후드", "미하라 : 본딩 체인", "헬름"]
        compiled = __import__("fast_engine.engine.compiler", fromlist=["compile_moris_squad"]).compile_moris_squad(build_squad(names))
        blockers = static_score_blockers(compiled)
        self.assertNotIn("cadence:리틀 머메이드:세이렌 송 2:ammo_charge_pct", blockers)
        self.assertIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)
        self.assertIn("skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)


if __name__ == "__main__":
    unittest.main()
