from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    p.write_text(text.replace(old, new, 1))


# Live MG warmup-speed belongs to the rapid runtime's weapon state.  It changes
# how much warmup a shot adds, not the interval that was already scheduled by the
# previous shot.
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    '''    def _signature(self, actor: int, now: float) -> tuple[float, ...]:
        return (self.effects.sum_stat(actor, "reload_speed_pct", now=now),)
''',
    '''    def _signature(self, actor: int, now: float) -> tuple[float, ...]:
        mode = str(self.squad.members[actor].weapon.get("fire_mode") or "auto")
        warmup_speed = (
            self.effects.sum_stat(actor, "mg_warmup_speed_pct", now=now)
            if mode == "auto_warmup"
            else 0.0
        )
        return (
            self.effects.sum_stat(actor, "reload_speed_pct", now=now),
            warmup_speed,
        )
''',
)
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    '''        rate = machine._mg_rate(st.warmup)
        inter = 1.0 / rate
        cap = float(self.squad.members[st.actor].weapon.get("warmup_bullets") or 1.0)
        warm_inc = max(0.0, 1.0 + machine.mods.mg_warmup_speed_pct / 100.0)
        st.warmup = min(cap, st.warmup + warm_inc)
        return inter
''',
    '''        rate = machine._mg_rate(st.warmup)
        inter = 1.0 / rate
        cap = float(self.squad.members[st.actor].weapon.get("warmup_bullets") or 1.0)
        warmup_speed = self.effects.sum_stat(
            st.actor,
            "mg_warmup_speed_pct",
            now=st.phase_end,
        )
        warm_inc = max(0.0, 1.0 + warmup_speed / 100.0)
        st.warmup = min(cap, st.warmup + warm_inc)
        return inter
''',
)

# Score certification: mg_warmup_speed_pct only affects MG recipients.  Other
# weapon types in a broad target cohort are cadence no-ops for this stat.
marker = '''def _reload_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
'''
helpers = '''def _is_dynamic_mg_warmup_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") != "mg_warmup_speed_pct":
        return False
    if effect.effect_type != "buff":
        return False
    if effect.parameters.get("duration_bullets") is not None:
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    mg_targets = tuple(
        actor
        for actor in _possible_ally_targets(squad, effect)
        if str(squad.members[actor].weapon.get("fire_mode") or "") == "auto_warmup"
    )
    return all(_rapid_actor_score_safe(squad, actor) for actor in mg_targets)


def _dynamic_mg_warmup_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if not _is_dynamic_mg_warmup_score_supported(squad, effect):
            continue
        actors.update(
            actor
            for actor in _possible_ally_targets(squad, effect)
            if str(squad.members[actor].weapon.get("fire_mode") or "") == "auto_warmup"
        )
    return tuple(sorted(actors))


''' + marker
replace_once("fast_engine/engine/score.py", marker, helpers)

replace_once(
    "fast_engine/engine/score.py",
    '''    actors.update(
        actor
        for actor in _dynamic_ammo_charge_score_actors(squad)
        if str(squad.members[actor].weapon.get("fire_mode") or "")
        in {"auto", "auto_warmup"}
    )
    return tuple(sorted(actors))
''',
    '''    actors.update(
        actor
        for actor in _dynamic_ammo_charge_score_actors(squad)
        if str(squad.members[actor].weapon.get("fire_mode") or "")
        in {"auto", "auto_warmup"}
    )
    actors.update(_dynamic_mg_warmup_score_actors(squad))
    return tuple(sorted(actors))
''',
)

replace_once(
    "fast_engine/engine/score.py",
    '''            if stat in {"ammo_charge_pct", "ammo_charge_flat"} and _is_dynamic_ammo_charge_score_supported(squad, effect):
                continue
            blockers.append(f"cadence:{label}")
''',
    '''            if stat in {"ammo_charge_pct", "ammo_charge_flat"} and _is_dynamic_ammo_charge_score_supported(squad, effect):
                continue
            if stat == "mg_warmup_speed_pct" and _is_dynamic_mg_warmup_score_supported(squad, effect):
                continue
            blockers.append(f"cadence:{label}")
''',
)

