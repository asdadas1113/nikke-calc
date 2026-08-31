from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .conditions import ConditionEvaluator, SignalContext
from .effects import ActiveEffectStore
from .state import ENEMY, StateStore
from .targets import TargetResolver
from .triggers import TriggerMode

if TYPE_CHECKING:
    from .burst import BurstMachine, BurstSignal
    from .model import CompiledEffect, CompiledSquad, EnemyStaticProfile
    from .scheduler import EventScheduler


@dataclass(frozen=True, slots=True)
class DispatchResult:
    activated_effect_ids: tuple[int, ...]
    skipped_unsupported: tuple[int, ...] = ()


class TriggerDispatcher:
    """Fast effect dispatcher over precompiled actor-scoped trigger buckets.

    It deliberately executes only a small certified stat surface for now. Every
    other parsed effect remains present in IR but is skipped, so adding the
    scheduler cannot accidentally claim broad combat coverage.
    """

    __slots__ = (
        "squad", "state", "enemy", "burst", "scheduler", "effects", "targets",
        "conditions", "_effect_table", "_event_counts", "_conditional_counts",
        "_activation_counts",
    )

    _EXECUTABLE_STATS = frozenset({
        "burst_cooldown_reduce",
        "burst_cooldown",
        "fullburst_duration",
    })

    def __init__(
        self,
        squad: "CompiledSquad",
        state: StateStore,
        enemy: "EnemyStaticProfile",
        burst: "BurstMachine",
        scheduler: "EventScheduler",
    ) -> None:
        self.squad = squad
        self.state = state
        self.enemy = enemy
        self.burst = burst
        self.scheduler = scheduler
        self.effects = ActiveEffectStore(squad, state)
        self.targets = TargetResolver(squad, state, self.effects, burst)
        self.conditions = ConditionEvaluator(squad, state, self.effects, enemy, burst)
        self._effect_table = tuple(squad.effects)
        self._event_counts: dict[tuple[int, str], int] = defaultdict(int)
        self._conditional_counts: dict[tuple[int, str], tuple[int, int]] = {}
        self._activation_counts: dict[int, int] = defaultdict(int)

    @staticmethod
    def is_executable_effect(effect: "CompiledEffect") -> bool:
        stat = effect.stat or ""
        return stat in TriggerDispatcher._EXECUTABLE_STATS or stat.startswith("burst_stage_override:")

    # Backward-compatible internal spelling while call sites migrate.
    _is_executable = is_executable_effect

    def _rule_matches(
        self,
        effect: "CompiledEffect",
        rule_index: int,
        *,
        event_key: str,
        event_count: int,
        context: SignalContext,
        now: float,
    ) -> bool:
        rule = effect.triggers[rule_index]
        if rule.mode is TriggerMode.EVENT:
            return True
        if rule.mode is TriggerMode.AT_LEAST:
            return event_count >= int(rule.threshold or 0)
        if rule.mode is TriggerMode.EXACT:
            return event_count == int(rule.threshold or 0)
        if rule.mode is TriggerMode.MODULO:
            n = int(rule.threshold or 0)
            return n > 0 and event_count % n == 0
        if rule.mode is TriggerMode.VALUE_AT_LEAST:
            return context.value is not None and context.value >= float(rule.threshold or 0.0)
        if rule.mode in {TriggerMode.CONDITIONAL_AT_LEAST, TriggerMode.CONDITIONAL_MODULO}:
            # Moris counts only base events whose condition passes, and multiple
            # effects in the same group must not double-increment the count.
            if not self.conditions.evaluate_all(
                effect.condition_rules,
                effect_id=effect.effect_id,
                owner_actor=effect.actor,
                target_actor=None,
                now=now,
                context=context,
            ):
                return False
            key = (effect.actor, rule.group or rule.raw)
            last_base, conditional = self._conditional_counts.get(key, (-1, 0))
            if last_base != event_count:
                conditional += 1
                self._conditional_counts[key] = (event_count, conditional)
            threshold = int(rule.threshold or 0)
            if rule.mode is TriggerMode.CONDITIONAL_AT_LEAST:
                return conditional >= threshold
            return threshold > 0 and conditional % threshold == 0
        return False

    def _activate(
        self, effect: "CompiledEffect", *, now: float, context: SignalContext,
        conditions_prechecked: bool = False,
    ) -> bool:
        if not self._is_executable(effect):
            return False
        if effect.max_trigger is not None and self._activation_counts[effect.effect_id] >= effect.max_trigger:
            return False

        named_target = effect.target_spec.count if effect.target_spec.mode.value == "named_actor" else None
        if not conditions_prechecked and not self.conditions.evaluate_all(
            effect.condition_rules,
            effect_id=effect.effect_id,
            owner_actor=effect.actor,
            target_actor=named_target,
            now=now,
            context=context,
        ):
            return False

        targets = self.targets.resolve(effect.target_spec, owner_actor=effect.actor, now=now)
        stat = effect.stat or ""
        value = float(effect.value or 0.0)

        if effect.effect_type == "instant":
            if stat == "burst_cooldown_reduce":
                for target in targets:
                    if target != ENEMY:
                        self.burst.adjust_cooldown(target, value, now, self.scheduler)
            else:
                return False
        elif effect.effect_type == "buff":
            for target in targets:
                self.effects.activate(effect, target, now, self.scheduler)
            if stat.startswith("burst_stage_override:"):
                suffix = stat.split(":", 1)[1]
                if suffix.startswith("reenter"):
                    self.burst.set_reenter_stage(effect.actor, suffix.removeprefix("reenter"))
                else:
                    self.burst.set_stage_override(effect.actor, suffix)
        else:
            return False

        self._activation_counts[effect.effect_id] += 1
        return True

    def dispatch(self, signal: "BurstSignal", *, context: SignalContext = SignalContext()) -> DispatchResult:
        owner = signal.owner_actor
        event_key = signal.event_key
        counter_key = (owner, event_key)
        self._event_counts[counter_key] += int(getattr(signal, "count_increment", 1))
        event_count = self._event_counts[counter_key]

        activated: list[int] = []
        skipped: list[int] = []
        seen_effects: set[int] = set()
        for indexed in self.squad.trigger_index.for_actor_event(owner, event_key):
            effect = self._effect_table[indexed.effect_id]
            if effect.effect_id in seen_effects:
                continue
            if not self._rule_matches(effect, indexed.rule_index, event_key=event_key,
                                      event_count=event_count, context=context, now=signal.time):
                continue
            # Moris stops after the first matching timing for one effect.
            seen_effects.add(effect.effect_id)
            if self._is_executable(effect):
                if self._activate(
                    effect, now=signal.time, context=context,
                    conditions_prechecked=effect.triggers[indexed.rule_index].mode in {
                        TriggerMode.CONDITIONAL_AT_LEAST, TriggerMode.CONDITIONAL_MODULO
                    },
                ):
                    activated.append(effect.effect_id)
            else:
                skipped.append(effect.effect_id)
        return DispatchResult(tuple(activated), tuple(skipped))

    def burst_cooldown_buff(self, actor: int, now: float) -> float:
        return max(0.0, self.effects.sum_stat(actor, "burst_cooldown", now=now))

    def full_burst_extension(self, now: float, b3_actor: int | None) -> float:
        seen_casters: set[int] = set()
        total = 0.0
        for effect, active in self.effects.iter_stat("fullburst_duration", now=now):
            caster = effect.actor
            if caster in seen_casters:
                continue
            # Match Moris: a burst_cast-owned duration applies only when that
            # caster is this cycle's B3 user.
            if any(rule.raw == "burst_cast" for rule in effect.triggers) and caster != b3_actor:
                continue
            total += float(effect.value or 0.0) * active.stacks
            seen_casters.add(caster)
        return total

    def handle_expiry(self, event) -> None:
        expired = self.effects.handle_expiry(event)
        if expired is None:
            return
        stat = expired.stat or ""
        if stat.startswith("burst_stage_override:"):
            # Recompute both lanes from surviving overrides for this caster.
            stage = None
            reenter = None
            for effect, _active in self.effects.iter_stat_prefix("burst_stage_override:", now=event.time):
                if effect.actor != expired.actor:
                    continue
                suffix = (effect.stat or "").split(":", 1)[1]
                if suffix.startswith("reenter"):
                    reenter = suffix.removeprefix("reenter")
                else:
                    stage = suffix
            self.burst.set_stage_override(expired.actor, stage)
            self.burst.set_reenter_stage(expired.actor, reenter)
