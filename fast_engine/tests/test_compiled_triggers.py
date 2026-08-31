from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from calculator.buff_manager import BuffManager
from context.spec import build_squad
from fast_engine.engine import TriggerMode, compile_moris_squad, compile_trigger_rule

ROOT = Path(__file__).resolve().parents[2]


class TriggerCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skills = json.loads((ROOT / "data" / "parsed_skills.json").read_text(encoding="utf-8"))
        # _timing_to_index_key has no stateful dependency; one real manager is enough
        # to use Moris itself as the compatibility oracle for all timing strings.
        cls.moris = BuffManager(build_squad(["리타", "크라운", "홍련", "앨리스", "나가"]), {})

    def test_all_current_timings_compile_and_match_moris_notify_index_key(self):
        seen = 0
        mismatches = []
        for char, effects in self.skills.items():
            for effect in effects:
                trigger_value = (effect.get("trigger_values") or {}).get("10")
                for timing in (effect.get("trigger") or {}).get("timing", ()):
                    seen += 1
                    rule = compile_trigger_rule(timing, trigger_value=trigger_value)
                    moris_key = self.moris._timing_to_index_key(timing)
                    if rule.event_key != moris_key:
                        mismatches.append((char, timing, rule.event_key, moris_key))
        self.assertGreater(seen, 0)
        self.assertEqual(mismatches, [])

    def test_timing_modes_preserve_current_count_semantics(self):
        self.assertEqual(compile_trigger_rule("burst_cast_count:2").mode, TriggerMode.AT_LEAST)
        self.assertEqual(compile_trigger_rule("full_burst_start_exact:1").mode, TriggerMode.EXACT)
        full_charge = compile_trigger_rule("full_charge_count:3")
        self.assertEqual(full_charge.mode, TriggerMode.MODULO)
        self.assertTrue(full_charge.trigger_count_reducible)
        conditional = compile_trigger_rule("conditional_hit_count:페이로드 확산:36")
        self.assertEqual(conditional.mode, TriggerMode.CONDITIONAL_MODULO)
        self.assertEqual(conditional.group, "페이로드 확산")
        multi = compile_trigger_rule("multi_hit:5")
        self.assertEqual(multi.mode, TriggerMode.VALUE_AT_LEAST)
        self.assertEqual(multi.event_key, "multi_hit")

    def test_level_dependent_trigger_placeholder_is_resolved_at_compile_time(self):
        rule = compile_trigger_rule("hit_count:{0}", trigger_value=17)
        self.assertEqual(rule.raw, "hit_count:17")
        self.assertEqual(rule.event_key, "hit_count")
        self.assertEqual(rule.threshold, 17)

    def test_periodic_interval_is_numeric_and_not_notify_indexed(self):
        rule = compile_trigger_rule("every:0.0167s")
        self.assertEqual(rule.mode, TriggerMode.PERIODIC)
        self.assertIsNone(rule.event_key)
        self.assertAlmostEqual(rule.interval or 0.0, 0.0167)


class MorisEffectExpansionTests(unittest.TestCase):
    def test_compiler_includes_all_moris_registered_effect_sources(self):
        squad = build_squad(["리타", "크라운", "홍련", "앨리스", "나가"])
        moris = BuffManager(squad, {})
        compiled = compile_moris_squad(squad)
        self.assertEqual(len(compiled.effects), len(moris._effects))
        tags = Counter(effect.source_tag for effect in compiled.effects)
        self.assertGreater(tags["skill"], 0)
        self.assertGreater(tags["equipment"], 0)
        self.assertGreater(tags["cube"], 0)
        self.assertGreater(tags["collection"], 0)
        self.assertFalse(any(effect.capability.category.value == "unknown" for effect in compiled.effects))

    def test_effect_ids_are_contiguous_and_trigger_index_points_to_them(self):
        compiled = compile_moris_squad(build_squad(["리타", "크라운", "홍련", "앨리스", "나가"]))
        self.assertEqual(
            tuple(effect.effect_id for effect in compiled.effects),
            tuple(range(len(compiled.effects))),
        )
        indexed_ids = {
            item.effect_id
            for bucket in compiled.trigger_index.by_event.values()
            for item in bucket
        } | {item.effect_id for item in compiled.trigger_index.periodic}
        triggered_ids = {
            effect.effect_id for effect in compiled.effects if effect.triggers
        }
        self.assertEqual(indexed_ids, triggered_ids)

    def test_compiled_values_resolve_skill_level_and_fixed_sources(self):
        squad = build_squad(["리타", "크라운", "홍련", "앨리스", "나가"])
        compiled = compile_moris_squad(squad)
        # Every fixed-value generated source should already be numeric in Fast IR.
        generated = [e for e in compiled.effects if e.source_tag != "skill" and e.stat]
        self.assertTrue(generated)
        self.assertTrue(all(e.value is not None for e in generated if e.source_tag in {"equipment", "cube", "collection"}))


if __name__ == "__main__":
    unittest.main()
