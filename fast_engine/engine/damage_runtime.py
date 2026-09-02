from __future__ import annotations

from dataclasses import dataclass
from math import inf, nextafter
from typing import TYPE_CHECKING

from .conditions import ConditionMode, SignalContext
from .core_events import is_static_expected_core_count_rule
from .damage_events import (
    DamageEventSpec,
    FixedDotSpec,
    StackCountDamageSpec,
    StackScaledDotSpec,
    compile_fixed_dot_damage_event,
    compile_pending_b3_bonus_damage_event,
    compile_simple_damage_event,
    compile_stack_count_damage_event,
    compile_stack_scaled_dot_damage_event,
    expected_damage_event,
)
from .damage_state import DamageTermResolver
from .scheduler import EventKind, ScheduledEvent
from .state import ENEMY
from .targets import TargetMode
from .triggers import TriggerMode

if TYPE_CHECKING:
    from .burst_runtime import BurstRuntime
    from .model import CompiledEffect, CompiledSquad, EnemyStaticProfile


_SAFE_EVENT_KEYS = frozenset({
    "battle_start",
    "burst_cast",
    "full_burst_start",
    "full_burst_end",
    "event:ally_burst_cast",
    "hit_count",
    "full_charge_hit",
    "core_hit",
    "pellet_hit",
    "burst_enter:1",
    "burst_enter:2",
    "burst_enter:3",
    "squad_burst_cast:1",
    "squad_burst_cast:2",
    "squad_burst_cast:3",
})
_STACK_COUNT_SAFE_CONDITIONS = frozenset({
    ConditionMode.DURING_FULL_BURST,
    ConditionMode.NOT_DURING_FULL_BURST,
    ConditionMode.BURST_CASTED,
    ConditionMode.BURST_NOT_CASTED,
    ConditionMode.GAUGE_AT_LEAST,
    ConditionMode.GAUGE_BELOW,
    ConditionMode.GAUGE_EQUAL,
    ConditionMode.GAUGE_MOD,
    ConditionMode.SELF_STACK_AT_LEAST,
})
_PATTERNLESS_UNREACHABLE_STATE_EVENTS = frozenset({
    "enemy_death",
    "received_hit",
    "event:self_down",
})
_DOT_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class DotTickToken:
    effect_id: int
    generation: int
    expires_at: float


