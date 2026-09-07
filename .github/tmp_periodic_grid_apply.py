from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    s = p.read_text(encoding='utf-8')
    if old not in s:
        raise SystemExit(f'anchor missing in {path}: {old[:160]!r}')
    p.write_text(s.replace(old, new, 1), encoding='utf-8')

# 1) Sparse dynamic periodic cadence owner. No global frame loop: only target
# periodics receive generation-tagged reservations, and modifier changes rescale
# their remaining raw cooldown before the deadline is mapped to Moris ticks.
Path('fast_engine/engine/dynamic_periodic.py').write_text(r'''from __future__ import annotations

from dataclasses import dataclass

from .frame_lattice import moris_next_tick, moris_observed_tick
from .scheduler import EventKind, EventScheduler
from .triggers import TriggerMode

_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class DynamicPeriodicTickToken:
    effect_id: int
    rule_index: int
    generation: int


@dataclass(slots=True)
class _DynamicPeriodicState:
    effect_id: int
    rule_index: int
    actor: int
    effect_name: str
    base_interval: float
    interval: float
    next_nominal: float
    generation: int = 0


class DynamicPeriodicCadenceRuntime:
    """Sparse Moris-style every:Ns cadence with targeted interval modifiers.

    Moris rescales the *remaining* cooldown whenever the effective interval
    changes. Fast keeps one raw next-fire timestamp per affected periodic and
    only maps that boundary onto the repeated-add 60 Hz lattice. Old scheduled
    reservations are invalidated by generation rather than cancelled, so no
    global frame stream is introduced.
    """

    __slots__ = (
        'squad', 'effects', 'scheduler', 'horizon', '_states', '_owned',
    )

    def __init__(
        self,
        squad,
        effects,
        scheduler: EventScheduler,
        *,
        horizon: float,
        modifier_filter,
        effect_filter,
    ) -> None:
        self.squad = squad
        self.effects = effects
        self.scheduler = scheduler
        self.horizon = float(horizon)
        self._states: dict[tuple[int, int], _DynamicPeriodicState] = {}

        target_keys: set[tuple[int, str]] = set()
        for modifier in squad.effects:
            if not modifier_filter(modifier):
                continue
            if (modifier.stat or '') != 'effect_interval':
                continue
            target_name = modifier.parameters.get('target_effect')
            if not isinstance(target_name, str) or not target_name:
                continue
            target_keys.add((modifier.actor, target_name))

        for actor, target_name in target_keys:
            candidates = [
                effect for effect in squad.effects
                if effect.actor == actor
                and effect.name == target_name
                and effect_filter(effect)
            ]
            if len(candidates) != 1:
                continue
            effect = candidates[0]
            periodic_rules = [
                (index, rule)
                for index, rule in enumerate(effect.triggers)
                if rule.mode is TriggerMode.PERIODIC
                and rule.interval is not None
                and float(rule.interval) > 0.0
            ]
            if len(periodic_rules) != 1:
                continue
            rule_index, rule = periodic_rules[0]
            base = float(rule.interval)
            key = (effect.effect_id, rule_index)
            self._states[key] = _DynamicPeriodicState(
                effect.effect_id,
                rule_index,
                actor,
                effect.name,
                base,
                base,
                base,
            )

        self._owned = frozenset(self._states)

    @property
    def owned(self) -> frozenset[tuple[int, int]]:
        return self._owned

    def owns(self, effect_id: int, rule_index: int) -> bool:
        return (int(effect_id), int(rule_index)) in self._owned

    def _effective_interval(self, state: _DynamicPeriodicState, now: float) -> float:
        flat = self.effects.sum_targeted_stat(
            state.actor,
            'effect_interval',
            state.effect_name,
            now=now,
        )
        interval = max(0.0, state.base_interval + flat)
        return max(interval, state.base_interval * 0.05)

    def _reserve(self, state: _DynamicPeriodicState) -> None:
        if state.next_nominal >= self.horizon:
            return
        observed = moris_observed_tick(state.next_nominal, horizon=self.horizon)
        # If a phase-later event changed cadence after BuffManager's periodic
        # phase at the same Moris frame, the newly-due periodic cannot run
        # retroactively. Moris sees it on the next outer-loop tick.
        if observed <= self.scheduler.now + _EPS:
            observed = moris_next_tick(self.scheduler.now, horizon=self.horizon)
        if observed >= self.horizon:
            return
        self.scheduler.schedule(
            observed,
            EventKind.PERIODIC_TICK,
            actor=state.actor,
            payload=DynamicPeriodicTickToken(
                state.effect_id,
                state.rule_index,
                state.generation,
            ),
        )

    def start(self) -> None:
        for state in self._states.values():
            state.interval = self._effective_interval(state, 0.0)
            state.next_nominal = state.interval
            self._reserve(state)

    def sync(self, now: float) -> None:
        """Rescale remaining cooldown after an interval state transition."""
        now = float(now)
        for state in self._states.values():
            new_interval = self._effective_interval(state, now)
            old_interval = state.interval
            if abs(new_interval - old_interval) <= _EPS:
                continue
            remaining = max(0.0, state.next_nominal - now)
            state.next_nominal = now + remaining * (new_interval / old_interval)
            state.interval = new_interval
            state.generation += 1
            self._reserve(state)

    def accepts(self, token: DynamicPeriodicTickToken) -> bool:
        state = self._states.get((token.effect_id, token.rule_index))
        return state is not None and state.generation == token.generation

    def after_tick(self, token: DynamicPeriodicTickToken) -> None:
        state = self._states[(token.effect_id, token.rule_index)]
        state.next_nominal += state.interval
        state.generation += 1
        self._reserve(state)
''', encoding='utf-8')

