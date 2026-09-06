from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"patch anchor not found: {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Effective weapon: materialize the first cross-class rapid override from
# weapon-type defaults without character-name branches.
patch(
    "fast_engine/engine/weapon.py",
    '_FRAME_RATE_CAP = 60.0\n',
    '''_FRAME_RATE_CAP = 60.0\n\n_CERTIFIED_AUTO_WEAPON_CHANGE_DEFAULTS = {\n    "SMG": {\n        "fire_mode": "auto",\n        "fire_rate": 24.0,\n        "fire_rate_max": None,\n        "warmup_bullets": 1.0,\n        "warmup_cooldown_time": 1.0,\n        "post_fire_delay": 0.0,\n        "post_reload_delay": 0.0,\n        "reload_start_delay": 0.0,\n        "cover_during_delay": False,\n        "charge_time": 0.0,\n        "pellets": 1,\n        "muzzles": 1,\n        "is_clip": False,\n        "normal_hit_coeff": 1.0,\n        "core_base_diameter": 110.0,\n        "core_acc_slope": 1.0,\n        "core_model_n": 2.55,\n        "control": {},\n    },\n}\n''',
)
patch(
    "fast_engine/engine/weapon.py",
    '''        effect, _active = row\n        params = effect.parameters\n        weapon = dict(base)\n        for key in (\n''',
    '''        effect, _active = row\n        params = effect.parameters\n        weapon = dict(base)\n        changed_type = str(params.get("weapon_type") or weapon.get("weapon_type") or "")\n        base_type = str(base.get("weapon_type") or "")\n        defaults = _CERTIFIED_AUTO_WEAPON_CHANGE_DEFAULTS.get(changed_type)\n        if changed_type != base_type and defaults is not None:\n            weapon.update(defaults)\n            weapon["weapon_type"] = changed_type\n            weapon["_moris_frame_observed"] = True\n            weapon["_weapon_change_effect_id"] = int(effect.effect_id)\n        for key in (\n''',
)

