from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from context.spec import build_squad
from fast_engine.engine import (
    ENEMY,
    CapabilityDisposition,
    EffectCategory,
    StateDomain,
    StateStore,
    compile_moris_squad,
    inspect_effect,
)
from fast_engine.engine.capabilities import classify_effect, condition_family, target_family, timing_family

ROOT = Path(__file__).resolve().parents[2]


class CapabilityManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skills = json.loads((ROOT / "data" / "parsed_skills.json").read_text(encoding="utf-8"))
        cls.names = frozenset(cls.skills)

    def test_all_current_effects_have_known_semantic_category_and_generic_grammar(self):
        categories = Counter()
        custom_timing = []
        custom_condition = []
        custom_target = []
        total = 0
        for char, effects in self.skills.items():
            for effect in effects:
                total += 1
                category = classify_effect(effect, root=ROOT)
                categories[category] += 1
                trigger = effect.get("trigger") or {}
                custom_timing.extend(
                    (char, t) for t in trigger.get("timing", []) if timing_family(str(t)) == "custom"
                )
                custom_condition.extend(
                    (char, c) for c in trigger.get("condition", []) if condition_family(str(c)) == "custom"
                )
                if target_family(effect.get("target"), character_names=self.names) == "custom":
                    custom_target.append((char, effect.get("target")))
        self.assertEqual(total, 1799)
        self.assertEqual(categories[EffectCategory.UNKNOWN], 0)
        self.assertEqual(custom_timing, [])
        self.assertEqual(custom_condition, [])
        self.assertEqual(custom_target, [])

    def test_current_special_fallback_surface_is_explicit_and_tiny(self):
        rows = []
        for char, effects in self.skills.items():
            for i, effect in enumerate(effects):
                cap = inspect_effect(char, i, effect, root=ROOT, character_names=self.names)
                if cap.disposition is CapabilityDisposition.FALLBACK:
                    rows.append((char, cap.stat))
        self.assertEqual(
            rows,
            [
                ("신데렐라 : 크리스탈 웨이브", "squad_ammo_consume_as"),
                ("아인", "feather_refresh"),
                ("아인", "feather_refresh"),
            ],
        )

    def test_moris_nop_does_not_block_fast_routing_contract(self):
        # projectile_dmg_pct is documented as Moris NOP in this snapshot.
        synthetic = {
            "source": "스킬1", "type": "buff", "name": "x",
            "trigger": {"timing": ["battle_start"], "condition": []},
            "target": "self", "stat": "projectile_dmg_pct", "values": {"10": 1.0},
        }
        cap = inspect_effect("synthetic", 0, synthetic, root=ROOT, character_names=self.names)
        self.assertEqual(cap.disposition, CapabilityDisposition.MIRROR_MORIS_NOP)
        self.assertFalse(cap.blocks_fast)

    def test_weapon_count_capability_is_narrowly_certified(self):
        killer = compile_moris_squad(
            build_squad(["D : 킬러 와이프", "아니스", "라피", "미하라", "프로덕트 08"])
        )
        kw = next(e for e in killer.members[0].effects if e.stat == "burst_cooldown_reduce")
        self.assertEqual(kw.capability.disposition, CapabilityDisposition.READY)

        dorothy = compile_moris_squad(
            build_squad(["도로시", "아니스", "라피", "미하라", "프로덕트 08"])
        )
        last_bullet = next(
            e for e in dorothy.members[0].effects
            if e.stat == "burst_cooldown_reduce" and any(r.raw == "last_bullet_fire" for r in e.triggers)
        )
        self.assertEqual(last_bullet.capability.disposition, CapabilityDisposition.PLANNED)
        self.assertIn("timing:weapon_hit", last_bullet.capability.blockers)

    def test_unknown_synthetic_mechanic_fails_closed(self):
        synthetic = {
            "source": "스킬1", "type": "instant", "name": "x",
            "trigger": {"timing": ["battle_start"], "condition": []},
            "target": "self", "stat": "future_unknown_fast_stat",
        }
        cap = inspect_effect("synthetic", 0, synthetic, root=ROOT, character_names=self.names)
        self.assertEqual(cap.disposition, CapabilityDisposition.UNKNOWN)
        self.assertTrue(cap.blocks_fast)