# 2) ActiveEffectStore targeted stat lookup. This mirrors sum_stat but filters
# target_effect so unrelated every:Ns skills are never coupled.
replace_once(
    'fast_engine/engine/effects.py',
'''    def has_stat(self, target: int, stat: str, *, now: float) -> bool:\n        self._materialize_pending_stat(stat, now)\n        return bool(self._active_keys(self._by_target_stat, target, stat, now))\n\n    def sum_stat(self, target: int, stat: str, *, now: float) -> float:\n''',
'''    def has_stat(self, target: int, stat: str, *, now: float) -> bool:\n        self._materialize_pending_stat(stat, now)\n        return bool(self._active_keys(self._by_target_stat, target, stat, now))\n\n    def sum_targeted_stat(\n        self,\n        target: int,\n        stat: str,\n        target_effect: str,\n        *,\n        now: float,\n    ) -> float:\n        """Sum one stat only from effects explicitly naming ``target_effect``."""\n        self._materialize_pending_stat(stat, now)\n        total = 0.0\n        for key in self._active_keys(self._by_target_stat, target, stat, now):\n            active = self._active[key]\n            effect = self._effects[active.effect_id]\n            if effect.parameters.get("target_effect") != target_effect:\n                continue\n            total += float(effect.value or 0.0) * self.effect_value_scale(\n                effect, active, now=now\n            )\n        return total\n\n    def sum_stat(self, target: int, stat: str, *, now: float) -> float:\n''')

# 3) Narrow executable modifier shape. Runtime owns only finite self burst-cast
# target_effect interval buffs; score proof below owns the target relationship.
replace_once(
    'fast_engine/engine/dispatcher.py',
'''    @staticmethod\n    def is_executable_effect(effect: "CompiledEffect") -> bool:\n        stat = effect.stat or ""\n''',
'''    @staticmethod\n    def _finite_self_effect_interval_shape_supported(effect: "CompiledEffect") -> bool:\n        target_effect = effect.parameters.get("target_effect")\n        return (\n            effect.effect_type == "buff"\n            and (effect.stat or "") == "effect_interval"\n            and effect.target_spec.mode is TargetMode.SELF\n            and effect.value is not None\n            and effect.duration is not None\n            and float(effect.duration) > 0.0\n            and effect.max_stack in (None, 1, 1.0)\n            and effect.tick_interval is None\n            and isinstance(target_effect, str)\n            and bool(target_effect)\n            and set(effect.parameters) == {"target_effect"}\n            and not effect.condition_rules\n            and len(effect.triggers) == 1\n            and effect.triggers[0].mode is TriggerMode.EVENT\n            and effect.triggers[0].event_key == "burst_cast"\n        )\n\n    @staticmethod\n    def is_executable_effect(effect: "CompiledEffect") -> bool:\n        stat = effect.stat or ""\n        if TriggerDispatcher._finite_self_effect_interval_shape_supported(effect):\n            return True\n''')