# 2) Rapid runtime: consult the live effective weapon, preserve whole-combat
# hit_count across mode edges, reset only physical mode session state, and use
# sparse Moris frame observation for the certified changed auto weapon.
patch(
    "fast_engine/engine/dynamic_reload.py",
    'from .scheduler import EventKind, EventScheduler, ScheduledEvent\n',
    'from .scheduler import EventKind, EventScheduler, ScheduledEvent\nfrom .frame_lattice import moris_observed_tick\n',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''        "_states",\n        "_score_sink",\n    )\n''',
    '''        "_states",\n        "_score_sink",\n        "_effective_weapon",\n    )\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''        self._states: dict[int, _RapidActorState] = {}\n        self._score_sink: Callable[[int, int, float], None] | None = None\n\n        hit_thresholds''',
    '''        self._states: dict[int, _RapidActorState] = {}\n        self._score_sink: Callable[[int, int, float], None] | None = None\n        self._effective_weapon: Callable[[int, float], dict] | None = None\n\n        hit_thresholds''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''    def attach_score_sink(\n        self,\n''',
    '''    def attach_effective_weapon(\n        self, callback: Callable[[int, float], dict]\n    ) -> None:\n        if self._states:\n            raise RuntimeError("Fast effective weapon callback must be attached before weapon start")\n        self._effective_weapon = callback\n\n    def _weapon(self, actor: int, now: float) -> dict:\n        if self._effective_weapon is None:\n            return self.squad.members[actor].weapon\n        return self._effective_weapon(actor, float(now))\n\n    def attach_score_sink(\n        self,\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''    def _full_ammo(self, actor: int, now: float) -> int:\n        base_full = self._machine(actor)._full_ammo()\n        base_weapon = int(self.squad.members[actor].weapon["max_ammo"])\n''',
    '''    def _full_ammo(self, actor: int, now: float) -> int:\n        weapon = self._weapon(actor, now)\n        if int(weapon.get("max_ammo", 0)) < 0:\n            return 999999\n        base_full = self._machine(actor)._full_ammo()\n        base_weapon = int(self.squad.members[actor].weapon["max_ammo"])\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''    def _signature(self, actor: int, now: float) -> tuple[float, ...]:\n        mode = str(self.squad.members[actor].weapon.get("fire_mode") or "auto")\n''',
    '''    def _signature(self, actor: int, now: float) -> tuple[float, ...]:\n        weapon = self._weapon(actor, now)\n        mode = str(weapon.get("fire_mode") or "auto")\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''        return (\n            self.effects.sum_stat(actor, "reload_speed_pct", now=now),\n            warmup_speed,\n            float(self._full_ammo(actor, now)),\n        )\n\n    def _hits_per_shot(self, actor: int) -> int:\n        return self._machine(actor)._hits_per_shot()\n\n    def _shot_interval(self, st: _RapidActorState) -> float:\n        machine = self._machine(st.actor)\n        mode = str(self.squad.members[st.actor].weapon.get("fire_mode") or "auto")\n        if mode == "auto":\n            return 1.0 / machine._fixed_rate()\n''',
    '''        return (\n            float(weapon.get("_weapon_change_effect_id", -1)),\n            self.effects.sum_stat(actor, "reload_speed_pct", now=now),\n            warmup_speed,\n            float(self._full_ammo(actor, now)),\n        )\n\n    def _hits_per_shot(self, actor: int, now: float | None = None) -> int:\n        when = self._states[actor].phase_end if now is None and actor in self._states else float(now or 0.0)\n        weapon = self._weapon(actor, when)\n        return max(1, int(weapon.get("pellets") or 1) * int(weapon.get("muzzles") or 1))\n\n    def _shot_interval(self, st: _RapidActorState) -> float:\n        machine = self._machine(st.actor)\n        weapon = self._weapon(st.actor, st.phase_end)\n        mode = str(weapon.get("fire_mode") or "auto")\n        if mode == "auto":\n            base_rate = max(float(self.squad.members[st.actor].weapon.get("fire_rate") or 1.0), 1e-9)\n            static_factor = machine._fixed_rate() / base_rate\n            rate = min(60.0, max(0.01, float(weapon.get("fire_rate") or base_rate) * static_factor))\n            return 1.0 / rate\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''        cap = float(self.squad.members[st.actor].weapon.get("warmup_bullets") or 1.0)\n''',
    '''        cap = float(weapon.get("warmup_bullets") or 1.0)\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''    def _after_shot(self, st: _RapidActorState, shot_time: float) -> None:\n        hits = self._hits_per_shot(st.actor)\n        inter = self._shot_interval(st)\n        st.ammo -= 1\n        st.hit_count += 1\n        st.pellet_count += hits\n        st.last_shot = shot_time\n        st.last_inter = inter\n        st.phase = "reload_wait" if st.ammo <= 0 else "firing"\n        st.phase_end = shot_time + inter\n''',
    '''    def _after_shot(self, st: _RapidActorState, shot_time: float) -> None:\n        weapon = self._weapon(st.actor, shot_time)\n        hits = self._hits_per_shot(st.actor, shot_time)\n        inter = self._shot_interval(st)\n        infinite = int(weapon.get("max_ammo", 0)) < 0\n        if not infinite:\n            st.ammo -= 1\n        st.hit_count += 1\n        st.pellet_count += hits\n        st.last_shot = shot_time\n        st.last_inter = inter\n        st.phase = "firing" if infinite or st.ammo > 0 else "reload_wait"\n        if weapon.get("_moris_frame_observed"):\n            st.fire_deadline = max(float(st.fire_deadline), float(shot_time)) + inter\n            st.phase_end = moris_observed_tick(st.fire_deadline, horizon=self.duration)\n        else:\n            st.phase_end = shot_time + inter\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''        actor = st.actor\n        weapon = self.squad.members[actor].weapon\n        if st.phase == "reload_wait":\n''',
    '''        actor = st.actor\n        weapon = self._weapon(actor, transition_time)\n        if st.phase == "reload_wait":\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''            full = self._full_ammo(actor, now)\n            st = _RapidActorState(\n                actor=actor,\n                ammo=full,\n                phase="firing",\n                phase_end=float(now),\n                signature=self._signature(actor, now),\n            )\n''',
    '''            full = self._full_ammo(actor, now)\n            st = _RapidActorState(\n                actor=actor,\n                ammo=full,\n                phase="firing",\n                phase_end=float(now),\n                fire_deadline=float(now),\n                signature=self._signature(actor, now),\n            )\n''',
)
patch(
    "fast_engine/engine/dynamic_reload.py",
    '''            signature = self._signature(actor, now)\n            full = int(signature[2])\n            clamped = st.phase != "reloading" and st.ammo > full\n            if clamped:\n                st.ammo = full\n            if clamped or signature != st.signature:\n                st.signature = signature\n                self._invalidate(st)\n''',
    '''            signature = self._signature(actor, now)\n            full = int(signature[3])\n            weapon_changed = st.signature is not None and signature[0] != st.signature[0]\n            if weapon_changed:\n                # Moris starts/ends a weapon-change session with fresh physical\n                # weapon state, but BuffManager hit_count is whole-combat and is\n                # deliberately preserved.\n                st.ammo = full\n                st.phase = "firing"\n                st.phase_end = float(now)\n                st.fire_deadline = float(now)\n                st.warmup = 0.0\n                st.last_inter = 0.0\n            clamped = st.phase != "reloading" and st.ammo > full\n            if clamped:\n                st.ammo = full\n            if weapon_changed or clamped or signature != st.signature:\n                st.signature = signature\n                self._invalidate(st)\n''',
)

# Rapid cadence's ordinary non-squad-ammo path should reuse the dynamic-aware
# base transition implementation.
patch(
    "fast_engine/engine/dynamic_rapid.py",
    '''        actor = st.actor\n        weapon = self.squad.members[actor].weapon\n        if not self._squad_ammo_thresholds:\n            if st.phase == "reload_wait":\n                factor = self._reload_factor(actor, transition_time)\n                st.phase = "reloading"\n                st.phase_end = transition_time + (\n                    float(weapon.get("reload_start_delay", 0.0))\n                    + float(weapon.get("reload_time", 0.0))\n                ) * factor\n                return\n            if st.phase == "reloading":\n                st.ammo = self._full_ammo(actor, transition_time)\n                factor = self._reload_factor(actor, transition_time)\n                st.phase = "firing"\n                st.phase_end = transition_time + float(\n                    weapon.get("post_reload_delay", 0.0)\n                ) * factor\n                return\n            raise RuntimeError(f"unexpected rapid cadence phase: {st.phase!r}")\n\n        # Empty-magazine reload''',
    '''        actor = st.actor\n        weapon = self._weapon(actor, transition_time)\n        if not self._squad_ammo_thresholds:\n            return super()._finish_nonshot_phase(st, transition_time)\n\n        # Empty-magazine reload''',
)

# Parent effective_weapon is the single live weapon source for charge and rapid.
patch(
    "fast_engine/engine/dynamic_weapon.py",
    '''        self._rapid_reload = DynamicRapidCadenceRuntime(\n            squad,\n            effects,\n            state,\n            scheduler,\n            duration=duration,\n            effect_filter=effect_filter,\n        )\n\n        actors = set(self.actors)\n''',
    '''        self._rapid_reload = DynamicRapidCadenceRuntime(\n            squad,\n            effects,\n            state,\n            scheduler,\n            duration=duration,\n            effect_filter=effect_filter,\n        )\n        self._rapid_reload.attach_effective_weapon(self.effective_weapon)\n\n        actors = set(self.actors)\n''',
)

# 3) Dispatcher: exact finite self SMG infinite-ammo burst-cast producer.
patch(
    "fast_engine/engine/dispatcher.py",
    '''    def _temporary_self_charge_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n''',
    '''    @classmethod\n    def _temporary_self_rapid_weapon_change_shape_supported(cls, effect: "CompiledEffect") -> bool:\n        params = effect.parameters\n        allowed = {"favorite", "weapon_type", "damage_coeff", "max_ammo"}\n        return (\n            effect.capability.disposition is CapabilityDisposition.PLANNED\n            and effect.effect_type == "weapon_change"\n            and effect.target_spec.mode is TargetMode.SELF\n            and effect.target_spec.runtime_supported\n            and bool(effect.name)\n            and effect.duration is not None and float(effect.duration) > 0.0\n            and effect.max_stack in (None, 1, 1.0)\n            and effect.max_trigger is None\n            and effect.tick_interval is None\n            and not effect.condition_rules\n            and set(params).issubset(allowed)\n            and {"weapon_type", "damage_coeff", "max_ammo"}.issubset(params)\n            and params.get("weapon_type") == "SMG"\n            and params.get("max_ammo") == -1\n            and isinstance(params.get("damage_coeff"), (int, float))\n            and float(params.get("damage_coeff")) > 0.0\n            and len(effect.triggers) == 1\n            and effect.triggers[0].mode is TriggerMode.EVENT\n            and effect.triggers[0].event_key == "burst_cast"\n        )\n\n    def _temporary_self_rapid_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n        if not self._temporary_self_rapid_weapon_change_shape_supported(effect):\n            return False\n        member = self.squad.members[effect.actor]\n        return (\n            str(member.weapon.get("fire_mode") or "") == "auto"\n            and not member.weapon.get("control")\n            and not member.weapon.get("is_clip")\n            and not member.weapon.get("cover_during_delay")\n        )\n\n    def _temporary_self_charge_weapon_change_runtime_supported(\n        self, effect: "CompiledEffect"\n    ) -> bool:\n''',
)
patch(
    "fast_engine/engine/dispatcher.py",
    '''        if self._temporary_self_charge_weapon_change_runtime_supported(effect):\n            return True\n''',
    '''        if (\n            self._temporary_self_charge_weapon_change_runtime_supported(effect)\n            or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n        ):\n            return True\n''',
)
patch(
    "fast_engine/engine/dispatcher.py",
    '''        elif effect.effect_type == "weapon_change":\n            if (\n                not self._temporary_self_charge_weapon_change_runtime_supported(effect)\n                or tuple(targets) != (effect.actor,)\n            ):\n                return False\n            self.effects.activate_group(effect, targets, now, self.scheduler)\n''',
    '''        elif effect.effect_type == "weapon_change":\n            if (\n                not (\n                    self._temporary_self_charge_weapon_change_runtime_supported(effect)\n                    or self._temporary_self_rapid_weapon_change_runtime_supported(effect)\n                )\n                or tuple(targets) != (effect.actor,)\n            ):\n                return False\n            self.effects.activate_group(effect, targets, now, self.scheduler)\n''',
)

# 4) Score-time graph proof and rapid ownership.
patch(
    "fast_engine/engine/score.py",
    '''def _charge_actor_score_safe(squad: CompiledSquad, actor: int) -> bool:\n''',
    '''def _temporary_self_rapid_weapon_change_score_supported(\n    squad: CompiledSquad, effect\n) -> bool:\n    if not TriggerDispatcher._temporary_self_rapid_weapon_change_shape_supported(effect):\n        return False\n    actor = effect.actor\n    member = squad.members[actor]\n    if not (\n        str(member.weapon.get("fire_mode") or "") == "auto"\n        and not member.weapon.get("control")\n        and not member.weapon.get("is_clip")\n        and not member.weapon.get("cover_during_delay")\n        and effect.name\n    ):\n        return False\n    related = tuple(\n        other for other in squad.effects\n        if other.effect_type == "weapon_change"\n        and actor in _possible_ally_targets(squad, other)\n    )\n    if len(related) != 1 or related[0].effect_id != effect.effect_id:\n        return False\n\n    name = effect.name\n    consumers = []\n    for other in squad.effects:\n        if other.effect_id == effect.effect_id:\n            continue\n        references = (\n            any(rule.key == name for rule in other.condition_rules)\n            or any((rule.event_key or "") == f"event:state_end:{name}" for rule in other.triggers)\n            or other.parameters.get("target_effect") == name\n        )\n        if references:\n            consumers.append(other)\n    if len(consumers) != 1:\n        return False\n    consumer = consumers[0]\n    if not (\n        consumer.actor == actor\n        and consumer.effect_type == "damage"\n        and (consumer.stat or "") == "bonus_damage"\n        and consumer.target_spec.mode is TargetMode.ENEMY\n        and consumer.target_spec.runtime_supported\n        and consumer.value is not None and float(consumer.value) >= 0.0\n        and consumer.duration is None\n        and consumer.max_stack is None\n        and consumer.max_trigger is None\n        and consumer.tick_interval is None\n        and not consumer.parameters\n        and len(consumer.condition_rules) == 1\n        and consumer.condition_rules[0].mode is ConditionMode.SELF_STATE\n        and consumer.condition_rules[0].key == name\n        and len(consumer.triggers) == 1\n        and consumer.triggers[0].mode is TriggerMode.MODULO\n        and consumer.triggers[0].event_key == "hit_count"\n        and consumer.triggers[0].trigger_count_reducible\n        and int(consumer.triggers[0].threshold or 0) > 0\n    ):\n        return False\n    return True\n\n\ndef _charge_actor_score_safe(squad: CompiledSquad, actor: int) -> bool:\n''',
)
patch(
    "fast_engine/engine/score.py",
    '''    for effect in squad.effects:\n        if effect.effect_type != "weapon_change":\n            continue\n        if actor in _possible_ally_targets(squad, effect):\n            return False\n\n    if _actor_has_executable_core_count(squad, actor):\n''',
    '''    weapon_changes = tuple(\n        effect for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and actor in _possible_ally_targets(squad, effect)\n    )\n    if weapon_changes and not (\n        len(weapon_changes) == 1\n        and _temporary_self_rapid_weapon_change_score_supported(squad, weapon_changes[0])\n    ):\n        return False\n\n    if _actor_has_executable_core_count(squad, actor):\n''',
)
patch(
    "fast_engine/engine/score.py",
    '''    actors.update(\n        row.actor\n        for row in certified_stack3_self_stun_remove_lifecycles(squad)\n        if _rapid_actor_score_safe(squad, row.actor)\n    )\n    return tuple(sorted(actors))\n''',
    '''    actors.update(\n        row.actor\n        for row in certified_stack3_self_stun_remove_lifecycles(squad)\n        if _rapid_actor_score_safe(squad, row.actor)\n    )\n    actors.update(\n        effect.actor\n        for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n        and _rapid_actor_score_safe(squad, effect.actor)\n    )\n    return tuple(sorted(actors))\n''',
)
patch(
    "fast_engine/engine/score.py",
    '''    rapid=set(_dynamic_rapid_reload_score_actors(squad))\n    if rapid != set(range(len(squad.members))):\n        return False\n''',
    '''    if any(\n        effect.effect_type == "weapon_change"\n        and _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n        for effect in squad.effects\n    ):\n        return False\n    rapid=set(_dynamic_rapid_reload_score_actors(squad))\n    if rapid != set(range(len(squad.members))):\n        return False\n''',
)
patch(
    "fast_engine/engine/score.py",
    '''        if effect.effect_type == "weapon_change":\n            if not _temporary_self_charge_weapon_change_score_supported(squad, effect):\n                blockers.append(f"weapon_change:{owner}:{effect.name or 'unnamed'}")\n            continue\n''',
    '''        if effect.effect_type == "weapon_change":\n            if not (\n                _temporary_self_charge_weapon_change_score_supported(squad, effect)\n                or _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n            ):\n                blockers.append(f"weapon_change:{owner}:{effect.name or 'unnamed'}")\n            continue\n''',
)

# 5) Regression contract.
test = ROOT / "fast_engine/tests/test_damage_moran_weapon_change_lifecycle.py"
if not test.exists():
    test.write_text(r'''from __future__ import annotations

from dataclasses import replace
import unittest

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import (
    _temporary_self_rapid_weapon_change_score_supported,
    static_score_blockers,
)


MORAN_TEAMS = (
    "스쿼드4",
    "레이드_이브레이븐",
    "레이드_아니스서머메이든",
    "레이드_브리드디젤",
    "레이드_트리나홍련",
)


class MoranWeaponChangeLifecycleTest(unittest.TestCase):
    def _compiled(self, team="스쿼드4"):
        case = snapshot.SQUADS[team]
        return compile_moris_squad(spec.build_squad(list(case["members"])))

    @staticmethod
    def _producer(compiled):
        return next(
            effect for effect in compiled.effects
            if effect.effect_type == "weapon_change"
            and compiled.members[effect.actor].name == "목단"
        )

    def test_exact_public_moran_weapon_change_blockers_are_owned(self):
        for team in MORAN_TEAMS:
            with self.subTest(team=team):
                compiled = self._compiled(team)
                self.assertFalse(any(
                    blocker.startswith("weapon_change:목단:")
                    for blocker in static_score_blockers(compiled)
                ))
                effect = self._producer(compiled)
                self.assertTrue(_temporary_self_rapid_weapon_change_score_supported(compiled, effect))

    def test_effective_smg_view_and_mode_edges_preserve_global_hit_phase(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        actor = effect.actor
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=20.0, first_burst_time=3.0),
            EnemyStaticProfile(defense=31784.0, duration=20.0, core_px=0.0),
        )
        runtime.weapons._rapid_reload.attach_score_sink((), lambda *_: None) if False else None
        # Score wiring normally selects the actor. Direct lifecycle tests attach it explicitly.
        runtime.weapons.attach_score_block_sink((actor,), lambda *_: None)
        runtime.weapons.start(0.0)
        rapid = runtime.weapons._rapid_reload
        st = rapid._states[actor]
        st.hit_count = 37
        st.pellet_count = 37
        st.dispatched_hit_count = 35
        st.dispatched_pellet_count = 35

        runtime.dispatcher.dispatch(BurstSignal(3.05, "burst_cast", actor, actor))
        runtime.weapons.sync(3.05)
        changed = runtime.weapons.effective_weapon(actor, 3.05)
        self.assertEqual(changed["weapon_type"], "SMG")
        self.assertEqual(changed["fire_mode"], "auto")
        self.assertEqual(changed["fire_rate"], 24.0)
        self.assertEqual(changed["max_ammo"], -1)
        self.assertEqual(changed["damage_coeff"], 14.7)
        self.assertTrue(changed["_moris_frame_observed"])
        self.assertEqual(st.hit_count, 37)
        self.assertEqual(st.ammo, 999999)
        self.assertAlmostEqual(st.phase_end, 3.05, places=9)

        next_boundary = rapid._predict_next_boundary(actor)
        self.assertIsNotNone(next_boundary)
        when, expected = next_boundary
        self.assertEqual(expected, 40)
        self.assertAlmostEqual(when, 3.1333333333333333, places=8)

        expiry = next(
            event for event in runtime.scheduler._heap
            if abs(event.time - 13.05) < 1e-8
        )
        runtime.dispatcher.handle_expiry(expiry)
        runtime.weapons.sync(13.05)
        restored = runtime.weapons.effective_weapon(actor, 13.05)
        self.assertIs(restored, compiled.members[actor].weapon)
        self.assertEqual(st.hit_count, 37)
        self.assertEqual(st.ammo, int(compiled.members[actor].weapon["max_ammo"]))
        self.assertAlmostEqual(st.phase_end, 13.05, places=9)

    def test_shape_rejects_wider_weapon_modes(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        for params in (
            {**effect.parameters, "max_ammo": 60},
            {**effect.parameters, "weapon_type": "AR"},
            {**effect.parameters, "skill_damage": True},
            {**effect.parameters, "duration_bullets": 10},
        ):
            with self.subTest(params=params):
                self.assertFalse(
                    _temporary_self_rapid_weapon_change_score_supported(
                        compiled, replace(effect, parameters=params)
                    )
                )

    def test_dependency_graph_rejects_missing_or_mismatched_name(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        self.assertFalse(
            _temporary_self_rapid_weapon_change_score_supported(
                compiled, replace(effect, name="unreferenced weapon state")
            )
        )

    def test_other_class_changing_weapon_changes_remain_blocked(self):
        found = False
        for name, case in snapshot.SQUADS.items():
            if str(name).startswith("지그_") or "스노우 화이트" not in case["members"]:
                continue
            compiled = compile_moris_squad(spec.build_squad(list(case["members"])))
            if any(blocker.startswith("weapon_change:스노우 화이트:") for blocker in static_score_blockers(compiled)):
                found = True
                break
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")

print("Moran lifecycle implementation staged")
