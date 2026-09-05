from __future__ import annotations

import unittest

from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers


class DynamicWeaponChangeTest(unittest.TestCase):
    def _team(self, name: str):
        case = snapshot.SQUADS[name]
        squad = spec.build_squad(list(case["members"]))
        return squad, compile_moris_squad(squad)

    def test_red_hood_mint_frika_team_clears_weapon_change_and_max_ammo_blockers(self):
        squad, compiled = self._team("레이드_레드후드퀀시")
        blockers = static_score_blockers(compiled)
        self.assertEqual(blockers, ())
        self.assertFalse(any("weapon_change" in item or "max_ammo" in item for item in blockers))
        cfg = spec.build_config(squad, {
            "duration": 30.0,
            "first_burst_time": 3.0,
            "rng_mode": "expected",
        })
        policy = compile_burst_policy(squad, compiled, cfg)
        score = score_static_squad(
            compiled,
            policy,
            EnemyStaticProfile(defense=31784.0, duration=30.0),
        )
        self.assertEqual(score.unsupported, ())
        self.assertGreater(score.squad_total, 0.0)

    def test_red_hood_transform_activates_and_restores_effective_weapon(self):
        from fast_engine.engine.burst import BurstPolicy, BurstSignal
        from fast_engine.engine.burst_runtime import BurstRuntime

        _squad, compiled = self._team("레이드_레드후드퀀시")
        actor = next(i for i, member in enumerate(compiled.members) if member.name == "레드 후드")
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=20.0, first_burst_time=3.0),
            EnemyStaticProfile(defense=31784.0, duration=20.0),
        )
        runtime.weapons.start(0.0)
        base = runtime.weapons.effective_weapon(actor, 0.0)
        self.assertEqual(base["max_ammo"], compiled.members[actor].weapon["max_ammo"])

        runtime.dispatcher.dispatch(BurstSignal(1.0, "squad_burst_cast:3", actor, actor))
        runtime.weapons.sync(1.0)
        changed = runtime.weapons.effective_weapon(actor, 1.0)
        self.assertEqual(changed["weapon_type"], "SR")
        self.assertEqual(changed["damage_coeff"], 51.46)
        self.assertEqual(changed["max_ammo"], -1)
        self.assertEqual(changed["full_charge_mult"], 250)
        self.assertEqual(changed["post_fire_delay"], 0.3)
        self.assertEqual(runtime.weapons._full_ammo(actor, 1.0), 999999)

        expiry = None
        while runtime.scheduler:
            event = runtime.scheduler.pop()
            if abs(event.time - 11.0) < 1e-9:
                expiry = event
                break
        self.assertIsNotNone(expiry)
        runtime.dispatcher.handle_expiry(expiry)
        runtime.weapons.sync(11.0)
        restored = runtime.weapons.effective_weapon(actor, 11.0)
        self.assertIs(restored, compiled.members[actor].weapon)

    def test_red_hood_transform_shape_is_narrow(self):
        _squad, compiled = self._team("레이드_레드후드퀀시")
        effects = [
            effect for effect in compiled.effects
            if effect.effect_type == "weapon_change"
            and compiled.members[effect.actor].name == "레드 후드"
        ]
        self.assertEqual(len(effects), 1)
        effect = effects[0]
        self.assertEqual(effect.parameters.get("weapon_type"), "SR")
        self.assertEqual(effect.parameters.get("max_ammo"), -1)
        self.assertEqual(effect.parameters.get("damage_coeff"), 51.46)
        self.assertEqual(effect.parameters.get("full_charge_mult"), 250)

    def test_class_changing_weapon_change_stays_blocked(self):
        found = False
        for name, case in snapshot.SQUADS.items():
            if str(name).startswith("지그_") or "스노우 화이트" not in case["members"]:
                continue
            squad = spec.build_squad(list(case["members"]))
            compiled = compile_moris_squad(squad)
            if any(
                blocker.startswith("weapon_change:스노우 화이트:")
                for blocker in static_score_blockers(compiled)
            ):
                found = True
                break
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
