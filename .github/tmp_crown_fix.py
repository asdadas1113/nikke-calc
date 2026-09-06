from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT / 'fast_engine/engine/burst_runtime.py'
text = runtime.read_text(encoding='utf-8')
old = '''        if not interested:
            return

        unsupported = interested & dynamic_actors
'''
new = '''        if not interested:
            return

        # A structurally zero core probability cannot emit core_hit_count at all.
        # Skip dynamic cadence validation before it can reject an unreachable
        # event family. This does not widen live-core support: any nonzero core
        # profile continues through the existing dynamic/accuracy fail-closed
        # guards below.
        if self.enemy.core_px is None:
            if self.enemy.effective_core_rate <= 0.0:
                return
        elif self.enemy.core_px <= 0.0 or self.enemy.core_uptime <= 0.0:
            return

        unsupported = interested & dynamic_actors
'''
if old not in text:
    raise SystemExit('core scheduling guard anchor not found')
runtime.write_text(text.replace(old, new, 1), encoding='utf-8')

test = ROOT / 'fast_engine/tests/test_damage_crown_royal_attire_lifecycle.py'
text = test.read_text(encoding='utf-8')
anchor = '''\n\nif __name__ == "__main__":\n    unittest.main()\n'''
method = r'''
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
'''
if anchor not in text:
    raise SystemExit('test module anchor not found')
test.write_text(text.replace(anchor, '\n' + method + anchor, 1), encoding='utf-8')
