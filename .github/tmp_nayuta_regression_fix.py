from __future__ import annotations

from pathlib import Path

p = Path("fast_engine/tests/test_periodic_named_stack_delivery.py")
s = p.read_text(encoding="utf-8")

old = '''    def test_public_nayuta_delivery_opens_but_weapon_change_stays_closed(self):\n'''
new = '''    def test_public_nayuta_delivery_and_exact_weapon_change_are_open(self):\n'''
if old not in s:
    raise SystemExit("public Nayuta regression method anchor missing")
s = s.replace(old, new, 1)

old = '''                self.assertEqual(nayuta_delivery, ())\n                self.assertIn("weapon_change:나유타:기억 연소", blockers)\n'''
new = '''                self.assertEqual(nayuta_delivery, ())\n                self.assertNotIn("weapon_change:나유타:기억 연소", blockers)\n'''
if old not in s:
    raise SystemExit("public Nayuta weapon-change assertion anchor missing")
s = s.replace(old, new, 1)

old = '''        members[self.NAYUTA] = replace(\n            owner,\n            effects=tuple(\n                core_observer if effect.effect_id == base.effect_id else effect\n                for effect in owner.effects\n            ),\n        )\n'''
new = '''        # Isolate the periodic/core-count safety property from the separately\n        # certified Nayuta cross-mode weapon-change lifecycle. Keep every effect\n        # slot/effect_id intact because Dispatcher indexes the flattened table by\n        # compiled effect_id; only neutralize 기억 연소 inside this synthetic fixture.\n        memory_burn = next(effect for effect in owner.effects if effect.name == "기억 연소")\n        inert_memory_burn = replace(\n            memory_burn,\n            name="synthetic inert weapon change",\n            effect_type="stat",\n            stat="atk_pct",\n            target="self",\n            target_spec=replace(memory_burn.target_spec, mode=TargetMode.SELF),\n            conditions=(),\n            condition_rules=(),\n            triggers=(),\n            value=0.0,\n            duration=None,\n            max_stack=None,\n            max_trigger=None,\n            tick_interval=None,\n            parameters={},\n        )\n        members[self.NAYUTA] = replace(\n            owner,\n            effects=tuple(\n                core_observer if effect.effect_id == base.effect_id\n                else inert_memory_burn if effect.effect_id == memory_burn.effect_id\n                else effect\n                for effect in owner.effects\n            ),\n        )\n'''
if old not in s:
    raise SystemExit("periodic/core-count isolation anchor missing")
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("updated stale Nayuta regressions while preserving periodic/core-count fail-closed and effect IDs")