class SimpleDamageScoreSink:
    """Score the currently certified event-driven skill-damage subset.

    Fixed immediate damage, delayed B3 damage and fixed DoTs keep their existing
    compressed paths. Dynamic direct ``stack_count`` damage is gauge-only. The
    observable DoT slice mirrors Moris' named-state semantics: scaling_ref is
    captured into the DoT's own stack at activation, stack operations mutate that
    state, and named removal invalidates its future timer reservations.
    """

    __slots__ = (
        "squad", "enemy", "specs", "pending_specs", "dot_specs", "stack_specs",
        "stateful_dot_specs", "unsupported_effect_ids", "char_total", "runtime",
        "resolver", "_pending_effect_ids", "_effect_actor", "_dot_generation",
        "_stateful_dot_names", "_weapon_hit_source_ids",
    )

    def __init__(self, squad: "CompiledSquad", enemy: "EnemyStaticProfile") -> None:
        self.squad = squad
        self.enemy = enemy
        self.specs: dict[int, DamageEventSpec] = {}
        self.pending_specs: dict[int, DamageEventSpec] = {}
        self.dot_specs: dict[int, FixedDotSpec] = {}
        self.stack_specs: dict[int, StackCountDamageSpec] = {}
        self.stateful_dot_specs: dict[int, StackScaledDotSpec] = {}
        self.unsupported_effect_ids: set[int] = set()
        self.char_total = [0.0] * len(squad.members)
        self.runtime: "BurstRuntime | None" = None
        self.resolver: DamageTermResolver | None = None
        self._pending_effect_ids: list[int] = []
        self._effect_actor = {
            effect.effect_id: effect.actor for effect in squad.effects
        }
        self._dot_generation: dict[int, int] = {}
        self._stateful_dot_names: dict[str, list[int]] = {}
        self._weapon_hit_source_ids: set[int] = set()

        downstream_keys = set(squad.trigger_index.by_event)
        scaled_names = {
            str(effect.parameters.get("target_effect"))
            for effect in squad.effects
            if (effect.stat or "") == "dmg_scale_mag_pct"
            and effect.parameters.get("target_effect")
        }

        for effect in squad.effects:
            if effect.effect_type != "damage":
                continue

            spec = compile_simple_damage_event(effect, squad.members[effect.actor])
            pending = None
            dot = None
            stack = None
            stateful_dot = None
            if spec is None:
                pending = compile_pending_b3_bonus_damage_event(
                    effect, squad.members[effect.actor]
                )
            if spec is None and pending is None:
                stack = compile_stack_count_damage_event(
                    effect, squad.members[effect.actor]
                )
            if spec is None and pending is None and stack is None:
                stateful_dot = compile_stack_scaled_dot_damage_event(
                    effect, squad.members[effect.actor]
                )
            if spec is None and pending is None and stack is None and stateful_dot is None:
                dot = compile_fixed_dot_damage_event(
                    effect, squad.members[effect.actor]
                )

            if (
                (spec is None and pending is None and dot is None and stack is None and stateful_dot is None)
                or not self._delivery_supported(effect)
            ):
                self.unsupported_effect_ids.add(effect.effect_id)
                continue
            if effect.name and (
                f"hit_count:{effect.name}" in downstream_keys
                or effect.name in scaled_names
                or (
                    f"weapon_hit:{effect.name}" in downstream_keys
                    and not self._weapon_hit_chain_shape_supported(effect)
                )
            ):
                self.unsupported_effect_ids.add(effect.effect_id)
                continue
            if effect.name and f"weapon_hit:{effect.name}" in downstream_keys:
                self._weapon_hit_source_ids.add(effect.effect_id)

            if stack is not None:
                if not self._stack_count_shape_supported(effect, stack):
                    self.unsupported_effect_ids.add(effect.effect_id)
                    continue
                self.stack_specs[effect.effect_id] = stack
            elif stateful_dot is not None:
                if not self._stateful_dot_shape_supported(effect, stateful_dot):
                    self.unsupported_effect_ids.add(effect.effect_id)
                    continue
                self.stateful_dot_specs[effect.effect_id] = stateful_dot
                self._stateful_dot_names.setdefault(effect.name, []).append(effect.effect_id)
            elif pending is not None:
                if self._has_later_same_actor_burst_cast_buff(effect):
                    self.unsupported_effect_ids.add(effect.effect_id)
                    continue
                self.pending_specs[effect.effect_id] = pending
            elif dot is not None:
                if self._dot_state_is_observed(effect):
                    self.unsupported_effect_ids.add(effect.effect_id)
                    continue
                self.dot_specs[effect.effect_id] = dot
            else:
                assert spec is not None
                self.specs[effect.effect_id] = spec

        # Observable DoTs are only safe when every reachable explicit mutator of
        # that named state belongs to the narrow state-operation slice below.
        for effect_id in tuple(self.stateful_dot_specs):
            effect = squad.effects[effect_id]
            if not self._stateful_dot_dependencies_supported(effect):
                self.stateful_dot_specs.pop(effect_id, None)
                ids = self._stateful_dot_names.get(effect.name, [])
                if effect_id in ids:
                    ids.remove(effect_id)
                self.unsupported_effect_ids.add(effect_id)

    def _has_later_same_actor_burst_cast_buff(self, effect: "CompiledEffect") -> bool:
        """Reject only later burst-cast buffs that can change pending B3 damage.

        Moris evaluates the queued B3 bonus before later same-cast buffs can alter
        that hit. Fast flushes at full-burst entry, so any later general damage
        modifier must remain fail-closed. A Moris-NOP, trigger-count control, or
        a damage-family modifier that provably does not apply to this pending hit
        cannot change its value and is safe to ignore for this ordering guard.
        """
        pending = compile_pending_b3_bonus_damage_event(
            effect, self.squad.members[effect.actor]
        )
        if pending is None:
            return True
        unrelated = {
            "trigger_count_reduce",
        }
        for other in self.squad.effects:
            if not (
                other.actor == effect.actor
                and other.actor_effect_index > effect.actor_effect_index
                and other.effect_type == "buff"
                and any(rule.raw == "burst_cast" for rule in other.triggers)
            ):
                continue
            if other.capability.disposition.value == "mirror_moris_nop":
                continue
            stat = other.stat or ""
            if stat in unrelated:
                continue
            if stat in {"projectile_attachment_dmg", "projectile_attachment_dmg_pct"}:
                if not pending.hit.is_projectile_attachment:
                    continue
            elif stat in {"projectile_explosion_dmg", "projectile_explosion_dmg_pct"}:
                if not pending.hit.is_projectile_explosion:
                    continue
            elif stat == "sequential_dmg_pct":
                if not pending.hit.is_sequential:
                    continue
            elif stat in {"dot_dmg", "dot_dmg_pct"}:
                if not pending.hit.is_dot:
                    continue
            # Any general modifier, or a family modifier matching this pending hit,
            # can change the queued damage and therefore preserves fail-closed.
            return True
        return False

    @staticmethod
    def _enemy_named_stack_marker_shape_supported(effect: "CompiledEffect") -> bool:
        return (
            effect.effect_type == "buff"
            and (effect.stat or "") == "buff_stack_add"
            and bool(effect.name)
            and effect.target_spec.mode is TargetMode.ENEMY
            and effect.value is not None
            and abs(float(effect.value) - 1.0) <= 1e-9
            and effect.duration in (None, -1.0)
            and effect.max_stack == -1
            and not effect.parameters
            and all(rule.is_runtime_supported for rule in effect.condition_rules)
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.EVENT
            and (effect.triggers[0].event_key or "").startswith("weapon_hit:")
        )

    def _weapon_hit_chain_shape_supported(self, source: "CompiledEffect") -> bool:
        if (
            source.effect_type != "damage"
            or not source.name
            or source.target_spec.mode is not TargetMode.ENEMY
            or compile_simple_damage_event(source, self.squad.members[source.actor]) is None
            or not all(rule.is_runtime_supported for rule in source.condition_rules)
        ):
            return False
        key = f"weapon_hit:{source.name}"
        consumers = [
            other for other in self.squad.effects
            if other.actor == source.actor
            and any(rule.event_key == key for rule in other.triggers)
        ]
        if not consumers:
            return False
        for consumer in consumers:
            matching = [rule for rule in consumer.triggers if rule.event_key == key]
            if not matching or any(rule.mode is not TriggerMode.EVENT for rule in matching):
                return False
            if consumer.effect_type == "damage":
                if (
                    consumer.target_spec.mode is not TargetMode.ENEMY
                    or compile_simple_damage_event(
                        consumer, self.squad.members[consumer.actor]
                    ) is None
                    or not all(rule.is_runtime_supported for rule in consumer.condition_rules)
                ):
                    return False
                continue
            if self._enemy_named_stack_marker_shape_supported(consumer):
                continue
            return False
        # Any exact-name count reducer must also stay inside the one-reducer slice.
        reducers = [
            other for other in self.squad.effects
            if other.actor == source.actor
            and (other.stat or "") == "trigger_count_reduce"
            and other.parameters.get("target_effect") == source.name
        ]
        return len(reducers) <= 1

    def supports_weapon_hit_source(self, actor: int, source_name: str) -> bool:
        return any(
            effect.effect_id in self._weapon_hit_source_ids
            and effect.actor == actor
            and effect.name == source_name
            and self.supports(effect)
            for effect in self.squad.effects
        )

    def post_damage_weapon_hit_key(self, effect: "CompiledEffect") -> str | None:
        if effect.effect_id not in self._weapon_hit_source_ids or not self.supports(effect):
            return None
        return f"weapon_hit:{effect.name}"

    def _stack_count_shape_supported(
        self,
        effect: "CompiledEffect",
        spec: StackCountDamageSpec,
    ) -> bool:
        if any(
            rule.mode not in _STACK_COUNT_SAFE_CONDITIONS
            for rule in effect.condition_rules
        ):
            return False
        if any(
            other.actor == effect.actor
            and other.parameters.get("gauge_id") == spec.ref
            and (other.stat or "") in {"gauge_charge", "gauge_consume"}
            for other in self.squad.effects
        ):
            return True
        providers = [
            other for other in self.squad.effects
            if other.actor == effect.actor
            and other.name == spec.ref
            and self._enemy_named_stack_marker_shape_supported(other)
        ]
        return len(providers) == 1

    def _gauge_ref_runtime_supported(self, actor: int, ref: str) -> bool:
        runtime = self.runtime
        if runtime is None:
            return True
        family = (actor, ref)
        if family in runtime.dispatcher._unsafe_gauge_families:
            return False
        return any(
            runtime.dispatcher._gauge_family(other) == family
            and runtime.dispatcher._gauge_shape_supported(other)
            for other in self.squad.effects
        )

    def _stack_count_runtime_supported(self, effect: "CompiledEffect") -> bool:
        spec = self.stack_specs.get(effect.effect_id)
        if spec is None:
            return False
        has_gauge = any(
            other.actor == effect.actor
            and other.parameters.get("gauge_id") == spec.ref
            and (other.stat or "") in {"gauge_charge", "gauge_consume"}
            for other in self.squad.effects
        )
        if has_gauge:
            return self._gauge_ref_runtime_supported(effect.actor, spec.ref)
        providers = [
            other for other in self.squad.effects
            if other.actor == effect.actor
            and other.name == spec.ref
            and self._enemy_named_stack_marker_shape_supported(other)
        ]
        if len(providers) != 1:
            return False
        if self.runtime is None:
            return True
        return self.runtime.dispatcher.can_activate_effect(providers[0])

    @staticmethod
    def _state_effect_patternless_unreachable(effect: "CompiledEffect") -> bool:
        return (
            bool(effect.triggers)
            and all(
                (rule.event_key or "") in _PATTERNLESS_UNREACHABLE_STATE_EVENTS
                for rule in effect.triggers
            )
        )

    @staticmethod
    def _state_operation_shape_supported(effect: "CompiledEffect") -> bool:
        stat = effect.stat or ""
        if effect.effect_type != "instant" or stat not in {"debuff_stack_add", "remove_named_buff"}:
            return False
        if effect.target_spec.mode is not TargetMode.ENEMY:
            return False
        target_name = effect.parameters.get("target_effect")
        if not isinstance(target_name, str) or not target_name:
            return False
        if not all(rule.is_runtime_supported for rule in effect.condition_rules):
            return False
        if not effect.triggers or any(
            rule.event_key not in _SAFE_EVENT_KEYS for rule in effect.triggers
        ):
            return False
        if stat == "debuff_stack_add":
            if effect.parameters.get("scaling") is not None:
                return False
            if effect.value is None or float(effect.value) <= 0.0:
                return False
            if abs(float(effect.value) - round(float(effect.value))) > 1e-9:
                return False
        return True

    def _stateful_dot_shape_supported(
        self,
        effect: "CompiledEffect",
        spec: StackScaledDotSpec,
    ) -> bool:
        return (
            bool(effect.name)
            and (effect.polarity or "").startswith("harmful")
            and spec.immediate
            and all(rule.is_runtime_supported for rule in effect.condition_rules)
        )

    def _stateful_dot_dependencies_supported(self, effect: "CompiledEffect") -> bool:
        name = effect.name
        for other in self.squad.effects:
            if other.effect_id == effect.effect_id:
                continue
            if other.parameters.get("target_effect") != name:
                continue
            if self._state_effect_patternless_unreachable(other):
                continue
            if not self._state_operation_shape_supported(other):
                return False
        return True

    def _stateful_dot_runtime_supported(
        self,
        effect: "CompiledEffect",
        seen: set[int] | None = None,
    ) -> bool:
        spec = self.stateful_dot_specs.get(effect.effect_id)
        if spec is None:
            return False
        if self.runtime is None:
            return True
        seen = set() if seen is None else set(seen)
        if effect.effect_id in seen:
            return False
        seen.add(effect.effect_id)

        has_declared_gauge = any(
            other.actor == effect.actor
            and other.parameters.get("gauge_id") == spec.ref
            and (other.stat or "") in {"gauge_charge", "gauge_consume", "gauge_max_add", "gauge_charge_enabled", "gauge_consume_as_ammo"}
            for other in self.squad.effects
        )
        if has_declared_gauge:
            return self._gauge_ref_runtime_supported(effect.actor, spec.ref)

        ref_ids = self._stateful_dot_names.get(spec.ref, ())
        for ref_id in ref_ids:
            ref_effect = self.squad.effects[ref_id]
            if ref_effect.actor != effect.actor:
                continue
            if self._stateful_dot_runtime_supported(ref_effect, seen):
                return True
        return False

    def supports_state_operation(self, effect: "CompiledEffect") -> bool:
        if not self._state_operation_shape_supported(effect):
            return False
        name = str(effect.parameters.get("target_effect") or "")
        ids = self._stateful_dot_names.get(name, ())
        if not ids:
            return False
        if self.runtime is None:
            return True
        return any(
            self._stateful_dot_runtime_supported(self.squad.effects[effect_id])
            for effect_id in ids
        )

    def activate_state_operation(
        self,
        effect: "CompiledEffect",
        *,
        now: float,
        targets: tuple[int, ...],
    ) -> bool:
        runtime = self.runtime
        if runtime is None or not self.supports_state_operation(effect):
            return False
        name = str(effect.parameters.get("target_effect") or "")
        stat = effect.stat or ""
        if stat == "debuff_stack_add":
            delta = int(round(float(effect.value or 0.0)))
            for target in targets:
                runtime.dispatcher.effects.adjust_named_stack(
                    target, name, delta, now=now
                )
            return True
        if stat == "remove_named_buff":
            removed: list[int] = []
            for target in targets:
                removed.extend(
                    runtime.dispatcher.effects.remove_named_state(
                        target, name, now=now
                    )
                )
            for effect_id in removed:
                if effect_id in self.stateful_dot_specs:
                    self._dot_generation[effect_id] = self._dot_generation.get(effect_id, 0) + 1
            return True
        return False

    def _dot_state_is_observed(self, effect: "CompiledEffect") -> bool:
        name = effect.name
        if not name:
            return False
        for other in self.squad.effects:
            if other.effect_id == effect.effect_id:
                continue
            if any(name in condition for condition in other.conditions):
                return True
            if other.parameters.get("target_effect") == name:
                return True
            raw_target = other.target
            if isinstance(raw_target, str) and raw_target.endswith(f":{name}"):
                return True
        return False

    def _weapon_hit_consumer_source_proven(
        self, effect: "CompiledEffect", event_key: str
    ) -> bool:
        source_name = event_key[len("weapon_hit:"):]
        sources = [
            source for source in self.squad.effects
            if source.actor == effect.actor
            and source.effect_type == "damage"
            and source.name == source_name
        ]
        return len(sources) == 1 and self._weapon_hit_chain_shape_supported(sources[0])

    def _delivery_supported(self, effect: "CompiledEffect") -> bool:
        if effect.target_spec.mode is not TargetMode.ENEMY:
            return False
        if not all(rule.is_runtime_supported for rule in effect.condition_rules):
            return False
        if not effect.triggers:
            return False
        for rule in effect.triggers:
            if rule.mode is TriggerMode.PERIODIC:
                if rule.interval is None or float(rule.interval) <= 0.0:
                    return False
                continue
            if rule.event_key not in _SAFE_EVENT_KEYS:
                if not (
                    (rule.event_key or "").startswith("weapon_hit:")
                    and self._weapon_hit_consumer_source_proven(effect, rule.event_key or "")
                ):
                    return False
            if rule.event_key == "core_hit" and not is_static_expected_core_count_rule(rule):
                return False
        return True

    def supports(self, effect: "CompiledEffect") -> bool:
        if effect.effect_id in self.stack_specs:
            return self._stack_count_runtime_supported(effect)
        if effect.effect_id in self.stateful_dot_specs:
            return self._stateful_dot_runtime_supported(effect)
        return (
            effect.effect_id in self.specs
            or effect.effect_id in self.pending_specs
            or effect.effect_id in self.dot_specs
        )

    def attach(self, runtime: "BurstRuntime") -> None:
        self.runtime = runtime
        self.resolver = DamageTermResolver(
            runtime.squad,
            runtime.dispatcher.effects,
            runtime.state,
            runtime.enemy,
        )

    def _damage_spec(self, effect_id: int) -> DamageEventSpec | None:
        direct = self.specs.get(effect_id) or self.pending_specs.get(effect_id)
        if direct is not None:
            return direct
        stack = self.stack_specs.get(effect_id)
        if stack is not None:
            return stack.damage
        stateful_dot = self.stateful_dot_specs.get(effect_id)
        if stateful_dot is not None:
            return stateful_dot.damage
        dot = self.dot_specs.get(effect_id)
        return None if dot is None else dot.damage

    def _reference_count(self, actor: int, ref: str, *, now: float) -> int | None:
        runtime = self.runtime
        if runtime is None:
            return None
        gauges = runtime.state.actors[actor].gauges
        if ref in gauges:
            return int(gauges[ref])
        if runtime.dispatcher.effects.has_named_state(ENEMY, ref, now=now):
            return int(runtime.dispatcher.effects.named_stack(ENEMY, ref, now=now))
        return None

    def _stack_count_hit_count(self, effect_id: int) -> int | None:
        spec = self.stack_specs.get(effect_id)
        runtime = self.runtime
        actor = self._effect_actor.get(effect_id)
        if spec is None or runtime is None or actor is None:
            return None
        count = self._reference_count(actor, spec.ref, now=runtime.scheduler.now)
        return spec.damage.hit_count if count is None else max(0, count)

    def _stateful_effect_stack(self, effect_id: int, *, now: float) -> float:
        runtime = self.runtime
        if runtime is None:
            return 0.0
        values = [
            active.stacks
            for active in runtime.dispatcher.effects._active.values()
            if active.effect_id == effect_id
            and active.target == ENEMY
            and active.active(now)
        ]
        return max(values, default=0.0)

    def _score_spec(
        self,
        effect_id: int,
        *,
        now: float,
        full_burst: bool,
    ) -> bool:
        spec = self._damage_spec(effect_id)
        runtime = self.runtime
        resolver = self.resolver
        actor = self._effect_actor.get(effect_id)
        if spec is None or runtime is None or resolver is None or actor is None:
            return False
        hit_count = None
        coeff_multiplier = 1.0
        if effect_id in self.stack_specs:
            hit_count = self._stack_count_hit_count(effect_id)
            if hit_count is None:
                return False
        if effect_id in self.stateful_dot_specs:
            coeff_multiplier = self._stateful_effect_stack(effect_id, now=now)
        terms = resolver.resolve(actor, now=now)
        self.char_total[actor] += expected_damage_event(
            spec,
            runtime.squad.members[actor],
            runtime.enemy,
            terms,
            full_burst=full_burst,
            hit_count=hit_count,
            coeff_multiplier=coeff_multiplier,
        )
        return True

    @staticmethod
    def _dot_tick_allowed(spec, tick_t: float, expires_at: float) -> bool:
        if spec.immediate:
            return tick_t < expires_at - _DOT_EPS
        return tick_t <= expires_at + _DOT_EPS

    def _schedule_dot(
        self,
        effect_id: int,
        *,
        now: float,
        spec,
    ) -> bool:
        runtime = self.runtime
        actor = self._effect_actor.get(effect_id)
        if runtime is None or actor is None:
            return False
        generation = self._dot_generation.get(effect_id, 0) + 1
        self._dot_generation[effect_id] = generation
        expires_at = inf if spec.duration == -1 else float(now) + spec.duration
        first_t = float(now) if spec.immediate else float(now) + spec.interval
        if self._dot_tick_allowed(spec, first_t, expires_at):
            runtime.scheduler.schedule(
                first_t,
                EventKind.DAMAGE_TICK,
                actor=actor,
                payload=DotTickToken(effect_id, generation, expires_at),
            )
        return True

    def _activate_dot(self, effect_id: int, *, now: float) -> bool:
        spec = self.dot_specs.get(effect_id)
        if spec is None:
            return False
        return self._schedule_dot(effect_id, now=now, spec=spec)

    def _activate_stateful_dot(
        self,
        effect: "CompiledEffect",
        *,
        now: float,
        targets: tuple[int, ...],
    ) -> bool:
        spec = self.stateful_dot_specs.get(effect.effect_id)
        runtime = self.runtime
        if spec is None or runtime is None or not self._stateful_dot_runtime_supported(effect):
            return False
        captured = self._reference_count(effect.actor, spec.ref, now=now)
        initial_stack = 1 if captured is None else captured
        runtime.dispatcher.effects.activate_group_scaled(
            effect,
            targets,
            now,
            runtime.scheduler,
            initial_stacks=initial_stack,
        )
        return self._schedule_dot(effect.effect_id, now=now, spec=spec)

    def activate(
        self,
        effect: "CompiledEffect",
        *,
        now: float,
        targets: tuple[int, ...],
        context: SignalContext,
    ) -> bool:
        del context
        if ENEMY not in targets:
            return False
        if effect.effect_id in self.stack_specs and not self._stack_count_runtime_supported(effect):
            return False
        if effect.effect_id in self.stateful_dot_specs:
            return self._activate_stateful_dot(
                effect,
                now=now,
                targets=targets,
            )
        if effect.effect_id in self.pending_specs:
            self._pending_effect_ids.append(effect.effect_id)
            return True
        if effect.effect_id in self.dot_specs:
            return self._activate_dot(effect.effect_id, now=now)
        return self._score_spec(
            effect.effect_id,
            now=now,
            full_burst=bool(self.runtime and self.runtime.machine.phase == "full_burst"),
        )

    def handle_scheduled_tick(self, event: ScheduledEvent) -> bool:
        token = event.payload
        if not isinstance(token, DotTickToken):
            return False
        spec = self.dot_specs.get(token.effect_id) or self.stateful_dot_specs.get(token.effect_id)
        runtime = self.runtime
        if spec is None or runtime is None:
            return False
        if self._dot_generation.get(token.effect_id) != token.generation:
            return False
        if not self._dot_tick_allowed(spec, event.time, token.expires_at):
            return False

        eval_time = float(event.time)
        if not spec.immediate and event.time >= token.expires_at - _DOT_EPS:
            eval_time = nextafter(float(token.expires_at), -inf)

        fired = self._score_spec(
            token.effect_id,
            now=eval_time,
            full_burst=runtime.machine.phase == "full_burst",
        )
        if not fired:
            return False

        next_t = float(event.time) + spec.interval
        if self._dot_tick_allowed(spec, next_t, token.expires_at):
            runtime.scheduler.schedule(
                next_t,
                EventKind.DAMAGE_TICK,
                actor=event.actor,
                payload=token,
            )
        return True

    def flush_pending_burst(self, *, now: float) -> int:
        if not self._pending_effect_ids:
            return 0
        queued = tuple(self._pending_effect_ids)
        self._pending_effect_ids.clear()
        fired = 0
        for effect_id in queued:
            if self._score_spec(effect_id, now=now, full_burst=True):
                fired += 1
        return fired

    @property
    def supported_count(self) -> int:
        return (
            len(self.specs)
            + len(self.pending_specs)
            + len(self.dot_specs)
            + len(self.stack_specs)
            + len(self.stateful_dot_specs)
        )

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported_effect_ids)
