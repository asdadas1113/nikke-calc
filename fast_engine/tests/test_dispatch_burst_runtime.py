from __future__ import annotations

import json
import unittest
from pathlib import Path

from calculator.timeline import simulate
from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import compile_condition
from fast_engine.engine.targets import compile_target

ROOT = Path(__file__).resolve().parents[2]
FRAME = 1.0 / 60.0


class CompileGrammarCoverageTests(unittest.TestCase):
    def test_all_current_conditions_and_targets_compile(self):
        skills = json.loads((ROOT / "data" / "parsed_skills.json").read_text(encoding="utf-8"))
        nikke = json.loads((ROOT / "data" / "parsed_nikke.json").read_text(encoding="utf-8"))
        actor_by_name = {name: i for i, name in enumerate(nikke)}
        conditions = 0
        targets = 0
        for effects in skills.values():
            for effect in effects:
                trigger_value = (effect.get("trigger_values") or {}).get("10")
                for condition in (effect.get("trigger") or {}).get("condition", ()):
                    compile_condition(condition, trigger_value=trigger_value)
                    conditions += 1
                compile_target(effect.get("target"), actor_by_name=actor_by_name)
                targets += 1
        self.assertEqual(conditions, 516)
        self.assertEqual(targets, 1799)


class BurstDispatchParityTests(unittest.TestCase):
    def _fast(self, names, duration):
        moris_squad = build_squad(names)
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(moris_squad, compiled, {"duration": duration})
        result = BurstRuntime(compiled, policy).run(duration=duration)
        return moris_squad, compiled, result

    @staticmethod
    def _moris_burst_times(squad, duration, event):
        result = simulate(squad, config={"duration": duration, "rng_mode": "expected"}, verbose=True)
        return [row.t for row in result.log.burst_log if row.event == event]

    def assertFrameClose(self, actual, expected):
        self.assertLessEqual(abs(actual - expected), FRAME + 1e-8, (actual, expected))

    def test_rita_full_burst_cooldown_reduction_tracks_moris_without_frame_loop(self):
        names = ["리타", "크라운", "홍련", "앨리스", "나가"]
        squad, _compiled, fast = self._fast(names, 80.0)
        moris_starts = self._moris_burst_times(squad, 80.0, "full_burst 시작")
        moris_ends = self._moris_burst_times(squad, 80.0, "full_burst 종료")
        self.assertGreaterEqual(len(fast.full_burst_starts), 5)
        for a, b in zip(fast.full_burst_starts[:5], moris_starts[:5]):
            self.assertFrameClose(a, b)
        for a, b in zip(fast.full_burst_ends[:5], moris_ends[:5]):
            self.assertFrameClose(a, b)

    def test_redhood_stage_override_and_self_cooldown_chain_track_moris(self):
        names = ["라피 : 레드 후드", "크라운", "홍련", "앨리스", "나가"]
        squad, compiled, fast = self._fast(names, 45.0)
        # No native B1 exists; battle_start condition should turn Red Hood into B1.
        first_b1 = next(row for row in fast.casts if row[2] == "1")
        self.assertEqual(compiled.names[first_b1[1]], "라피 : 레드 후드")
        moris_starts = self._moris_burst_times(squad, 45.0, "full_burst 시작")
        for a, b in zip(fast.full_burst_starts[:4], moris_starts[:4]):
            # Fast intentionally removes Moris 1/60-step quantization; the lead
            # can accumulate by a few frames over repeated short Red Hood cycles.
            self.assertLessEqual(abs(a - b), 0.05, (a, b))


    def test_killer_wife_full_charge_fast_forward_drives_burst_cooldown(self):
        names = ["D : 킬러 와이프", "아니스", "라피", "미하라", "프로덕트 08"]
        squad, _compiled, fast = self._fast(names, 80.0)
        moris_starts = self._moris_burst_times(squad, 80.0, "full_burst 시작")
        self.assertGreaterEqual(len(fast.full_burst_starts), 6)
        # Without weapon trigger dispatch this fixture falls back to ~20 s
        # burst cycles.  Count-boundary fast-forward restores the 13 s rhythm.
        self.assertLess(fast.full_burst_starts[1] - fast.full_burst_starts[0], 14.0)
        for a, b in zip(fast.full_burst_starts[:6], moris_starts[:6]):
            self.assertFrameClose(a, b)

    def test_modernia_fullburst_duration_only_applies_when_she_casts_b3(self):
        names = ["리타", "크라운", "모더니아", "앨리스", "나가"]
        squad, _compiled, fast = self._fast(names, 40.0)
        self.assertAlmostEqual(fast.full_burst_ends[0] - fast.full_burst_starts[0], 15.0, places=9)
        self.assertAlmostEqual(fast.full_burst_ends[1] - fast.full_burst_starts[1], 10.0, places=9)
        moris_starts = self._moris_burst_times(squad, 40.0, "full_burst 시작")
        moris_ends = self._moris_burst_times(squad, 40.0, "full_burst 종료")
        for a, b in zip(fast.full_burst_starts[:2], moris_starts[:2]):
            self.assertFrameClose(a, b)
        for a, b in zip(fast.full_burst_ends[:2], moris_ends[:2]):
            self.assertFrameClose(a, b)


if __name__ == "__main__":
    unittest.main()
