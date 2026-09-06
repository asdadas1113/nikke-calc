from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage import DamageTerms, HitSpec, expected_damage
from fast_engine.engine.damage_state import DamageTermResolver
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.scheduler import EventScheduler
from fast_engine.engine.score import score_static_squad, static_score_blockers
from fast_engine.engine.state import StateStore
from fast_engine.engine.targets import TargetMode
from fast_engine.engine.triggers import TriggerIndex


class CrownRoyalAttireLifecycleTests(unittest.TestCase):
    TEAM = "레이드_아스카루드밀라"

    @staticmethod
    def _fixture():
        moris = spec.build_squad(list(snapshot.SQUADS[CrownRoyalAttireLifecycleTests.TEAM]["members"]))
        squad = compile_moris_squad(moris)
        crown = next(i for i, member in enumerate(squad.members) if member.name == "크라운")
        naga = next(i for i, member in enumerate(squad.members) if member.name == "나가")
        royal = next(e for e in squad.members[crown].effects if e.name == "로얄 에타이어 4")
        heal = next(e for e in squad.members[naga].effects if e.name == "우정의 서포트 2")
        return moris, squad, crown, naga, royal, heal

    @staticmethod
    def _replace_effect(squad: CompiledSquad, effect_id: int, changed):
        members = list(squad.members)
        owner = squad.effects[effect_id].actor
        members[owner] = replace(
            members[owner],
            effects=tuple(changed if e.effect_id == effect_id else e for e in members[owner].effects),
        )
        effects = tuple(e for member in members for e in member.effects)
        return CompiledSquad(tuple(members), TriggerIndex.from_effects(effects, actor_count=len(members)))

    def test_public_asuka_ludmilla_certifies_and_excludes_only_unreachable_naga_heal(self):
        _moris, squad, crown, _naga, royal, heal = self._fixture()
        self.assertTrue(TriggerDispatcher._lowest_hp_heal_owner_unreachable(squad, heal, crown))
        self.assertTrue(TriggerDispatcher.heal_received_dependency_score_safe(squad, royal))
        self.assertEqual(static_score_blockers(squad), ())

    def test_moris_lowest_hp_two_is_fixed_to_front_pair_in_patternless_tie(self):
        moris, _squad, crown, _naga, _royal, _heal = self._fixture()
        resolved = []
        hp_rows = []
        original = BuffManager._resolve_target

        def traced(manager, target, caster):
            out = original(manager, target, caster)
            if caster == "나가" and target == "allies_lowest_hp:2":
                resolved.append(tuple(out))
                hp_rows.append(tuple(manager.state.get("hp_pct", {}).values()))
            return out

        with patch.object(BuffManager, "_resolve_target", new=traced):
            simulate(moris, config={"duration": 20.0, "rng_mode": "expected"}, verbose=True)
        self.assertGreaterEqual(len(resolved), 5)
        self.assertEqual(set(resolved), {("리틀 머메이드", "나가")})
        self.assertTrue(all(row and set(row) == {100.0} for row in hp_rows))
        self.assertNotIn(crown, (0, 1))

    def test_wider_lowest_hp_count_reaches_crown_and_fails_closed(self):
        _moris, squad, crown, _naga, royal, heal = self._fixture()
        changed = replace(
            heal,
            target="allies_lowest_hp:3",
            target_spec=replace(heal.target_spec, raw="allies_lowest_hp:3", count=3),
        )
        bad = self._replace_effect(squad, heal.effect_id, changed)
        bad_royal = bad.effects[royal.effect_id]
        self.assertFalse(TriggerDispatcher._lowest_hp_heal_owner_unreachable(bad, bad.effects[heal.effect_id], crown))
        self.assertFalse(TriggerDispatcher.heal_received_dependency_score_safe(bad, bad_royal))
        blockers = static_score_blockers(bad)
        self.assertIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)
        self.assertIn("skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)

    def test_any_hp_rank_mutator_revokes_unreachable_provider_proof(self):
        _moris, squad, crown, _naga, royal, heal = self._fixture()
        asuka_heal = next(e for e in squad.effects if e.name == "긴급 수복 4")
        changed = replace(asuka_heal, stat="current_hp_reduce", value=1.0)
        bad = self._replace_effect(squad, asuka_heal.effect_id, changed)
        self.assertFalse(TriggerDispatcher._lowest_hp_heal_owner_unreachable(bad, bad.effects[heal.effect_id], crown))
        self.assertFalse(TriggerDispatcher.heal_received_dependency_score_safe(bad, bad.effects[royal.effect_id]))

    def test_external_all_allies_heal_remains_fail_closed(self):
        _moris, squad, crown, _naga, royal, heal = self._fixture()
        changed = replace(
            heal,
            target="all_allies",
            target_spec=replace(heal.target_spec, raw="all_allies", mode=TargetMode.ALL_ALLIES, count=None),
        )
        bad = self._replace_effect(squad, heal.effect_id, changed)
        self.assertFalse(TriggerDispatcher.heal_received_dependency_score_safe(bad, bad.effects[royal.effect_id]))

    def test_timed_all_ally_buff_refreshes_one_shared_damage_state(self):
        _moris, squad, _crown, _naga, royal, _heal = self._fixture()
        state = StateStore.from_compiled_squad(squad)
        effects = ActiveEffectStore(squad, state)
        scheduler = EventScheduler()
        targets = tuple(range(len(squad.members)))
        effects.activate_group(royal, targets, 1.0, scheduler)
        effects.activate_group(royal, targets, 2.0, scheduler)

        for actor in targets:
            active = DamageTermResolver(squad, effects, state, EnemyStaticProfile(duration=10.0)).resolve(actor, now=8.5)
            expired = DamageTermResolver(squad, effects, state, EnemyStaticProfile(duration=10.0)).resolve(actor, now=9.0)
            self.assertAlmostEqual(active.atk_dmg_pct, 20.99, places=9)
            self.assertAlmostEqual(expired.atk_dmg_pct, 0.0, places=9)

            normal_active = expected_damage(
                base_atk=1000.0, enemy_def=0.0, core_dmg_mult=100.0, full_charge_mult=100.0,
                terms=active, hit=HitSpec(coeff=100.0, is_normal_atk=True),
            )
            normal_base = expected_damage(
                base_atk=1000.0, enemy_def=0.0, core_dmg_mult=100.0, full_charge_mult=100.0,
                terms=DamageTerms(), hit=HitSpec(coeff=100.0, is_normal_atk=True),
            )
            skill_active = expected_damage(
                base_atk=1000.0, enemy_def=0.0, core_dmg_mult=100.0, full_charge_mult=100.0,
                terms=active, hit=HitSpec(coeff=100.0, is_normal_atk=False),
            )
            skill_base = expected_damage(
                base_atk=1000.0, enemy_def=0.0, core_dmg_mult=100.0, full_charge_mult=100.0,
                terms=DamageTerms(), hit=HitSpec(coeff=100.0, is_normal_atk=False),
            )
            self.assertAlmostEqual(normal_active / normal_base, 1.2099, places=9)
            self.assertAlmostEqual(skill_active / skill_base, 1.2099, places=9)

    def test_fast_royal_attire_activation_times_match_moris_self_heal_chain(self):
        moris, squad, _crown, _naga, royal, _heal = self._fixture()
        duration = 40.0
        moris_result = simulate(moris, config={"duration": duration, "rng_mode": "expected"}, verbose=True)
        moris_times = []
        for row in moris_result.log.buff_events:
            if row.name == "로얄 에타이어 4" and row.kind == "activate" and row.target == "크라운":
                moris_times.append(float(row.t))

        fast_times = []
        original = ActiveEffectStore.activate_group
        def traced(store, effect, targets, now, scheduler):
            if effect.effect_id == royal.effect_id:
                fast_times.append(float(now))
            return original(store, effect, targets, now, scheduler)

        policy = compile_burst_policy(moris, squad, {"duration": duration, "rng_mode": "expected"})
        with patch.object(ActiveEffectStore, "activate_group", new=traced):
            score_static_squad(
                squad, policy, EnemyStaticProfile(duration=duration, core_px=0.0), duration=duration
            )
        self.assertEqual(len(moris_times), 2)
        self.assertEqual(len(fast_times), 2)
        for fast, expected in zip(fast_times, moris_times):
            self.assertAlmostEqual(fast, expected, places=9)


    def test_nonzero_core_profile_keeps_dynamic_core_count_fail_closed(self):
        moris, squad, _crown, _naga, _royal, _heal = self._fixture()
        duration = 2.0
        policy = compile_burst_policy(moris, squad, {"duration": duration, "rng_mode": "expected"})
        with self.assertRaisesRegex(NotImplementedError, "dynamic weapon \\+ core_hit_count"):
            score_static_squad(
                squad,
                policy,
                EnemyStaticProfile(duration=duration, core_px=10.0, core_uptime=1.0),
                duration=duration,
            )


if __name__ == "__main__":
    unittest.main()
