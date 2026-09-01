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


# Capability metadata: cadence instant ammo refill is now implemented for the
# score-certified dynamic-recipient slice. Unsupported timing/targets still keep
# their own capability blockers.
replace_once(
    "fast_engine/engine/capabilities.py",
    '        "max_ammo_pct", "max_ammo_flat", "charge_time_flat",\n',
    '        "max_ammo_pct", "max_ammo_flat", "ammo_charge_pct", "ammo_charge_flat", "charge_time_flat",\n',
)

# Dispatcher owns effect activation, but weapon runtime owns the real ammo clock.
replace_once(
    "fast_engine/engine/dispatcher.py",
    "from typing import TYPE_CHECKING\n",
    "from typing import Callable, TYPE_CHECKING\n",
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '        "conditions", "damage_sink", "_effect_table", "_event_counts", "_conditional_counts",\n'
    '        "_activation_counts", "_state_dependency_names", "_gauge_maxima",\n'
    '        "_unsafe_gauge_families", "_strict_score_delivery",\n',
    '        "conditions", "damage_sink", "_effect_table", "_event_counts", "_conditional_counts",\n'
    '        "_activation_counts", "_state_dependency_names", "_gauge_maxima",\n'
    '        "_unsafe_gauge_families", "_strict_score_delivery", "_ammo_charge_sink",\n',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '        "max_ammo_pct",\n        "max_ammo_flat",\n        "charge_time_flat",\n',
    '        "max_ammo_pct",\n        "max_ammo_flat",\n        "ammo_charge_pct",\n        "ammo_charge_flat",\n        "charge_time_flat",\n',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    "        self._strict_score_delivery = False\n",
    "        self._strict_score_delivery = False\n"
    "        self._ammo_charge_sink: Callable[[str, tuple[int, ...], float, float], bool] | None = None\n",
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    "    def enable_strict_score_delivery(self) -> None:\n        self._strict_score_delivery = True\n\n",
    "    def enable_strict_score_delivery(self) -> None:\n"
    "        self._strict_score_delivery = True\n\n"
    "    def attach_ammo_charge_sink(\n"
    "        self,\n"
    "        sink: Callable[[str, tuple[int, ...], float, float], bool],\n"
    "    ) -> None:\n"
    "        self._ammo_charge_sink = sink\n\n",
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '            if stat == "burst_cooldown_reduce":\n'
    '                for target in targets:\n'
    '                    if target != ENEMY:\n'
    '                        self.burst.adjust_cooldown(target, value, now, self.scheduler)\n'
    '            elif stat in self._GAUGE_STATS:\n',
    '            if stat == "burst_cooldown_reduce":\n'
    '                for target in targets:\n'
    '                    if target != ENEMY:\n'
    '                        self.burst.adjust_cooldown(target, value, now, self.scheduler)\n'
    '            elif stat in {"ammo_charge_pct", "ammo_charge_flat"}:\n'
    '                if self._ammo_charge_sink is None or any(target == ENEMY for target in targets):\n'
    '                    return False\n'
    '                actor_targets = tuple(int(target) for target in targets)\n'
    '                if not self._ammo_charge_sink(stat, actor_targets, value, now):\n'
    '                    return False\n'
    '            elif stat in self._GAUGE_STATS:\n',
)

