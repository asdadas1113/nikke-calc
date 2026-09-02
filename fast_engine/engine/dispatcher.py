from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from .capabilities import CapabilityDisposition
from .conditions import ConditionEvaluator, ConditionMode, SignalContext
from .damage_policy import is_direct_damage_buff_runtime_supported
from .effects import ActiveEffectStore
from .shot_blocks import static_bullet_lifetime_cadence_safe
from .state import ENEMY, StateStore
from .target_scope import possible_ally_targets, target_scope_is_static
from .targets import TargetMode, TargetResolver
from .triggers import TriggerMode
from .scheduler import EventKind

if TYPE_CHECKING:
    from .burst import BurstMachine, BurstSignal
    from .damage_runtime import SimpleDamageScoreSink
    from .model import CompiledEffect, CompiledSquad, EnemyStaticProfile
    from .scheduler import EventScheduler


_INTERNAL_BULLET_CONSUME_EVENT = "__fast_consume_dynamic_bullet_lifetime__"


@dataclass(frozen=True, slots=True)
class DispatchResult:
    activated_effect_ids: tuple[int, ...]
    skipped_unsupported: tuple[int, ...] = ()


class TriggerDispatcher:
    """Fast effect dispatcher over precompiled actor-scoped trigger buckets."""

    __slots__ = (
        "squad", "state", "enemy", "burst", "scheduler", "effects", "targets",
        "conditions", "damage_sink", "_effect_table", "_event_counts", "_conditional_counts",
        "_activation_counts", "_state_dependency_names", "_gauge_maxima",
        "_unsafe_gauge_families", "_strict_score_delivery", "_ammo_charge_sink",
        "_force_reload_sink", "_named_event_names_needed",
    )

    _AUXILIARY_STATS = frozenset({
        "atk_pct",
        "atk_flat",
        "atk_caster_based_pct",
    })

    _EXECUTABLE_STATS = frozenset({
        "burst_cooldown_reduce",
        "burst_cooldown",
        "fullburst_duration",
        "reload_speed_pct",
        "mg_warmup_speed_pct",
        "force_reload",
        "charge_speed_pct",
        "charge_speed_caster_based_pct",
        "max_ammo_pct",
        "max_ammo_flat",
        "ammo_charge_pct",
        "ammo_charge_flat",
        "charge_time_flat",
        "named_buff_duration_extend",
    })

    _SHIELD_STATS = frozenset({"shield_from_max_hp_pct"})
    _SHIELD_SAFE_EVENT_KEYS = frozenset({
        "battle_start",
        "burst_cast",
        "full_burst_start",
        "full_burst_end",
        "event:ally_burst_cast",
    })

    _GAUGE_STATS = frozenset({"gauge_charge", "gauge_consume"})
    _GAUGE_ADVANCED_STATS = frozenset({
        "gauge_max_add",
        "gauge_charge_enabled",
        "gauge_consume_as_ammo",
    })
    _GAUGE_SAFE_CONDITIONS = frozenset({
        ConditionMode.DURING_FULL_BURST,
        ConditionMode.NOT_DURING_FULL_BURST,
        ConditionMode.BURST_CASTED,
        ConditionMode.BURST_NOT_CASTED,
        ConditionMode.GAUGE_AT_LEAST,
        ConditionMode.GAUGE_BELOW,
        ConditionMode.GAUGE_EQUAL,
        ConditionMode.GAUGE_MOD,
    })
    _GAUGE_SAFE_EVENT_KEYS = frozenset({
        "battle_start",
        "burst_cast",
        "full_burst_start",
        "full_burst_end",
    })
    _PATTERNLESS_UNREACHABLE_GAUGE_EVENTS = frozenset({
        "enemy_death",
        "received_hit",
        "event:self_down",
    })

    def __init__(
        self,
        squad: "CompiledSquad",
        state: StateStore,
        enemy: "EnemyStaticProfile",
        burst: "BurstMachine",
        scheduler: "EventScheduler",
        damage_sink: "SimpleDamageScoreSink | None" = None,
    ) -> None:
        self.squad = squad
        self.state = state
        self.enemy = enemy
        self.burst = burst
        self.scheduler = scheduler
        self.damage_sink = damage_sink
        self.effects = ActiveEffectStore(squad, state)
        self.targets = TargetResolver(squad, state, self.effects, burst)
        self.conditions = ConditionEvaluator(squad, state, self.effects, enemy, burst)
        self._effect_table = tuple(squad.effects)
        self._event_counts: dict[tuple[int, str], int] = defaultdict(int)
        self._conditional_counts: dict[tuple[int, str], tuple[int, int]] = {}
        self._activation_counts: dict[int, int] = defaultdict(int)
        self._gauge_maxima: dict[tuple[int, str], float] = {}
        self._strict_score_delivery = False
        self._ammo_charge_sink: Callable[[str, tuple[int, ...], float, float], bool] | None = None
        self._force_reload_sink: Callable[[tuple[int, ...], float], bool] | None = None
        self._named_event_names_needed = frozenset(
            (rule.event_key or "")[len("event:"):]
            for effect in self._effect_table
            for rule in effect.triggers
            if self._is_generic_named_event_key(rule.event_key or "")
        )

        unsafe_gauges: set[tuple[int, str]] = set()
        for effect in self._effect_table:
            family = self._gauge_family(effect)
            stat = effect.stat or ""
            if family is None:
                continue
            if stat in self._GAUGE_ADVANCED_STATS:
                unsafe_gauges.add(family)
                continue
            if stat in self._GAUGE_STATS:
                if not self._gauge_shape_supported(effect) and not self._gauge_patternless_unreachable(effect):
                    unsafe_gauges.add(family)
        self._unsafe_gauge_families = frozenset(unsafe_gauges)

        state_modes = {
            ConditionMode.SELF_STATE, ConditionMode.NOT_SELF_STATE,
            ConditionMode.TARGET_STATE, ConditionMode.NOT_TARGET_STATE,
            ConditionMode.SELF_STACK_AT_LEAST, ConditionMode.TARGET_STACK_AT_LEAST,
        }
        self._state_dependency_names = frozenset(
            rule.key
            for effect in self._effect_table
            if self.is_runtime_executable_effect(effect)
            for rule in effect.condition_rules
            if rule.mode in state_modes and rule.key
        )

    def enable_strict_score_delivery(self) -> None:
        self._strict_score_delivery = True

    def attach_ammo_charge_sink(
        self,
        sink: Callable[[str, tuple[int, ...], float, float], bool],
    ) -> None:
        self._ammo_charge_sink = sink

    def attach_force_reload_sink(
        self,
        sink: Callable[[tuple[int, ...], float], bool],
    ) -> None:
        self._force_reload_sink = sink

    @classmethod
    def _gauge_family(cls, effect: "CompiledEffect") -> tuple[int, str] | None:
        stat = effect.stat or ""
        if stat not in cls._GAUGE_STATS and stat not in cls._GAUGE_ADVANCED_STATS:
            return None
        gauge_id = effect.parameters.get("gauge_id")
        if not isinstance(gauge_id, str) or not gauge_id:
            return None
        return effect.actor, gauge_id

    @classmethod
    def _gauge_shape_supported(cls, effect: "CompiledEffect") -> bool:
        family = cls._gauge_family(effect)
        if (
            family is None
            or effect.effect_type != "instant"
            or (effect.stat or "") not in cls._GAUGE_STATS
            or effect.target_spec.mode is not TargetMode.SELF
            or effect.value is None
            or not effect.triggers
        ):
            return False
        value = float(effect.value)
        if (effect.stat or "") == "gauge_charge" and value < 0.0:
            return False
        if (effect.stat or "") == "gauge_consume" and value < 0.0 and value != -1.0:
            return False
        if any(rule.mode not in cls._GAUGE_SAFE_CONDITIONS for rule in effect.condition_rules):
            return False
        for rule in effect.triggers:
            if rule.mode is not TriggerMode.EVENT:
                return False
            event_key = rule.event_key or ""
            if event_key in cls._GAUGE_SAFE_EVENT_KEYS:
                continue
            if event_key.startswith("burst_enter:") or event_key.startswith("squad_burst_cast:"):
                continue
            return False
        gauge_max = effect.parameters.get("gauge_max")
        if gauge_max is not None and float(gauge_max) < 0.0:
            return False
        return True

    @classmethod
    def _gauge_patternless_unreachable(cls, effect: "CompiledEffect") -> bool:
        return (
            cls._gauge_family(effect) is not None
            and (effect.stat or "") in cls._GAUGE_STATS
            and bool(effect.triggers)
            and all(
                (rule.event_key or "") in cls._PATTERNLESS_UNREACHABLE_GAUGE_EVENTS
                for rule in effect.triggers
            )
        )

    @staticmethod
    def _periodic_timing_is_only_blocker(effect: "CompiledEffect") -> bool:
        blockers = effect.capability.blockers
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and bool(blockers)
            and all(blocker == "timing:periodic" for blocker in blockers)
        )

    @staticmethod
    def _state_end_timing_is_only_runtime_blocker(effect: "CompiledEffect") -> bool:
        """Allow only the named-event shape emitted by Fast's timed self-state bridge.

        ``duration_bullets`` remains a runtime safety decision, so its capability
        field blocker may coexist with the state-end timing blocker here.
        """

        blockers = effect.capability.blockers
        allowed = {"timing:named_event", "field:duration_bullets"}
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and bool(blockers)
            and set(blockers).issubset(allowed)
            and any((rule.event_key or "").startswith("event:state_end:") for rule in effect.triggers)
            and all(
                rule.mode is TriggerMode.EVENT
                and (rule.event_key or "").startswith("event:state_end:")
                for rule in effect.triggers
            )
            and not effect.condition_rules
        )

    @staticmethod
    def _weapon_count_ammo_timing_is_only_runtime_blocker(effect: "CompiledEffect") -> bool:
        """Bridge only reducible physical-count instant ammo refills."""

        blockers = effect.capability.blockers
        if not (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(blockers) == {"timing:weapon_hit"}
            and effect.effect_type == "instant"
            and (effect.stat or "") in {"ammo_charge_pct", "ammo_charge_flat"}
            and effect.value is not None
            and float(effect.value) >= 0.0
            and effect.target_spec.runtime_supported
            and not effect.condition_rules
            and len(effect.triggers) == 1
        ):
            return False
        rule = effect.triggers[0]
        return (
            rule.mode is TriggerMode.MODULO
            and rule.trigger_count_reducible
            and rule.event_key in {"hit_count", "pellet_hit"}
            and int(rule.threshold or 0) > 0
        )

    @classmethod
    def _timed_shield_shape_supported(cls, effect: "CompiledEffect") -> bool:
        """Certify the presence-only timed shield slice owned by Fast."""

        if not (
            effect.effect_type == "buff"
            and (effect.stat or "") in cls._SHIELD_STATS
            and effect.value is not None
            and float(effect.value) > 0.0
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack in (None, 1, 1.0)
            and not effect.parameters
            and target_scope_is_static(effect.target_spec)
            and effect.target_spec.runtime_supported
            and not effect.condition_rules
            and bool(effect.triggers)
        ):
            return False
        for rule in effect.triggers:
            if rule.mode is not TriggerMode.EVENT:
                return False
            key = rule.event_key or ""
            if key in cls._SHIELD_SAFE_EVENT_KEYS:
                continue
            if key.startswith("burst_enter:") or key.startswith("squad_burst_cast:"):
                continue
            return False
        return True

    _NAMED_EVENT_EXEMPT = frozenset({
        "event:enemy_spawn",
        "event:target_spawn",
        "event:ally_burst_cast",
        "event:shield_applied",
    })

    @classmethod
    def _is_generic_named_event_key(cls, key: str) -> bool:
        return (
            key.startswith("event:")
            and not key.startswith("event:state_end:")
            and key not in cls._NAMED_EVENT_EXEMPT
        )

    @classmethod
    def _named_event_keys(cls, effect: "CompiledEffect") -> tuple[str, ...]:
        return tuple(
            rule.event_key or ""
            for rule in effect.triggers
            if cls._is_generic_named_event_key(rule.event_key or "")
        )

    @classmethod
    def _named_event_control_shape_supported(cls, effect: "CompiledEffect") -> bool:
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and effect.effect_type == "instant"
            and (effect.stat or "") == "burst_cooldown_reduce"
            and effect.value is not None
            and effect.target_spec.runtime_supported
            and all(rule.is_runtime_supported for rule in effect.condition_rules)
            and bool(effect.triggers)
            and all(
                rule.mode is TriggerMode.EVENT
                and cls._is_generic_named_event_key(rule.event_key or "")
                for rule in effect.triggers
            )
        )

    @classmethod
    def _named_duration_extend_shape_supported(cls, effect: "CompiledEffect") -> bool:
        target_effect = effect.parameters.get("target_effect")
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and effect.effect_type == "instant"
            and (effect.stat or "") == "named_buff_duration_extend"
            and effect.value is not None
            and float(effect.value) > 0.0
            and isinstance(target_effect, str)
            and bool(target_effect)
            and set(effect.parameters) == {"target_effect"}
            and target_scope_is_static(effect.target_spec)
            and effect.target_spec.runtime_supported
            and all(rule.is_runtime_supported for rule in effect.condition_rules)
            and bool(effect.triggers)
            and all(
                rule.mode is TriggerMode.EVENT
                and cls._is_generic_named_event_key(rule.event_key or "")
                for rule in effect.triggers
            )
        )

    @classmethod
    def _named_event_marker_nop_shape_supported(cls, effect: "CompiledEffect") -> bool:
        """Allow a Moris-NOP buff to exist only as a named-event marker.

        The underlying stat remains intentionally ignored. This bridge is limited
        to simple one-stack buffs on controller/burst events so it cannot turn an
        arbitrary unsupported mechanic into an executable Fast effect.
        """
        if not (
            effect.capability.disposition is CapabilityDisposition.MIRROR_MORIS_NOP
            and effect.effect_type == "buff"
            and bool(effect.name)
            and effect.max_stack in (None, 1, 1.0)
            and not effect.parameters
            and effect.target_spec.runtime_supported
            and not effect.condition_rules
            and bool(effect.triggers)
        ):
            return False
        for rule in effect.triggers:
            if rule.mode is not TriggerMode.EVENT:
                return False
            key = rule.event_key or ""
            if key in cls._SHIELD_SAFE_EVENT_KEYS:
                continue
            if key.startswith("burst_enter:") or key.startswith("squad_burst_cast:"):
                continue
            return False
        return True

    @staticmethod
    def is_executable_effect(effect: "CompiledEffect") -> bool:
        stat = effect.stat or ""
        if (
            TriggerDispatcher._named_event_control_shape_supported(effect)
            or TriggerDispatcher._named_duration_extend_shape_supported(effect)
        ):
            return True
        if stat in TriggerDispatcher._AUXILIARY_STATS:
            return (
                effect.effect_type == "buff"
                and effect.target_spec.runtime_supported
                and all(rule.is_runtime_supported for rule in effect.condition_rules)
            )
        if is_direct_damage_buff_runtime_supported(effect):
            return True
        capability_ok = (
            effect.capability.disposition is CapabilityDisposition.READY
            or TriggerDispatcher._periodic_timing_is_only_blocker(effect)
            or TriggerDispatcher._state_end_timing_is_only_runtime_blocker(effect)
            or TriggerDispatcher._weapon_count_ammo_timing_is_only_runtime_blocker(effect)
        )
        if not capability_ok:
            return False
        return (
            stat in TriggerDispatcher._EXECUTABLE_STATS
            or stat.startswith("burst_stage_override:")
        )

    _is_executable = is_executable_effect

    def _bullet_lifetime_runtime_safe(self, effect: "CompiledEffect") -> bool:
        if effect.parameters.get("duration_bullets") is None:
            return True
        if not target_scope_is_static(effect.target_spec):
            return True
        targets = possible_ally_targets(self.squad, effect)
        return bool(targets) and all(
            static_bullet_lifetime_cadence_safe(self.squad, actor)
            or self.effects.dynamic_bullet_lifetime_supported(actor)
            for actor in targets
        )

    def _named_event_source_runtime_safe(self, effect: "CompiledEffect") -> bool:
        keys = self._named_event_keys(effect)
        if not keys:
            return True
        for key in keys:
            name = key[len("event:"):]
            providers = tuple(
                provider
                for provider in self._effect_table
                if provider.effect_id != effect.effect_id
                and provider.effect_type == "buff"
                and provider.name == name
            )
            if not providers:
                return False
            for provider in providers:
                if self._named_event_keys(provider):
                    return False
                if provider.parameters.get("event_scope") not in (None, "", "squad", "recipients"):
                    return False
                if not provider.target_spec.runtime_supported:
                    return False
                if not (
                    self.is_executable_effect(provider)
                    or self._named_event_marker_nop_shape_supported(provider)
                ):
                    return False
        return True

    def is_runtime_executable_effect(self, effect: "CompiledEffect") -> bool:
        family = self._gauge_family(effect)
        if (
            family is not None
            and family not in self._unsafe_gauge_families
            and self._gauge_shape_supported(effect)
        ):
            return True
        if self._timed_shield_shape_supported(effect):
            return True
        if self.is_executable_effect(effect):
            if not self._named_event_source_runtime_safe(effect):
                return False
            return self._bullet_lifetime_runtime_safe(effect)
        if self.damage_sink is None:
            return False
        return (
            self.damage_sink.supports(effect)
            or self.damage_sink.supports_state_operation(effect)
        )

    def _sync_shield_target(self, target: int, *, now: float) -> None:
        present = any(
            active.target == target and float(effect.value or 0.0) > 0.0
            for effect, active in self.effects.iter_stat("shield_from_max_hp_pct", now=now)
        )
        self.state.set_shield(target, 1.0 if present else 0.0)

    def _is_state_dependency(self, effect: "CompiledEffect") -> bool:
        return (
            effect.effect_type == "buff"
            and bool(effect.name)
            and effect.name in self._state_dependency_names
            and effect.target_spec.runtime_supported
            and all(rule.is_runtime_supported for rule in effect.condition_rules)
        )

    def can_activate_effect(self, effect: "CompiledEffect") -> bool:
        if self.is_runtime_executable_effect(effect):
            return True
        if (
            effect.name
            and effect.name in self._named_event_names_needed
            and self._named_event_marker_nop_shape_supported(effect)
        ):
            return True
        return self._is_state_dependency(effect) and self._named_event_source_runtime_safe(effect)

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
        self,
        effect: "CompiledEffect",
        *,
        now: float,
        context: SignalContext,
        conditions_prechecked: bool = False,
        target_owner_actor: int | None = None,
    ) -> bool:
        if not self.can_activate_effect(effect):
            return False
        if (
            effect.max_trigger is not None
            and self._activation_counts[effect.effect_id] >= effect.max_trigger
        ):
            return False

        named_target = (
            effect.target_spec.count
            if effect.target_spec.mode.value == "named_actor"
            else None
        )
        if not conditions_prechecked and not self.conditions.evaluate_all(
            effect.condition_rules,
            effect_id=effect.effect_id,
            owner_actor=effect.actor,
            target_actor=named_target,
            now=now,
            context=context,
        ):
            return False

        targets = self.targets.resolve(
            effect.target_spec,
            owner_actor=(effect.actor if target_owner_actor is None else target_owner_actor),
            now=now,
        )
        if effect.parameters.get("duration_bullets") is not None:
            unsafe_targets = tuple(
                target
                for target in targets
                if target != ENEMY
                and not static_bullet_lifetime_cadence_safe(self.squad, target)
                and not self.effects.dynamic_bullet_lifetime_supported(target)
            )
            if unsafe_targets:
                if self._strict_score_delivery:
                    names = ", ".join(
                        self.squad.members[target].name for target in unsafe_targets
                    )
                    raise NotImplementedError(
                        "Fast duration_bullets resolved target cadence not owned: " + names
                    )
                return False

        stat = effect.stat or ""
        value = float(effect.value or 0.0)

        if effect.effect_type == "instant":
            if stat == "burst_cooldown_reduce":
                for target in targets:
                    if target != ENEMY:
                        self.burst.adjust_cooldown(target, value, now, self.scheduler)
            elif stat in {"ammo_charge_pct", "ammo_charge_flat"}:
                if self._ammo_charge_sink is None or any(target == ENEMY for target in targets):
                    return False
                actor_targets = tuple(int(target) for target in targets)
                if not self._ammo_charge_sink(stat, actor_targets, value, now):
                    return False
            elif stat == "force_reload":
                if self._force_reload_sink is None or any(target == ENEMY for target in targets):
                    return False
                actor_targets = tuple(int(target) for target in targets)
                if not self._force_reload_sink(actor_targets, now):
                    return False
            elif stat == "named_buff_duration_extend":
                if any(target == ENEMY for target in targets):
                    return False
                target_effect = effect.parameters.get("target_effect")
                if not isinstance(target_effect, str) or not target_effect:
                    return False
                self.effects.extend_named_states(
                    tuple(int(target) for target in targets),
                    target_effect,
                    value,
                    now=now,
                    scheduler=self.scheduler,
                )
            elif stat in self._GAUGE_STATS:
                family = self._gauge_family(effect)
                if (
                    family is None
                    or family in self._unsafe_gauge_families
                    or not self._gauge_shape_supported(effect)
                ):
                    return False
                gauge_id = family[1]
                for target in targets:
                    if target == ENEMY:
                        return False
                    target_family = (target, gauge_id)
                    if stat == "gauge_charge":
                        gauge_max = effect.parameters.get("gauge_max")
                        if gauge_max is not None:
                            self._gauge_maxima[target_family] = float(gauge_max)
                        maximum = self._gauge_maxima.get(target_family, float("inf"))
                        self.state.add_gauge(
                            target,
                            gauge_id,
                            value,
                            maximum=maximum,
                        )
                    else:
                        current = self.state.actors[target].gauges.get(gauge_id, 0.0)
                        if value == -1.0:
                            self.state.set_gauge(target, gauge_id, 0.0)
                        else:
                            self.state.set_gauge(
                                target,
                                gauge_id,
                                max(0.0, current - value),
                            )
            elif (
                self.damage_sink is not None
                and self.damage_sink.supports_state_operation(effect)
            ):
                if not self.damage_sink.activate_state_operation(
                    effect,
                    now=now,
                    targets=targets,
                ):
                    return False
            else:
                return False
        elif effect.effect_type == "buff":
            if stat in self._SHIELD_STATS and any(target == ENEMY for target in targets):
                return False
            was_active = self.effects.group_active(effect.effect_id, targets, now=now)
            activated_group = self.effects.activate_group(effect, targets, now, self.scheduler)
            max_stack = effect.max_stack if effect.max_stack is not None else 1.0
            if (
                activated_group
                and effect.name
                and effect.name in self._named_event_names_needed
                and (not was_active or float(max_stack) != 1.0)
            ):
                from .burst import BurstSignal
                if effect.parameters.get("event_scope") == "recipients":
                    audience = tuple(int(target) for target in targets if target != ENEMY)
                else:
                    audience = tuple(range(len(self.squad.members)))
                for observer in audience:
                    self.dispatch(BurstSignal(now, f"event:{effect.name}", observer, observer))
            if stat in self._SHIELD_STATS:
                from .burst import BurstSignal
                actor_targets = tuple(int(target) for target in targets)
                for target in actor_targets:
                    self._sync_shield_target(target, now=now)
                # Moris establishes shield state before notifying each recipient.
                for target in actor_targets:
                    self.dispatch(BurstSignal(now, "event:shield_applied", target, target))
            if stat.startswith("burst_stage_override:"):
                suffix = stat.split(":", 1)[1]
                if suffix.startswith("reenter"):
                    self.burst.set_reenter_stage(
                        effect.actor, suffix.removeprefix("reenter")
                    )
                else:
                    self.burst.set_stage_override(effect.actor, suffix)
        elif effect.effect_type == "damage":
            if self.damage_sink is None or not self.damage_sink.supports(effect):
                return False
            if not self.damage_sink.activate(
                effect,
                now=now,
                targets=targets,
                context=context,
            ):
                return False
        else:
            return False

        self._activation_counts[effect.effect_id] += 1
        return True

    def dispatch(
        self,
        signal: "BurstSignal",
        *,
        context: SignalContext = SignalContext(),
    ) -> DispatchResult:
        owner = signal.owner_actor
        event_key = signal.event_key
        if event_key == _INTERNAL_BULLET_CONSUME_EVENT:
            self.effects.consume_dynamic_bullet(owner, now=signal.time, count=1)
            return DispatchResult(())

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
            if not self._rule_matches(
                effect,
                indexed.rule_index,
                event_key=event_key,
                event_count=event_count,
                context=context,
                now=signal.time,
            ):
                continue
            seen_effects.add(effect.effect_id)
            if self.can_activate_effect(effect):
                if self._activate(
                    effect,
                    now=signal.time,
                    context=context,
                    conditions_prechecked=effect.triggers[indexed.rule_index].mode
                    in {
                        TriggerMode.CONDITIONAL_AT_LEAST,
                        TriggerMode.CONDITIONAL_MODULO,
                    },
                ):
                    activated.append(effect.effect_id)
            else:
                skipped.append(effect.effect_id)
        return DispatchResult(tuple(activated), tuple(skipped))

    def dispatch_periodic(
        self,
        effect_id: int,
        rule_index: int,
        *,
        time: float,
        context: SignalContext = SignalContext(),
    ) -> DispatchResult:
        effect = self._effect_table[effect_id]
        rule = effect.triggers[rule_index]
        if rule.mode is not TriggerMode.PERIODIC or rule.interval is None:
            raise ValueError(
                f"not a periodic trigger: effect={effect_id}, rule={rule_index}"
            )
        if not self.can_activate_effect(effect):
            return DispatchResult((), (effect.effect_id,))
        if self._activate(effect, now=time, context=context):
            return DispatchResult((effect.effect_id,), ())
        return DispatchResult((), ())

    def dispatch_team_hit(
        self,
        event_key: str,
        *,
        time: float,
        attacker: int,
        context: SignalContext = SignalContext(),
        count_increment: int = 1,
    ) -> DispatchResult:
        if count_increment <= 0:
            raise ValueError("count_increment must be > 0")
        counter_key = (-1, event_key)
        self._event_counts[counter_key] += int(count_increment)
        event_count = self._event_counts[counter_key]
        activated: list[int] = []
        skipped: list[int] = []
        seen_effects: set[int] = set()
        for indexed in self.squad.trigger_index.for_event(event_key):
            effect = self._effect_table[indexed.effect_id]
            if effect.effect_id in seen_effects:
                continue
            if not self._rule_matches(
                effect,
                indexed.rule_index,
                event_key=event_key,
                event_count=event_count,
                context=context,
                now=time,
            ):
                continue
            seen_effects.add(effect.effect_id)
            if self.can_activate_effect(effect):
                if self._activate(
                    effect,
                    now=time,
                    context=context,
                    target_owner_actor=attacker,
                    conditions_prechecked=effect.triggers[indexed.rule_index].mode
                    in {
                        TriggerMode.CONDITIONAL_AT_LEAST,
                        TriggerMode.CONDITIONAL_MODULO,
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
            if (
                any(rule.raw == "burst_cast" for rule in effect.triggers)
                and caster != b3_actor
            ):
                continue
            total += float(effect.value or 0.0) * active.stacks
            seen_casters.add(caster)
        return total

    def handle_expiry(self, event) -> None:
        expired = self.effects.handle_expiry(event)
        if expired is None:
            return

        # Moris removes all timed states first, then emits named state_end events.
        # The first Fast bridge is deliberately restricted to a one-target self
        # buff with an ordinary time lifetime. Group/bullet/removal-driven state
        # endings remain fail-closed until they have their own ordering contract.
        if (
            expired.name
            and expired.effect_type == "buff"
            and expired.target_spec.mode is TargetMode.SELF
            and expired.duration is not None
            and expired.duration >= 0.0
            and expired.parameters.get("duration_bullets") is None
        ):
            self.scheduler.schedule(
                event.time,
                EventKind.STATE_END_NOTIFY,
                actor=expired.actor,
                payload=(expired.actor, expired.name),
            )

        stat = expired.stat or ""
        if stat in self._SHIELD_STATS and event.actor != ENEMY:
            self._sync_shield_target(int(event.actor), now=event.time)
        if stat.startswith("burst_stage_override:"):
            stage = None
            reenter = None
            for effect, _active in self.effects.iter_stat_prefix(
                "burst_stage_override:", now=event.time
            ):
                if effect.actor != expired.actor:
                    continue
                suffix = (effect.stat or "").split(":", 1)[1]
                if suffix.startswith("reenter"):
                    reenter = suffix.removeprefix("reenter")
                else:
                    stage = suffix
            self.burst.set_stage_override(expired.actor, stage)
            self.burst.set_reenter_stage(expired.actor, reenter)