# 4) BurstRuntime wires dynamic-periodic reservations alongside existing fixed
# periodic compression and syncs only after relevant state transitions.
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''from .dynamic_weapon import MultiSignalChargeCadenceRuntime\n''',
'''from .dynamic_weapon import MultiSignalChargeCadenceRuntime\nfrom .dynamic_periodic import DynamicPeriodicCadenceRuntime, DynamicPeriodicTickToken\n''')
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''        "dispatcher", "weapons", "damage_sink",\n''',
'''        "dispatcher", "weapons", "periodics", "damage_sink",\n''')
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''        self.weapons = MultiSignalChargeCadenceRuntime(\n''',
'''        self.periodics = DynamicPeriodicCadenceRuntime(\n            squad,\n            self.dispatcher.effects,\n            self.scheduler,\n            horizon=policy.duration,\n            modifier_filter=self.dispatcher.is_runtime_executable_effect,\n            effect_filter=self.dispatcher.can_activate_effect,\n        )\n        self.weapons = MultiSignalChargeCadenceRuntime(\n''')
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''            rule = effect.triggers[indexed.rule_index]\n            if rule.mode is not TriggerMode.PERIODIC or rule.interval is None:\n''',
'''            rule = effect.triggers[indexed.rule_index]\n            if self.periodics.owns(effect.effect_id, indexed.rule_index):\n                continue\n            if rule.mode is not TriggerMode.PERIODIC or rule.interval is None:\n''')
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''        self._schedule_static_last_bullets(horizon, dynamic_actors)\n        self._schedule_initial_periodics(horizon)\n''',
'''        self._schedule_static_last_bullets(horizon, dynamic_actors)\n        self.periodics.start()\n        self._schedule_initial_periodics(horizon)\n''')
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''            if event.kind is EventKind.STATE_EXPIRE:\n                self.dispatcher.handle_expiry(event)\n                self.weapons.sync(event.time)\n''',
'''            if event.kind is EventKind.STATE_EXPIRE:\n                self.dispatcher.handle_expiry(event)\n                self.periodics.sync(event.time)\n                self.weapons.sync(event.time)\n''')
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''            if event.kind is EventKind.PERIODIC_TICK:\n                token = event.payload\n                if not isinstance(token, PeriodicTickToken):\n                    score_end_of_time(event.time)\n                    continue\n                self.dispatcher.dispatch_periodic(\n                    token.effect_id,\n                    token.rule_index,\n                    time=event.time,\n                    context=SignalContext(),\n                )\n                next_nominal = token.nominal_time + token.interval\n                if next_nominal < horizon:\n                    next_t = moris_observed_tick(next_nominal, horizon=horizon)\n                    if next_t < horizon:\n                        self.scheduler.schedule(\n                            next_t,\n                            EventKind.PERIODIC_TICK,\n                            actor=event.actor,\n                            payload=PeriodicTickToken(\n                                token.effect_id, token.rule_index, token.interval, next_nominal\n                            ),\n                        )\n                self.weapons.sync(event.time)\n                score_end_of_time(event.time)\n                continue\n''',
'''            if event.kind is EventKind.PERIODIC_TICK:\n                token = event.payload\n                if isinstance(token, DynamicPeriodicTickToken):\n                    if not self.periodics.accepts(token):\n                        score_end_of_time(event.time)\n                        continue\n                    self.dispatcher.dispatch_periodic(\n                        token.effect_id,\n                        token.rule_index,\n                        time=event.time,\n                        context=SignalContext(),\n                    )\n                    self.periodics.after_tick(token)\n                elif isinstance(token, PeriodicTickToken):\n                    self.dispatcher.dispatch_periodic(\n                        token.effect_id,\n                        token.rule_index,\n                        time=event.time,\n                        context=SignalContext(),\n                    )\n                    next_nominal = token.nominal_time + token.interval\n                    if next_nominal < horizon:\n                        next_t = moris_observed_tick(next_nominal, horizon=horizon)\n                        if next_t < horizon:\n                            self.scheduler.schedule(\n                                next_t,\n                                EventKind.PERIODIC_TICK,\n                                actor=event.actor,\n                                payload=PeriodicTickToken(\n                                    token.effect_id, token.rule_index, token.interval, next_nominal\n                                ),\n                            )\n                else:\n                    score_end_of_time(event.time)\n                    continue\n                self.weapons.sync(event.time)\n                score_end_of_time(event.time)\n                continue\n''')
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''            for signal in signals:\n                if signal.event_key == "burst_cast" and signal.source_actor is not None:\n                    casts.append(\n                        (signal.time, signal.source_actor, signal.stage or "")\n                    )\n                self.dispatcher.dispatch(signal, context=SignalContext())\n            if event.kind is EventKind.FULL_BURST_START:\n''',
'''            for signal in signals:\n                if signal.event_key == "burst_cast" and signal.source_actor is not None:\n                    casts.append(\n                        (signal.time, signal.source_actor, signal.stage or "")\n                    )\n                self.dispatcher.dispatch(signal, context=SignalContext())\n            self.periodics.sync(event.time)\n            if event.kind is EventKind.FULL_BURST_START:\n''')