class StateStoreTests(unittest.TestCase):
    def test_state_refresh_uses_generation_to_ignore_stale_expiry(self):
        store = StateStore(2)
        first = store.set_state(0, "buff", effect_id=3, source_actor=0, expires_at=10.0)
        second = store.set_state(0, "buff", effect_id=3, source_actor=0, expires_at=20.0)
        self.assertNotEqual(first, second)
        self.assertFalse(store.expire_state(0, "buff", first, now=10.0))
        self.assertTrue(store.has_state(0, "buff", now=10.0))
        self.assertTrue(store.expire_state(0, "buff", second, now=20.0))
        self.assertFalse(store.has_state(0, "buff"))

    def test_noop_mutation_does_not_invalidate_versions(self):
        store = StateStore(1, initial_hp=[100.0], initial_ammo=[10.0])
        before = store.version
        store.set_hp(0, 100.0)
        store.set_ammo(0, 10.0)
        self.assertEqual(store.version, before)
        store.set_ammo(0, 9.0)
        self.assertGreater(store.version, before)

    def test_damage_memory_does_not_invalidate_effect_cache_token(self):
        store = StateStore(1)
        effect_token = store.dependency_token(domains=(StateDomain.EFFECT, StateDomain.HEALTH))
        store.record_damage(0, 12345.0)
        self.assertEqual(
            store.dependency_token(domains=(StateDomain.EFFECT, StateDomain.HEALTH)),
            effect_token,
        )
        self.assertEqual(store.domain_version(StateDomain.EFFECT), 0)
        self.assertEqual(store.domain_version(StateDomain.DAMAGE_MEMORY), 1)

    def test_actor_scoped_tokens_do_not_invalidate_other_actor(self):
        store = StateStore(2)
        token = store.dependency_token(entities=(1,), domains=(StateDomain.EFFECT,))
        store.set_gauge(0, "ticket", 1.0)
        self.assertEqual(
            store.dependency_token(entities=(1,), domains=(StateDomain.EFFECT,)), token
        )
        self.assertNotEqual(
            store.dependency_token(entities=(0,), domains=(StateDomain.EFFECT,)), token
        )

    def test_enemy_named_state_has_independent_version_lane(self):
        store = StateStore(1)
        actor_token = store.dependency_token(entities=(0,), domains=(StateDomain.EFFECT,))
        store.set_state(ENEMY, "debuff", effect_id=4, source_actor=0, expires_at=5.0)
        self.assertTrue(store.has_state(ENEMY, "debuff", now=1.0))
        self.assertEqual(
            store.dependency_token(entities=(0,), domains=(StateDomain.EFFECT,)), actor_token
        )
        self.assertEqual(store.entity_version(ENEMY, StateDomain.EFFECT), 1)

    def test_state_store_can_boot_from_real_compiled_moris_squad(self):
        squad = compile_moris_squad(build_squad(["리타", "크라운", "홍련", "앨리스", "나가"]))
        store = StateStore.from_compiled_squad(squad)
        self.assertEqual(len(store.actors), 5)
        self.assertTrue(all(a.hp > 0 for a in store.actors))
        self.assertTrue(all(a.ammo >= 0 for a in store.actors))
        self.assertTrue(all(len(c.effects) == len(c.effect_capabilities) for c in squad.members))
        # Greenfield baseline has infrastructure only; combat effect dispatch is not falsely certified.
        self.assertFalse(squad.fast_ready)
        self.assertTrue(squad.capability_blockers)

    def test_stack_and_gauge_clamping(self):
        store = StateStore(1)
        store.set_state(0, "stacked", effect_id=1, source_actor=0, stacks=2, max_stacks=5)
        self.assertEqual(store.add_stack(0, "stacked", 99), 5)
        self.assertEqual(store.add_stack(0, "stacked", -99), 0)
        self.assertEqual(store.add_gauge(0, "g", 15, maximum=10), 10)
        self.assertEqual(store.add_gauge(0, "g", -99, maximum=10), 0)


if __name__ == "__main__":
    unittest.main()