# Composite dynamic weapon runtime mutates its own internal ammo state atomically.
insert_point = '''    def begin_full_burst(
        self,
        now: float,
        casted: Sequence[bool],
        full_burst_end: float,
    ) -> tuple[int, ...]:
        return self._rapid_reload.begin_full_burst(now, casted, full_burst_end)

'''
ammo_methods = insert_point + '''    @staticmethod
    def _ammo_charge_gain(full: int, stat: str, value: float) -> int:
        if stat == "ammo_charge_pct":
            # Moris uses Python round() on final effective maximum ammo.
            return int(round(float(full) * float(value) / 100.0))
        if stat == "ammo_charge_flat":
            return int(value)
        raise ValueError(f"unsupported ammo charge stat: {stat}")

    def apply_ammo_charge(
        self,
        stat: str,
        targets: tuple[int, ...],
        value: float,
        now: float,
    ) -> bool:
        """Apply an instant ammo refill to dynamic weapon state.

        All recipients are validated before mutation. Reload-cancel-on-full is
        intentionally outside this slice; certification rejects such controls.
        """

        if value < 0.0:
            return False
        selected = tuple(dict.fromkeys(int(actor) for actor in targets))
        dynamic = set(self.all_dynamic_actors)
        if not selected or any(actor not in dynamic for actor in selected):
            return False

        # Bring every selected actor to immediately before the instant effect.
        # BurstRuntime already does this globally, but keeping it local makes the
        # callback safe for direct tests and future non-burst instant sources.
        self.advance_to(float(now), inclusive=False)

        for actor in selected:
            if actor in self._rapid_reload.actors:
                runtime = self._rapid_reload
                st = runtime._states.get(actor)
                if st is None:
                    return False
                full = runtime._machine(actor)._full_ammo()
                gain = self._ammo_charge_gain(full, stat, value)
                st.ammo = min(full, st.ammo + gain)
                if st.phase == "reload_wait" and st.ammo > 0:
                    # The empty-magazine probe has not started reloading yet.
                    # Refilled ammo therefore preserves that next fire probe.
                    st.phase = "firing"
                    st.phase_end = max(float(now), st.phase_end)
                runtime._invalidate(st)
                runtime._plan(actor, float(now))
                self.state.set_ammo(actor, st.ammo)
                continue

            st = self._states.get(actor)
            if st is None:
                return False
            full = self._full_ammo(actor, float(now))
            gain = self._ammo_charge_gain(full, stat, value)
            st.ammo = min(full, st.ammo + gain)
            if st.phase == "post_fire_reload" and st.ammo > 0:
                # Refill arrived after the last shot but before reload start.
                # Keep the existing post-fire boundary, then charge again.
                st.phase = "post_fire"
            self._invalidate(st)
            self._plan(actor, float(now))
            self.state.set_ammo(actor, st.ammo)
        return True

'''
replace_once("fast_engine/engine/dynamic_weapon.py", insert_point, ammo_methods)

# Score certification and dynamic actor selection.
score_marker = '''def _reload_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
'''
score_helpers = '''def _actor_has_live_max_ammo_mutation(squad: CompiledSquad, actor: int) -> bool:
    for effect in squad.effects:
        if (effect.stat or "") not in {"max_ammo_pct", "max_ammo_flat", "max_ammo_infinite"}:
            continue
        if _is_folded_static_self_modifier(effect):
            continue
        if actor in _possible_ally_targets(squad, effect):
            return True
    return False


def _ammo_charge_named_event_safe(squad: CompiledSquad, effect) -> bool:
    if not effect.name:
        return True
    event_key = f"event:{effect.name}"
    return not any(
        other.effect_id != effect.effect_id
        and any(rule.event_key == event_key for rule in other.triggers)
        for other in squad.effects
    )


def _ammo_charge_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
    if _actor_has_live_max_ammo_mutation(squad, actor):
        return False
    mode = str(squad.members[actor].weapon.get("fire_mode") or "")
    if mode in {"auto", "auto_warmup"}:
        return _rapid_actor_score_safe(squad, actor)
    if mode == "charge":
        return _charge_actor_score_safe(squad, actor)
    return False


def _is_dynamic_ammo_charge_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") not in {"ammo_charge_pct", "ammo_charge_flat"}:
        return False
    if effect.effect_type != "instant" or effect.value is None or float(effect.value) < 0.0:
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    # Weapon state is initialized after battle_start in BurstRuntime. Keep that
    # lifecycle shape fail-closed in the first ammo-refill slice.
    if any(rule.event_key == "battle_start" for rule in effect.triggers):
        return False
    if not _ammo_charge_named_event_safe(squad, effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(
        _ammo_charge_recipient_score_safe(squad, actor) for actor in targets
    )


def _dynamic_ammo_charge_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if _is_dynamic_ammo_charge_score_supported(squad, effect):
            actors.update(_possible_ally_targets(squad, effect))
    return tuple(sorted(actors))


''' + score_marker
replace_once("fast_engine/engine/score.py", score_marker, score_helpers)