# 5) Score proof: only skip the periodic-grid blocker when this exact modifier
# names one same-actor, score-supported periodic damage effect with one fixed base
# interval. Other periodic invalidators remain fail-closed.
replace_once(
    'fast_engine/engine/score.py',
'''def static_normal_score_blockers(squad: CompiledSquad) -> tuple[str, ...]:\n''',
'''def _finite_targeted_effect_interval_score_supported(\n    squad: CompiledSquad, effect, damage_sink\n) -> bool:\n    if not TriggerDispatcher._finite_self_effect_interval_shape_supported(effect):\n        return False\n    target_name = effect.parameters.get("target_effect")\n    targets = [\n        candidate for candidate in squad.effects\n        if candidate.actor == effect.actor and candidate.name == target_name\n    ]\n    if len(targets) != 1:\n        return False\n    target = targets[0]\n    periodic = [\n        rule for rule in target.triggers\n        if rule.mode is TriggerMode.PERIODIC\n        and rule.interval is not None\n        and float(rule.interval) > 0.0\n    ]\n    return (\n        len(periodic) == 1\n        and target.effect_type == "damage"\n        and damage_sink.supports(target)\n    )\n\n\ndef static_normal_score_blockers(squad: CompiledSquad) -> tuple[str, ...]:\n''')
replace_once(
    'fast_engine/engine/score.py',
'''        if has_score_periodic and stat in _PERIODIC_GRID_INVALIDATORS:\n            blockers.append(f"periodic_grid:{label}")\n''',
'''        if has_score_periodic and stat in _PERIODIC_GRID_INVALIDATORS:\n            if (\n                stat == "effect_interval"\n                and _finite_targeted_effect_interval_score_supported(\n                    squad, effect, damage_sink\n                )\n            ):\n                continue\n            blockers.append(f"periodic_grid:{label}")\n''')

