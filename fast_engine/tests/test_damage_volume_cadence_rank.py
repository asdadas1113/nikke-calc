from __future__ import annotations

from dataclasses import replace
import unittest

from calculator.timeline import simulate
from context import snapshot, spec
import fast_engine.engine.score as score
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import compile_condition
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import StaticNormalAttackObserver, static_score_blockers
from fast_engine.engine.targets import TargetMode


class VolumeCadenceRankContractTests(unittest.TestCase):
    VOLUME = "레이드_볼륨"
    SCARLET = "홍련 : 흑영"
    LIBERALIO = "리버렐리오"

    @staticmethod
    def _compiled(label=VOLUME):
        moris = spec.build_squad(list(snapshot.SQUADS[label]["members"]))
        return moris, compile_moris_squad(moris)

    @staticmethod
    def _effect(compiled, name):
        return next(effect for effect in compiled.effects if effect.name == name)

    @staticmethod
    def _replace_effect(compiled, effect_id, replacement):
        members = []
        for member in compiled.members:
            effects = tuple(
                replacement if effect.effect_id == effect_id else effect
                for effect in member.effects
            )
            members.append(replace(member, effects=effects))
        return replace(compiled, members=tuple(members))

    @staticmethod
    def _public_unique_rows():
        source = []
        for label, row in snapshot.SQUADS.items():
            if str(label).startswith("지그_"):
                continue
            members = tuple(row.get("members") or ())
            if len(members) != 5:
                continue
            if any(str(member).startswith("test_") for member in members):
                continue
            source.append((label, members))
        seen = set()
        for label, members in source:
            if members in seen:
                continue
            seen.add(members)
            yield label, members

    def test_public_volume_is_newly_score_certifiable(self):
        _moris, compiled = self._compiled()
        self.assertEqual(static_score_blockers(compiled), ())

    def test_public_owned_scope_is_exact(self):
        lazy_labels = set()
        ammo_labels = set()
        for label, members in self._public_unique_rows():
            compiled = compile_moris_squad(spec.build_squad(list(members)))
            for effect in compiled.effects:
                if (
                    effect.name == "차분한 수심 4"
                    and score._lazy_rank_target_score_safe(compiled, effect)
                ):
                    lazy_labels.add(label)
                if (
                    effect.name == "화무십일홍 · 수라 2"
                    and score._is_dynamic_ammo_charge_score_supported(compiled, effect)
                ):
                    ammo_labels.add(label)
        self.assertEqual(
            lazy_labels,
            {"스쿼드4", "레이드_네온벨벳", "레이드_볼륨"},
        )
        self.assertEqual(ammo_labels, {"스쿼드4", "레이드_볼륨"})

    def test_moris_oracle_and_fast_first_full_burst_match_owned_state(self):
        moris, compiled = self._compiled()
        oracle = simulate(
            moris,
            config={
                "duration": 5.0,
                "first_burst_time": 3.0,
                "rng_mode": "expected",
            },
            seed=42,
            verbose=True,
        )
        log = oracle.log
        self.assertIsNotNone(log)
        assert log is not None
        fb_start = next(
            float(row.t)
            for row in log.burst_log
            if row.event == "full_burst 시작"
        )
        self.assertAlmostEqual(fb_start, 3.4, places=9)
        lazy = next(
            row
            for row in log.buff_events
            if row.caster == self.LIBERALIO
            and row.name == "차분한 수심 4"
            and row.kind == "activate"
        )
        self.assertAlmostEqual(float(lazy.t), fb_start, places=9)
        self.assertEqual(lazy.target, self.SCARLET)
        ammo_rows = [
            row
            for row in log.ammo_log
            if row.caster == self.SCARLET
            and abs(float(row.t) - fb_start) <= 1e-9
        ]
        self.assertTrue(any(int(row.ammo) == 26 for row in ammo_rows))

        policy = compile_burst_policy(
            moris, compiled, {"duration": 5.0, "first_burst_time": 3.0}
        )
        enemy = EnemyStaticProfile(duration=5.0, core_px=0.0)
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        observer = StaticNormalAttackObserver(runtime, duration=3.401)
        result = runtime.run(duration=3.401, score_observer=observer)
        self.assertLessEqual(
            abs(result.full_burst_starts[0] - fb_start),
            1.0 / 60.0 + 1e-8,
        )
        scarlet = next(
            actor
            for actor, member in enumerate(compiled.members)
            if member.name == self.SCARLET
        )
        self.assertEqual(runtime.weapons._full_ammo(scarlet, fb_start), 26)
        self.assertEqual(runtime.weapons._states[scarlet].ammo, 26)
        lazy_targets = {
            active.target
            for _effect, active in runtime.dispatcher.effects.iter_stat(
                "charge_speed_caster_based_pct", now=fb_start
            )
        }
        self.assertEqual(lazy_targets, {scarlet})

    def test_live_max_refill_requires_single_source_before_refill(self):
        _moris, compiled = self._compiled()
        source = self._effect(compiled, "화무십일홍 · 수라")
        refill = self._effect(compiled, "화무십일홍 · 수라 2")
        self.assertTrue(
            score._same_event_self_max_ammo_before_refill_score_safe(
                compiled, refill, refill.actor
            )
        )

        member = compiled.members[refill.actor]
        effects = list(member.effects)
        i_source = next(
            i for i, row in enumerate(effects) if row.effect_id == source.effect_id
        )
        i_refill = next(
            i for i, row in enumerate(effects) if row.effect_id == refill.effect_id
        )
        effects[i_source], effects[i_refill] = effects[i_refill], effects[i_source]
        members = list(compiled.members)
        members[refill.actor] = replace(member, effects=tuple(effects))
        reordered = replace(compiled, members=tuple(members))
        self.assertFalse(
            score._same_event_self_max_ammo_before_refill_score_safe(
                reordered, refill, refill.actor
            )
        )

        duplicate = replace(
            source,
            effect_id=max(effect.effect_id for effect in compiled.effects) + 1,
            actor_effect_index=max(
                row.actor_effect_index for row in member.effects
            )
            + 1,
        )
        members = list(compiled.members)
        members[refill.actor] = replace(
            member, effects=member.effects + (duplicate,)
        )
        competing = replace(compiled, members=tuple(members))
        self.assertFalse(
            score._same_event_self_max_ammo_before_refill_score_safe(
                competing, refill, refill.actor
            )
        )

    def test_live_max_refill_wider_shapes_fail_closed(self):
        _moris, compiled = self._compiled()
        source = self._effect(compiled, "화무십일홍 · 수라")
        refill = self._effect(compiled, "화무십일홍 · 수라 2")

        half = replace(refill, value=50.0)
        self.assertFalse(
            score._same_event_self_max_ammo_before_refill_score_safe(
                self._replace_effect(compiled, refill.effect_id, half),
                half,
                half.actor,
            )
        )
        conditioned = replace(
            refill,
            conditions=("during_full_burst",),
            condition_rules=(compile_condition("during_full_burst"),),
        )
        self.assertFalse(
            score._same_event_self_max_ammo_before_refill_score_safe(
                self._replace_effect(compiled, refill.effect_id, conditioned),
                conditioned,
                conditioned.actor,
            )
        )
        flat_source = replace(source, stat="max_ammo_flat")
        flat_squad = self._replace_effect(compiled, source.effect_id, flat_source)
        self.assertFalse(
            score._same_event_self_max_ammo_before_refill_score_safe(
                flat_squad, refill, refill.actor
            )
        )

    def test_lazy_charge_speed_shape_stays_narrow(self):
        _moris, compiled = self._compiled()
        lazy = self._effect(compiled, "차분한 수심 4")
        self.assertTrue(TriggerDispatcher._lazy_rank_target_shape_supported(lazy))
        count_two = replace(
            lazy,
            target_spec=replace(lazy.target_spec, count=2),
        )
        self.assertFalse(
            TriggerDispatcher._lazy_rank_target_shape_supported(count_two)
        )
        top_atk = replace(
            lazy,
            target_spec=replace(
                lazy.target_spec,
                mode=TargetMode.TOP_ATK,
                raw="allies_top_atk:1",
            ),
        )
        self.assertFalse(TriggerDispatcher._lazy_rank_target_shape_supported(top_atk))
        conditioned = replace(
            lazy,
            conditions=("during_full_burst",),
            condition_rules=(compile_condition("during_full_burst"),),
        )
        self.assertFalse(
            TriggerDispatcher._lazy_rank_target_shape_supported(conditioned)
        )
        parameterized = replace(lazy, parameters={"unexpected": 1})
        self.assertFalse(
            TriggerDispatcher._lazy_rank_target_shape_supported(parameterized)
        )

    def test_lazy_charge_speed_requires_every_base_b3_to_be_charge_safe(self):
        _moris, compiled = self._compiled()
        lazy = self._effect(compiled, "차분한 수심 4")
        scarlet = next(
            actor
            for actor, member in enumerate(compiled.members)
            if member.name == self.SCARLET
        )
        member = compiled.members[scarlet]
        weapon = dict(member.weapon)
        weapon["fire_mode"] = "auto"
        weapon["weapon_type"] = "SMG"
        members = list(compiled.members)
        members[scarlet] = replace(member, weapon=weapon, weapon_type="SMG")
        unsafe = replace(compiled, members=tuple(members))
        self.assertFalse(score._lazy_rank_target_score_safe(unsafe, lazy))

    def test_lazy_named_state_consumer_keeps_fail_closed(self):
        _moris, compiled = self._compiled()
        lazy = self._effect(compiled, "차분한 수심 4")
        host = compiled.members[0]
        template = host.effects[0]
        consumer = replace(
            template,
            effect_id=max(effect.effect_id for effect in compiled.effects) + 1,
            actor_effect_index=max(row.actor_effect_index for row in host.effects) + 1,
            name="synthetic lazy consumer",
            conditions=("self_state:차분한 수심 4",),
            condition_rules=(compile_condition("self_state:차분한 수심 4"),),
        )
        members = list(compiled.members)
        members[0] = replace(host, effects=host.effects + (consumer,))
        unsafe = replace(compiled, members=tuple(members))
        self.assertFalse(score._lazy_rank_target_score_safe(unsafe, lazy))


if __name__ == "__main__":
    unittest.main()
