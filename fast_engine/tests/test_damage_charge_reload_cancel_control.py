from __future__ import annotations

from types import SimpleNamespace
import unittest

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.weapon import is_supported_charge_reload_cancel_control


class ChargeReloadCancelControlTests(unittest.TestCase):
    @staticmethod
    def _member(control, *, fire_mode='charge', is_clip=False):
        return SimpleNamespace(
            weapon={
                'fire_mode': fire_mode,
                'is_clip': is_clip,
                'control': control,
            }
        )

    def test_only_exact_pure_charge_cancel_on_full_shape_is_owned(self):
        self.assertTrue(
            is_supported_charge_reload_cancel_control(
                self._member({'reload': {'cancel_on_full': True}})
            )
        )
        for control in (
            {'reload': {'cancel_on_full': False}},
            {'reload': {'cancel_on_full': True, 'lead': 0.1}},
            {'reload': {'cancel_on_full': True}, 'hold': {'policy': 'own_full_burst'}},
        ):
            self.assertFalse(
                is_supported_charge_reload_cancel_control(self._member(control))
            )
        self.assertFalse(
            is_supported_charge_reload_cancel_control(
                self._member({'reload': {'cancel_on_full': True}}, fire_mode='auto')
            )
        )
        self.assertFalse(
            is_supported_charge_reload_cancel_control(
                self._member({'reload': {'cancel_on_full': True}}, is_clip=True)
            )
        )

    @staticmethod
    def _public_runtime():
        entry = snapshot.SQUADS['레이드_볼륨']
        moris_squad = spec.build_squad(list(entry['members']))
        compiled = compile_moris_squad(moris_squad)
        actor = next(i for i, member in enumerate(compiled.members) if member.name == '홍련 : 흑영')
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=8.0, first_burst_time=30.0),
            EnemyStaticProfile(defense=0.0, core_px=0.0, duration=8.0),
        )
        runtime.weapons.actors = tuple(sorted(set(runtime.weapons.actors) | {actor}))
        runtime.start(duration=8.0)
        return runtime, actor

    def test_full_refill_cancels_active_reload_and_partial_refill_does_not(self):
        runtime, actor = self._public_runtime()
        state = runtime.weapons._states[actor]
        full = runtime.weapons._full_ammo(actor, 0.1)
        state.ammo = 0
        state.phase = 'reloading'
        state.phase_end = 2.0
        old_generation = state.generation

        self.assertTrue(
            runtime.weapons.apply_ammo_charge(
                'ammo_charge_flat', (actor,), float(full), 0.1
            )
        )
        self.assertEqual(state.ammo, full)
        self.assertEqual(state.phase, 'charging')
        self.assertGreater(state.generation, old_generation)
        self.assertLess(state.phase_end, 2.0)

        runtime, actor = self._public_runtime()
        state = runtime.weapons._states[actor]
        full = runtime.weapons._full_ammo(actor, 0.1)
        state.ammo = 0
        state.phase = 'reloading'
        state.phase_end = 2.0
        self.assertTrue(
            runtime.weapons.apply_ammo_charge(
                'ammo_charge_flat', (actor,), float(max(1, full - 1)), 0.1
            )
        )
        self.assertLess(state.ammo, full)
        self.assertEqual(state.phase, 'reloading')

    def test_public_frontier_owns_exact_scarlet_live_max_refill(self):
        volume = compile_moris_squad(
            spec.build_squad(list(snapshot.SQUADS['레이드_볼륨']['members']))
        )
        volume_blockers = static_score_blockers(volume)
        self.assertNotIn(
            'cadence:홍련 : 흑영:화무십일홍 · 수라 2:ammo_charge_pct',
            volume_blockers,
        )
        self.assertNotIn(
            'cadence:마스트 : 로망틱 메이드:파이레츠 스피릿 2:reload_speed_pct',
            volume_blockers,
        )
        self.assertNotIn(
            'skill_state_delivery:마스트 : 로망틱 메이드:파이레츠 스피릿:split_dmg_pct',
            volume_blockers,
        )

        squad4 = compile_moris_squad(
            spec.build_squad(list(snapshot.SQUADS['스쿼드4']['members']))
        )
        blockers = static_score_blockers(squad4)
        self.assertNotIn('control:홍련 : 흑영', blockers)
        self.assertEqual(blockers, ())
        self.assertNotIn(
            'cadence:홍련 : 흑영:화무십일홍 · 수라 2:ammo_charge_pct',
            blockers,
        )


if __name__ == '__main__':
    unittest.main()