replace_once(
    "fast_engine/engine/score.py",
    "    actors.update(charge & set(_dynamic_reload_score_actors(squad)))\n"
    "    actors.update(_dynamic_charge_bullet_lifetime_score_actors(squad))\n"
    "    return tuple(sorted(actors))\n",
    "    actors.update(charge & set(_dynamic_reload_score_actors(squad)))\n"
    "    actors.update(charge & set(_dynamic_ammo_charge_score_actors(squad)))\n"
    "    actors.update(_dynamic_charge_bullet_lifetime_score_actors(squad))\n"
    "    return tuple(sorted(actors))\n",
)
replace_once(
    "fast_engine/engine/score.py",
    "    actors.update(\n"
    "        actor\n"
    "        for actor, member in enumerate(squad.members)\n"
    "        if member.weapon.get(\"control\")\n"
    "        and _rapid_actor_score_safe(squad, actor, require_cover_control=True)\n"
    "    )\n"
    "    return tuple(sorted(actors))\n",
    "    actors.update(\n"
    "        actor\n"
    "        for actor, member in enumerate(squad.members)\n"
    "        if member.weapon.get(\"control\")\n"
    "        and _rapid_actor_score_safe(squad, actor, require_cover_control=True)\n"
    "    )\n"
    "    actors.update(\n"
    "        actor\n"
    "        for actor in _dynamic_ammo_charge_score_actors(squad)\n"
    "        if str(squad.members[actor].weapon.get(\"fire_mode\") or \"\")\n"
    "        in {\"auto\", \"auto_warmup\"}\n"
    "    )\n"
    "    return tuple(sorted(actors))\n",
)
replace_once(
    "fast_engine/engine/score.py",
    '            if stat == "reload_speed_pct" and _is_dynamic_reload_score_supported(squad, effect):\n'
    '                continue\n'
    '            blockers.append(f"cadence:{label}")\n',
    '            if stat == "reload_speed_pct" and _is_dynamic_reload_score_supported(squad, effect):\n'
    '                continue\n'
    '            if stat in {"ammo_charge_pct", "ammo_charge_flat"} and _is_dynamic_ammo_charge_score_supported(squad, effect):\n'
    '                continue\n'
    '            blockers.append(f"cadence:{label}")\n',
)
replace_once(
    "fast_engine/engine/score.py",
    "        if self.dynamic_reload_actors:\n"
    "            runtime.weapons.attach_score_block_sink(\n"
    "                self.dynamic_reload_actors,\n"
    "                self._score_dynamic_reload_block,\n"
    "            )\n",
    "        if self.dynamic_reload_actors:\n"
    "            runtime.weapons.attach_score_block_sink(\n"
    "                self.dynamic_reload_actors,\n"
    "                self._score_dynamic_reload_block,\n"
    "            )\n"
    "        runtime.dispatcher.attach_ammo_charge_sink(runtime.weapons.apply_ammo_charge)\n",
)