Path("fast_engine/tests/test_damage_dynamic_mg_warmup.py").write_text(r'''from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition, EffectCapability, EffectCategory
from fast_engine.engine.model import CompiledEffect, CompiledSquad, EnemyStaticProfile
from fast_engine.engine.normal_attack import expected_normal_block_damage
from fast_engine.engine.score import StaticNormalAttackObserver, static_normal_score_blockers, static_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.tests.test_damage_dynamic_reload_scoring import _member


def _effect(value: float = 100.0, duration: float = 10.0) -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name="live MG warmup",
        effect_type="buff",
        stat="mg_warmup_speed_pct",
        polarity="beneficial",
        target="self",
        target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("burst_cast", "burst_cast", TriggerMode.EVENT),),
        value=value,
        duration=duration,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=EffectCapability(
            character="synthetic-reload",
            index=0,
            source="synthetic",
            name="live MG warmup",
            effect_type="buff",
            stat="mg_warmup_speed_pct",
            category=EffectCategory.CADENCE_TIMELINE,
            timing_families=("burst",),
            condition_families=(),
            target_family="ally_static",
            advanced_fields=(),
            disposition=CapabilityDisposition.READY,
            blockers=(),
        ),
    )


def _squad(effect: CompiledEffect) -> CompiledSquad:
    member = _member((effect,), fire_mode="auto_warmup", weapon_type="MG")
    weapon = dict(member.weapon)
    weapon.update(
        fire_rate=1.0,
        fire_rate_max=3.0,
        warmup_bullets=4,
        warmup_cooldown_time=10.0,
        max_ammo=20,
        reload_time=10.0,
    )
    member = replace(member, weapon=weapon)
    return CompiledSquad((member,), TriggerIndex.from_effects((effect,), actor_count=1))


class DynamicMgWarmupScoringTests(unittest.TestCase):
    def test_live_warmup_speed_changes_compressed_mg_cadence(self):
        effect = _effect()
        squad = _squad(effect)
        self.assertNotIn(
            "cadence:synthetic-reload:live MG warmup:mg_warmup_speed_pct",
            static_normal_score_blockers(squad),
        )

        duration = 2.1
        enemy = EnemyStaticProfile(
            defense=0.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=duration,
        )
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=duration, first_burst_time=10.0),
            enemy,
        )
        runtime.dispatcher.effects.activate(effect, 0, 0.0, runtime.scheduler)
        observer = StaticNormalAttackObserver(runtime, duration=duration)
        result = runtime.run(duration=duration, score_observer=observer)
        score = observer.finish(events_processed=result.events_processed)

        self.assertEqual(observer.dynamic_reload_actors, (0,))
        terms = observer.resolver.resolve(0, now=0.25)
        per_shot = expected_normal_block_damage(
            observer.specs[0],
            shot_count=1,
            base_atk=squad.members[0].base_atk,
            enemy_def=enemy.defense,
            terms=terms,
            core_prob=0.0,
            is_full_burst=False,
            is_optimal_range=False,
        )
        # +100% warmup makes the MG warmup path 0 -> 2 -> 4.  Shots inside
        # [0, 2.1) are therefore 0.0, 1.0, 1.5, 1.833..., four total.
        # The old static-only warmup increment produced only three shots here.
        self.assertAlmostEqual(score.char_total[0], per_shot * 4.0, places=6)

    def test_asuka_public_blocker_is_removed_without_character_whitelist(self):
        names = [
            "리틀 머메이드",
            "델타 : 닌자 시프",
            "크라운",
            "아스카 : WILLE",
            "라피 : 레드 후드",
        ]
        blockers = static_score_blockers(build_squad(names))
        self.assertNotIn(
            "cadence:아스카 : WILLE:긴급 수복 2:mg_warmup_speed_pct",
            blockers,
        )


if __name__ == "__main__":
    unittest.main()
''')
