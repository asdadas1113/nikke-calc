from __future__ import annotations

import unittest

from calculator.sim_result import _is_normal
from calculator.timeline import simulate
from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.weapon import (
    simulate_static_weapon_cadence,
    simulate_static_weapon_trigger_boundaries,
)


class WeaponCompileTests(unittest.TestCase):
    def test_compiler_lowers_weapon_delay_and_mode_metadata(self):
        squad = compile_moris_squad(build_squad(["라피", "폴리", "프로덕트 12", "델타", "아니스"]))
        by_name = {member.name: member.weapon for member in squad.members}
        self.assertEqual(by_name["라피"]["fire_mode"], "auto")
        self.assertEqual(by_name["프로덕트 12"]["fire_mode"], "auto_warmup")
        self.assertEqual(by_name["델타"]["fire_mode"], "charge")
        self.assertAlmostEqual(by_name["폴리"]["reload_start_delay"], 0.2)
        self.assertAlmostEqual(by_name["폴리"]["post_reload_delay"], 0.2)
        self.assertTrue(by_name["아니스"]["is_clip"])

    def test_permanent_equipment_and_cube_modifiers_enter_static_cadence(self):
        squad = compile_moris_squad(build_squad(["라피", "폴리", "프로덕트 12", "델타", "아니스"]))
        rapi = squad.members[0]
        from fast_engine.engine.weapon import compile_static_cadence_modifiers
        mods = compile_static_cadence_modifiers(rapi)
        self.assertAlmostEqual(mods.max_ammo_pct, 129.64)
        self.assertAlmostEqual(mods.reload_speed_pct, 29.69)


class WeaponCadenceParityTests(unittest.TestCase):
    NAMES = ["라피", "폴리", "프로덕트 12", "델타", "아니스"]

    @classmethod
    def setUpClass(cls):
        cls.duration = 180.0
        cls.moris_squad = build_squad(cls.NAMES)
        cls.compiled = compile_moris_squad(cls.moris_squad)
        cls.fast = simulate_static_weapon_cadence(cls.compiled, duration=cls.duration)
        cls.moris = simulate(
            cls.moris_squad,
            config={"duration": cls.duration, "rng_mode": "expected"},
            verbose=True,
        )

    def _moris_shots(self, actor: int) -> tuple[int, int]:
        member = self.compiled.members[actor]
        normal = [
            event for event in self.moris.hits
            if event.caster == member.name and _is_normal(event)
        ]
        per_shot = 1
        if member.weapon_type == "SG":
            per_shot = int(member.weapon.get("pellets", 1)) * int(member.weapon.get("muzzles", 1))
        return len(normal) // per_shot, len(normal)

    def test_all_six_weapon_families_keep_180s_shot_counts_close_to_moris(self):
        # This five-person fixture covers AR / SG / MG / SR / RL. SMG shares the
        # fixed-rate auto path with AR and has its own synthetic test below.
        for actor, fast in enumerate(self.fast):
            moris_shots, _ = self._moris_shots(actor)
            tolerance = max(1, round(moris_shots * 0.002))  # 0.2% ranking-engine gate
            self.assertLessEqual(
                abs(fast.shots - moris_shots), tolerance,
                (self.compiled.members[actor].name, fast.shots, moris_shots),
            )

    def test_reload_completion_counts_match_moris_for_180s_fixture(self):
        for actor, fast in enumerate(self.fast):
            name = self.compiled.members[actor].name
            moris_completed = sum(
                1 for row in self.moris.log.reload_log
                if row.caster == name and row.event == "재장전 완료"
            )
            self.assertEqual(fast.reload_completions, moris_completed, name)

    def test_shot_semantics_preserve_sg_pellets_and_charge_hits(self):
        by_name = {member.name: self.fast[i] for i, member in enumerate(self.compiled.members)}
        poli = by_name["폴리"]
        self.assertEqual(poli.hit_events, poli.shots * 10)
        for name in ("델타", "아니스"):
            self.assertEqual(by_name[name].full_charge_hits, by_name[name].shots)


    def test_reducible_full_charge_trigger_materializes_only_threshold_boundaries(self):
        squad = compile_moris_squad(
            build_squad(["D : 킬러 와이프", "아니스", "라피", "미하라", "프로덕트 08"])
        )
        cadence = simulate_static_weapon_cadence(squad, duration=80.0)[0]
        boundaries = [
            row for row in simulate_static_weapon_trigger_boundaries(
                squad, duration=80.0, effect_filter=TriggerDispatcher.is_executable_effect
            )
            if row.actor == 0 and row.event_key == "full_charge_hit"
        ]
        self.assertGreater(cadence.full_charge_hits, 40)
        self.assertEqual(len(boundaries), cadence.full_charge_hits // 8)
        self.assertTrue(all(row.count_increment == 8 for row in boundaries))
        self.assertLess(len(boundaries), cadence.full_charge_hits / 4)

    def test_smg_uses_same_constant_rate_auto_primitive(self):
        squad = compile_moris_squad(
            build_squad(["시그널", "라피", "폴리", "델타", "아니스"])
        )
        fast = simulate_static_weapon_cadence(squad, duration=10.0)[0]
        self.assertGreater(fast.shots, 0)
        self.assertEqual(squad.members[0].weapon["fire_mode"], "auto")


if __name__ == "__main__":
    unittest.main()