# New focused regressions.
Path("fast_engine/tests/test_damage_dynamic_ammo_charge.py").write_text(r'''from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition, EffectCapability, EffectCategory
from fast_engine.engine.model import CompiledEffect, CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import StaticNormalAttackObserver, static_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.tests.test_damage_dynamic_reload_scoring import _member


def _cap(stat: str, *, name: str = "ammo refill") -> EffectCapability:
    return EffectCapability(
        character="synthetic-reload",
        index=0,
        source="synthetic",
        name=name,
        effect_type="instant",
        stat=stat,
        category=EffectCategory.CADENCE_TIMELINE,
        timing_families=("burst",),
        condition_families=(),
        target_family="ally_static",
        advanced_fields=(),
        disposition=CapabilityDisposition.READY,
        blockers=(),
    )


def _ammo_effect(*, stat: str = "ammo_charge_flat", value: float = 1.0, name: str = "refill") -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name=name,
        effect_type="instant",
        stat=stat,
        polarity="beneficial",
        target="self",
        target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("burst_cast", "burst_cast", TriggerMode.EVENT),),
        value=value,
        duration=None,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=_cap(stat, name=name),
    )


def _named_consumer(effect_id: int = 1) -> CompiledEffect:
    return CompiledEffect(
        effect_id=effect_id,
        actor=0,
        actor_effect_index=1,
        source="synthetic",
        source_tag="skill",
        name="named followup",
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("event:refill", "event:refill", TriggerMode.EVENT),),
        value=10.0,
        duration=5.0,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=EffectCapability(
            character="synthetic-reload",
            index=1,
            source="synthetic",
            name="named followup",
            effect_type="buff",
            stat="atk_pct",
            category=EffectCategory.HIT_FORMULA,
            timing_families=("named_event",),
            condition_families=(),
            target_family="ally_static",
            advanced_fields=(),
            disposition=CapabilityDisposition.PLANNED,
            blockers=("timing:named_event",),
        ),
    )


def _squad(effects: tuple[CompiledEffect, ...], *, fire_mode: str = "auto") -> CompiledSquad:
    member = _member(effects, fire_mode=fire_mode, weapon_type="AR" if fire_mode == "auto" else "SR")
    return CompiledSquad((member,), TriggerIndex.from_effects(effects, actor_count=1))


class DynamicAmmoChargeTests(unittest.TestCase):
    def _runtime(self, effect: CompiledEffect):
        squad = _squad((effect,))
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=5.0, first_burst_time=30.0),
            EnemyStaticProfile(defense=100.0, duration=5.0),
        )
        observer = StaticNormalAttackObserver(runtime, duration=5.0)
        runtime.start(duration=5.0)
        return runtime, observer

    def test_refill_before_reload_start_preserves_next_fire_probe(self):
        runtime, observer = self._runtime(_ammo_effect())
        runtime.weapons.advance_to(0.75, inclusive=False)
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.phase, "reload_wait")
        self.assertEqual(st.ammo, 0)
        before = observer.char_total[0]
        self.assertTrue(runtime.weapons.apply_ammo_charge("ammo_charge_flat", (0,), 1.0, 0.75))
        self.assertEqual(st.phase, "firing")
        self.assertEqual(st.ammo, 1)
        runtime.weapons.advance_to(1.01, inclusive=True)
        self.assertGreater(observer.char_total[0], before)

    def test_refill_during_reload_does_not_cancel_reload(self):
        runtime, _observer = self._runtime(_ammo_effect())
        runtime.weapons.advance_to(1.25, inclusive=False)
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.phase, "reloading")
        self.assertTrue(runtime.weapons.apply_ammo_charge("ammo_charge_flat", (0,), 1.0, 1.25))
        self.assertEqual(st.phase, "reloading")
        self.assertEqual(st.ammo, 1)

    def test_percent_refill_uses_python_round_and_caps_at_full(self):
        runtime, _observer = self._runtime(_ammo_effect(stat="ammo_charge_pct", value=33.26))
        runtime.weapons.advance_to(0.01, inclusive=True)
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.ammo, 1)
        self.assertTrue(runtime.weapons.apply_ammo_charge("ammo_charge_pct", (0,), 33.26, 0.1))
        # max ammo 2 -> round(0.6652) == 1, capped at 2
        self.assertEqual(st.ammo, 2)

    def test_named_event_consumer_keeps_ammo_effect_fail_closed(self):
        refill = _ammo_effect()
        followup = _named_consumer()
        squad = _squad((refill, followup))
        blockers = static_score_blockers(squad)
        self.assertIn("cadence:synthetic-reload:refill:ammo_charge_flat", blockers)

    def test_public_squad1_little_mermaid_ammo_blocker_is_removed(self):
        names = ["리틀 머메이드", "크라운", "라피 : 레드 후드", "미하라 : 본딩 체인", "헬름"]
        compiled = __import__("fast_engine.engine.compiler", fromlist=["compile_moris_squad"]).compile_moris_squad(build_squad(names))
        blockers = static_score_blockers(compiled)
        self.assertNotIn("cadence:리틀 머메이드:세이렌 송 2:ammo_charge_pct", blockers)
        self.assertIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)
        self.assertIn("skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)


if __name__ == "__main__":
    unittest.main()
''')