# 6) Focused public regression including Moris oracle activation frames.
Path('fast_engine/tests/test_damage_effect_interval_periodic_grid.py').write_text(r'''from __future__ import annotations

import unittest
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers


TEAM = '레이드_헬름아쿠아스노우'


def _compiled():
    moris = spec.build_squad(list(snapshot.SQUADS[TEAM]['members']))
    return moris, compile_moris_squad(moris)


class EffectIntervalPeriodicGridTests(unittest.TestCase):
    def test_public_modifier_is_exact_owned_shape(self):
        _moris, squad = _compiled()
        ada = next(i for i, member in enumerate(squad.members) if member.name == '에이다')
        modifier = next(
            effect for effect in squad.members[ada].effects
            if (effect.stat or '') == 'effect_interval'
        )
        self.assertTrue(
            TriggerDispatcher._finite_self_effect_interval_shape_supported(modifier)
        )
        blockers = static_score_blockers(squad)
        self.assertNotIn(
            'periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval',
            blockers,
        )
        self.assertIn('normal_state:미란다:웨이크업! 4:rank_target_timing', blockers)

    def test_public_fast_grenade_activation_frames_match_moris(self):
        moris, squad = _compiled()
        ada = next(i for i, member in enumerate(squad.members) if member.name == '에이다')
        grenade = next(
            effect for effect in squad.members[ada].effects
            if effect.name == '섬광 수류탄 투척'
        )
        duration = 35.0
        config = {'duration': duration, 'rng_mode': 'expected'}
        enemy = dict(DEFAULT_ENEMY)
        policy = compile_burst_policy(moris, squad, config)
        enemy_profile = EnemyStaticProfile(
            defense=float(enemy.get('def', 31784.0)),
            element=enemy.get('code'),
            core_px=float(enemy.get('core_px', 0.0) or 0.0),
            duration=duration,
        )

        fast: list[float] = []
        sink = SimpleDamageScoreSink(squad, enemy_profile)
        original_fast = TriggerDispatcher.dispatch_periodic

        def traced_fast(dispatcher, effect_id, rule_index, *, time, context):
            result = original_fast(
                dispatcher, effect_id, rule_index, time=time, context=context
            )
            if effect_id == grenade.effect_id and effect_id in result.activated_effect_ids:
                fast.append(float(time))
            return result

        with patch.object(TriggerDispatcher, 'dispatch_periodic', new=traced_fast):
            BurstRuntime(
                squad, policy, enemy_profile, damage_sink=sink
            ).run(duration=duration)

        moris_times: list[float] = []
        original_activate = BuffManager._activate

        def traced_moris(self, eff, caster, t, suppress_event=False):
            if caster == '에이다' and eff.get('name') == '섬광 수류탄 투척':
                moris_times.append(float(t))
            return original_activate(
                self, eff, caster, t, suppress_event=suppress_event
            )

        with patch.object(BuffManager, '_activate', new=traced_moris):
            simulate(moris, config=config, enemy=enemy, verbose=False)

        self.assertEqual(len(fast), len(moris_times))
        for fast_time, moris_time in zip(fast, moris_times):
            self.assertAlmostEqual(fast_time, moris_time, places=9)
        self.assertAlmostEqual(fast[5], 21.783333333333378, places=9)
        self.assertAlmostEqual(fast[6], 22.78333333333332, places=9)

    def test_neighboring_interval_shapes_remain_unowned(self):
        _moris, squad = _compiled()
        ada = next(i for i, member in enumerate(squad.members) if member.name == '에이다')
        modifier = next(
            effect for effect in squad.members[ada].effects
            if (effect.stat or '') == 'effect_interval'
        )
        from dataclasses import replace

        for changed in (
            replace(modifier, target_spec=replace(modifier.target_spec, mode=__import__('fast_engine.engine.targets', fromlist=['TargetMode']).TargetMode.ALL_ALLIES)),
            replace(modifier, duration=None),
            replace(modifier, parameters={}),
            replace(modifier, max_stack=2.0),
        ):
            with self.subTest(changed=changed):
                self.assertFalse(
                    TriggerDispatcher._finite_self_effect_interval_shape_supported(changed)
                )


if __name__ == '__main__':
    unittest.main()
''', encoding='utf-8')

print('staged targeted effect_interval periodic-grid semantics + focused regression')
