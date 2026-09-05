from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from .capabilities import CapabilityDisposition
from .conditions import ConditionEvaluator, ConditionMode, SignalContext
from .damage_policy import (
    DIRECT_DAMAGE_STATE_STATS,
    is_direct_damage_buff_runtime_supported,
)
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
_STAT_APPLIED_EVENT_STATS = frozenset({"dot_dmg_pct", "split_dmg_pct"})


@dataclass(frozen=True, slots=True)
class DispatchResult:
    activated_effect_ids: tuple[int, ...]
    skipped_unsupported: tuple[int, ...] = ()


class TriggerDispatcher:
    """Fast effect dispatcher over precompiled actor-scoped trigger buckets."""

    __slots__ = (
        "squad", "state", "enemy", "burst", "scheduler", "effects", "targets",
        "conditions", "damage_sink", "_effect_table", "_event_counts", "_conditional_counts",
        "_activation_counts", "_state_dependency_names", "_self_stack_passive_ids",
        "_self_stack_dependency_names", "_self_state_passive_ids",
        "_self_state_dependency_names", "_gauge_maxima",
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
        self._self_stack_passive_ids = tuple(
            effect.effect_id
            for effect in self._effect_table
            if self._self_stack_conditional_passive_shape_supported(effect)
            and self.is_runtime_executable_effect(effect)
        )
        self._self_stack_dependency_names = frozenset(
            rule.key
            for effect_id in self._self_stack_passive_ids
            for rule in self._effect_table[effect_id].condition_rules
            if rule.key
        )
        self._self_state_passive_ids = tuple(
            effect.effect_id
            for effect in self._effect_table
            if self._self_state_conditional_passive_shape_supported(effect)
            and self.is_runtime_executable_effect(effect)
        )
        self._self_state_dependency_names = frozenset(
            rule.key
            for effect_id in self._self_state_passive_ids
            for rule in self._effect_table[effect_id].condition_rules
            if rule.key
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
    def _periodic_permanent_self_direct_stack_shape_supported(
        effect: "CompiledEffect",
    ) -> bool:
        """Certify an immutable-grid periodic self stack used by damage scoring.

        This deliberately excludes finite lifetimes, mutable conditions, recipient
        selection, removable state and periodic side effects. Moris/Fast need only
        observe the fixed periodic stack edge and its generic named-event broadcast.
        """
        if not (
            effect.effect_type == "buff"
            and bool(effect.name)
            and (effect.stat or "") in DIRECT_DAMAGE_STATE_STATS
            and effect.polarity == "beneficial_irremovable"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and effect.duration in (None, -1, -1.0)
            and effect.max_stack is not None
            and float(effect.max_stack) > 1.0
            and float(effect.max_stack).is_integer()
            and effect.max_trigger is None
            and effect.tick_interval is None
            and not effect.parameters
            and not effect.condition_rules
            and bool(effect.triggers)
        ):
            return False
        return all(
            rule.mode is TriggerMode.PERIODIC
            and rule.interval is not None
            and float(rule.interval) > 0.0
            for rule in effect.triggers
        )

    @staticmethod
    def _periodic_finite_self_crit_shape_supported(
        effect: "CompiledEffect",
    ) -> bool:
        """Certify a fixed-grid finite one-stack self crit buff during full burst."""
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers) == {
                "category:hit_formula",
                "stat:crit_rate",
                "timing:periodic",
                "condition:simple_runtime",
            }
            and effect.effect_type == "buff"
            and bool(effect.name)
            and (effect.stat or "") == "crit_rate"
            and effect.polarity == "beneficial"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and float(effect.value) >= 0.0
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack in (1, 1.0)
            and effect.max_trigger is None
            and effect.tick_interval is None
            and not effect.parameters
            and len(effect.condition_rules) == 1
            and effect.condition_rules[0].mode is ConditionMode.DURING_FULL_BURST
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.PERIODIC
            and effect.triggers[0].interval is not None
            and float(effect.triggers[0].interval) > 0.0
        )

    @staticmethod
    def _periodic_finite_enemy_received_damage_shape_supported(
        effect: "CompiledEffect",
    ) -> bool:
        """Certify a fixed-grid finite enemy received-damage stack."""
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers) == {
                "category:hit_formula",
                "stat:received_dmg_pct",
                "timing:periodic",
                "condition:enemy",
                "target:enemy_singleton",
            }
            and effect.effect_type == "buff"
            and effect.polarity == "harmful"
            and bool(effect.name)
            and (effect.stat or "") == "received_dmg_pct"
            and effect.target_spec.mode is TargetMode.ENEMY
            and effect.target_spec.runtime_supported
            and effect.value is not None
            and float(effect.value) >= 0.0
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack is not None
            and float(effect.max_stack) >= 1.0
            and float(effect.max_stack).is_integer()
            and effect.max_trigger is None
            and effect.tick_interval is None
            and not effect.parameters
            and len(effect.condition_rules) == 1
            and effect.condition_rules[0].mode is ConditionMode.TARGET_CODE
            and bool(effect.condition_rules[0].key)
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.PERIODIC
            and effect.triggers[0].interval is not None
            and float(effect.triggers[0].interval) > 0.0
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

    @staticmethod
    def _full_charge_hit_permanent_self_charge_speed_shape_supported(
        effect: "CompiledEffect",
    ) -> bool:
        """Certify a permanent self charge-speed state applied after a full-charge hit."""
        if not (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers) == {"timing:weapon_hit"}
            and effect.effect_type == "buff"
            and (effect.stat or "") == "charge_speed_pct"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and float(effect.value) >= 0.0
            and effect.duration in (None, -1.0)
            and effect.max_stack in (None, 1, 1.0)
            and effect.max_trigger is None
            and effect.tick_interval is None
            and not effect.parameters
            and not effect.condition_rules
            and len(effect.triggers) == 1
        ):
            return False
        rule = effect.triggers[0]
        return rule.mode is TriggerMode.EVENT and rule.event_key == "full_charge_hit"

    @staticmethod
    def _on_attack_charge_speed_shape_supported(effect: "CompiledEffect") -> bool:
        """Bridge only a simple self charge-speed stack driven by one physical attack."""
        if not (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers) == {"timing:weapon_hit"}
            and effect.effect_type == "buff"
            and (effect.stat or "") == "charge_speed_pct"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack is not None
            and float(effect.max_stack) >= 1.0
            and not effect.parameters
            and not effect.condition_rules
            and len(effect.triggers) == 1
        ):
            return False
        rule = effect.triggers[0]
        return rule.mode is TriggerMode.EVENT and rule.event_key == "on_attack"

    @staticmethod
    def _charge_overflow_conversion_shape_supported(effect: "CompiledEffect") -> bool:
        """Certify immutable self charge-speed overflow conversion."""
        return (
            effect.effect_type == "buff"
            and (effect.stat or "") == "charge_speed_overflow_conversion_pct"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and float(effect.value) >= 0.0
            and effect.duration in (None, -1.0)
            and effect.max_stack in (None, 1, 1.0)
            and not effect.parameters
            and not effect.condition_rules
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.EVENT
            and effect.triggers[0].event_key == "battle_start"
        )

    @staticmethod
    def _trigger_count_reduce_shape_supported(effect: "CompiledEffect") -> bool:
        return (
            effect.effect_type == "buff"
            and (effect.stat or "") == "trigger_count_reduce"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and float(effect.value) > 0.0
            and float(effect.value).is_integer()
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack in (None, 1, 1.0)
            and set(effect.parameters) == {"target_effect"}
            and isinstance(effect.parameters.get("target_effect"), str)
            and bool(effect.parameters.get("target_effect"))
            and all(rule.is_runtime_supported for rule in effect.condition_rules)
            and bool(effect.triggers)
            and all(
                rule.mode is TriggerMode.EVENT
                and (rule.event_key or "") in {"burst_cast", "full_burst_start", "full_burst_end"}
                for rule in effect.triggers
            )
        )

    def _trigger_count_reduce_runtime_supported(self, effect: "CompiledEffect") -> bool:
        if not self._trigger_count_reduce_shape_supported(effect):
            return False
        name = str(effect.parameters.get("target_effect") or "")
        targets = [
            other for other in self._effect_table
            if other.actor == effect.actor and other.name == name
        ]
        if len(targets) != 1:
            return False
        target = targets[0]
        return (
            len(target.triggers) == 1
            and target.triggers[0].mode is TriggerMode.MODULO
            and target.triggers[0].trigger_count_reducible
            and target.triggers[0].event_key == "hit_count"
            and int(target.triggers[0].threshold or 0) > int(float(effect.value))
        )

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

    def _enemy_named_stack_marker_runtime_supported(self, effect: "CompiledEffect") -> bool:
        if not self._enemy_named_stack_marker_shape_supported(effect) or self.damage_sink is None:
            return False
        source = (effect.triggers[0].event_key or "")[len("weapon_hit:"):]
        return self.damage_sink.supports_weapon_hit_source(effect.actor, source)

    @staticmethod
    def _enemy_remove_named_state_shape_supported(effect: "CompiledEffect") -> bool:
        return (
            effect.effect_type == "instant"
            and (effect.stat or "") == "remove_named_buff"
            and effect.target_spec.mode is TargetMode.ENEMY
            and set(effect.parameters) == {"target_effect"}
            and isinstance(effect.parameters.get("target_effect"), str)
            and bool(effect.parameters.get("target_effect"))
            and all(rule.is_runtime_supported for rule in effect.condition_rules)
            and bool(effect.triggers)
            and all(
                rule.mode is TriggerMode.EVENT
                and (rule.event_key or "") in {"burst_cast", "full_burst_start", "full_burst_end"}
                for rule in effect.triggers
            )
        )

    def _enemy_remove_named_state_runtime_supported(self, effect: "CompiledEffect") -> bool:
        if not self._enemy_remove_named_state_shape_supported(effect):
            return False
        name = str(effect.parameters.get("target_effect") or "")
        providers = [
            other for other in self._effect_table
            if other.actor == effect.actor
            and other.name == name
            and self._enemy_named_stack_marker_shape_supported(other)
        ]
        return len(providers) == 1 and self._enemy_named_stack_marker_runtime_supported(providers[0])

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

    @staticmethod
    def _parse_stack_reach_event_key(key: str) -> tuple[str, int] | None:
        prefix = "stack_reach:"
        if not key.startswith(prefix):
            return None
        body = key[len(prefix):]
        name, sep, raw = body.rpartition(":")
        if not sep or not name or not raw.isdigit():
            return None
        threshold = int(raw)
        return None if threshold <= 0 else (name, threshold)

    @classmethod
    def _self_stack_reach_marker_shape_supported(cls, effect: "CompiledEffect") -> bool:
        """Materialize only a sparse permanent self stack used as a state counter.

        The underlying stat may remain a Moris-NOP for damage purposes. Fast owns
        only the stack count and its hit-count boundaries, not the ignored stat.
        """
        if not (
            effect.capability.disposition is CapabilityDisposition.MIRROR_MORIS_NOP
            and effect.effect_type == "buff"
            and bool(effect.name)
            and effect.target_spec.mode is TargetMode.SELF
            and effect.duration in (None, -1, -1.0)
            and effect.max_stack is not None
            and float(effect.max_stack) > 1.0
            and float(effect.max_stack).is_integer()
            and set(effect.parameters).issubset({"note"})
            and not effect.condition_rules
            and len(effect.triggers) == 1
        ):
            return False
        rule = effect.triggers[0]
        return (
            rule.mode is TriggerMode.MODULO
            and rule.trigger_count_reducible
            and rule.event_key == "hit_count"
            and int(rule.threshold or 0) > 0
        )

    @classmethod
    def _stack_reach_source_shape_supported(
        cls, squad: "CompiledSquad", effect: "CompiledEffect"
    ) -> bool:
        parsed = tuple(
            cls._parse_stack_reach_event_key(rule.event_key or "")
            for rule in effect.triggers
        )
        if not parsed or any(item is None for item in parsed):
            return False
        for item in parsed:
            assert item is not None
            name, threshold = item
            providers = tuple(
                provider
                for provider in squad.members[effect.actor].effects
                if provider.effect_id != effect.effect_id
                and provider.name == name
                and cls._self_stack_reach_marker_shape_supported(provider)
            )
            if len(providers) != 1:
                return False
            marker = providers[0]
            if threshold > int(float(marker.max_stack or 0.0)):
                return False
            if any(
                other.effect_id != marker.effect_id
                and other.parameters.get("target_effect") == name
                and (other.stat or "") in {
                    "buff_stack_add", "buff_stack_remove", "buff_stack_init"
                }
                for other in squad.members[effect.actor].effects
            ):
                return False
        return True

    @classmethod
    def _self_stack_remove_shape_supported(cls, effect: "CompiledEffect") -> bool:
        name = effect.parameters.get("target_effect")
        if not (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and effect.effect_type == "instant"
            and (effect.stat or "") == "remove_named_buff"
            and effect.target_spec.mode is TargetMode.SELF
            and isinstance(name, str)
            and bool(name)
            and set(effect.parameters) == {"target_effect"}
            and not effect.condition_rules
            and bool(effect.triggers)
        ):
            return False
        for rule in effect.triggers:
            parsed = cls._parse_stack_reach_event_key(rule.event_key or "")
            if rule.mode is not TriggerMode.EVENT or parsed is None or parsed[0] != name:
                return False
        return True

    def _self_stack_remove_runtime_supported(self, effect: "CompiledEffect") -> bool:
        return (
            self._self_stack_remove_shape_supported(effect)
            and self._stack_reach_source_shape_supported(self.squad, effect)
        )

    @classmethod
    def _self_stack_heal_shape_supported(cls, effect: "CompiledEffect") -> bool:
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and effect.effect_type == "instant"
            and (effect.stat or "") == "heal_hp_pct"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and float(effect.value) > 0.0
            and not effect.parameters
            and not effect.condition_rules
            and bool(effect.triggers)
            and all(
                rule.mode is TriggerMode.EVENT
                and cls._parse_stack_reach_event_key(rule.event_key or "") is not None
                for rule in effect.triggers
            )
        )

    @classmethod
    def _self_stack_heal_chain_shape_supported(
        cls, squad: "CompiledSquad", effect: "CompiledEffect"
    ) -> bool:
        if not (
            cls._self_stack_heal_shape_supported(effect)
            and cls._stack_reach_source_shape_supported(squad, effect)
        ):
            return False
        for rule in effect.triggers:
            key = rule.event_key or ""
            parsed = cls._parse_stack_reach_event_key(key)
            if parsed is None:
                return False
            name, _threshold = parsed
            resetters = tuple(
                other
                for other in squad.members[effect.actor].effects
                if other.effect_id != effect.effect_id
                and cls._self_stack_remove_shape_supported(other)
                and other.parameters.get("target_effect") == name
                and any((r.event_key or "") == key for r in other.triggers)
            )
            if not resetters:
                return False
        return True

    def _self_stack_heal_runtime_supported(self, effect: "CompiledEffect") -> bool:
        return self._self_stack_heal_chain_shape_supported(self.squad, effect)

    @classmethod
    def heal_received_dependency_score_safe(
        cls, squad: "CompiledSquad", consumer: "CompiledEffect"
    ) -> bool:
        """Certify heal_received only when every possible provider is owned.

        The first slice intentionally supports only a recurring self stack-heal
        chain. External instant heals and lifesteal remain fail-closed so omitted
        refreshes cannot silently change a comparison-critical buff window.
        """
        owner = consumer.actor
        providers = tuple(
            provider
            for provider in squad.effects
            if provider.effect_id != consumer.effect_id
            and (provider.stat or "") in {"heal_hp_pct", "lifesteal_pct"}
            and owner in possible_ally_targets(squad, provider)
        )
        if not providers:
            return False
        return all(
            (provider.stat or "") == "heal_hp_pct"
            and provider.actor == owner
            and provider.target_spec.mode is TargetMode.SELF
            and cls._self_stack_heal_chain_shape_supported(squad, provider)
            for provider in providers
        )

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

    @staticmethod
    def _timed_self_named_state_marker_shape_supported(effect: "CompiledEffect") -> bool:
        """Certify a pure finite self-state marker emitted by one burst cast."""
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers) == {"category:state_trigger", "stat:None"}
            and effect.effect_type == "buff"
            and not (effect.stat or "")
            and bool(effect.name)
            and effect.value is None
            and effect.polarity in (None, "neutral")
            and effect.target_spec.mode is TargetMode.SELF
            and effect.target_spec.runtime_supported
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack in (None, 1, 1.0)
            and effect.max_trigger is None
            and effect.tick_interval is None
            and not effect.condition_rules
            and set(effect.parameters).issubset({"note"})
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.EVENT
            and effect.triggers[0].event_key == "burst_cast"
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

    @classmethod
    def _temporary_self_charge_weapon_change_shape_supported(cls, effect: "CompiledEffect") -> bool:
        params = effect.parameters
        allowed = {
            "weapon_type", "damage_coeff", "max_ammo", "reload_seconds",
            "reload_time", "charge_seconds", "charge_time", "full_charge_mult",
            "post_fire_delay", "cover_during_delay",
        }
        if not (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers).issubset({
                "stat:None",
                "field:weapon_type",
                "field:damage_coeff",
                "field:max_ammo",
                "field:full_charge_mult",
                "field:post_fire_delay",
                "field:cover_during_delay",
                "field:reload_seconds",
                "field:reload_time",
                "field:charge_seconds",
                "field:charge_time",
            })
            and effect.effect_type == "weapon_change"
            and effect.target_spec.mode.value == "self"
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack in (None, 1, 1.0)
            and not effect.condition_rules
            and bool(effect.triggers)
            and not (set(params) - allowed)
            and params.get("weapon_type") in {"SR", "RL"}
            and params.get("max_ammo") == -1
            and isinstance(params.get("damage_coeff"), (int, float))
            and isinstance(params.get("full_charge_mult"), (int, float))
            and isinstance(params.get("post_fire_delay"), (int, float))
        ):
            return False
        charge = params.get("charge_seconds", params.get("charge_time", 1.0))
        if not isinstance(charge, (int, float)) or float(charge) < 0.0:
            return False
        for rule in effect.triggers:
            if rule.mode is not TriggerMode.EVENT:
                return False
            key = rule.event_key or ""
            if key == "burst_cast" or key.startswith("squad_burst_cast:"):
                continue
            return False
        return True

    def _temporary_self_charge_weapon_change_runtime_supported(
        self, effect: "CompiledEffect"
    ) -> bool:
        if not self._temporary_self_charge_weapon_change_shape_supported(effect):
            return False
        member = self.squad.members[effect.actor]
        params = effect.parameters
        charge = float(params.get("charge_seconds", params.get("charge_time", 1.0)))
        return (
            str(member.weapon.get("fire_mode") or "") == "charge"
            and str(member.weapon.get("weapon_type") or member.weapon_type) == str(params.get("weapon_type"))
            and abs(float(member.weapon.get("charge_time") or 0.0) - charge) <= 1e-9
            and not member.weapon.get("control")
            and not member.weapon.get("is_clip")
        )

    @staticmethod
    def _stat_applied_event_stat(key: str) -> str | None:
        prefix = "event:stat_applied:"
        if not key.startswith(prefix):
            return None
        stat = key[len(prefix):]
        return stat if stat in _STAT_APPLIED_EVENT_STATS else None

    @classmethod
    def _stat_applied_charge_speed_shape_supported(cls, effect: "CompiledEffect") -> bool:
        """Certify one finite self charge-speed state driven by recipient stat application."""
        if not (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers) == {"timing:named_event"}
            and effect.effect_type == "buff"
            and (effect.stat or "") == "charge_speed_pct"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and float(effect.value) > -100.0
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack in (None, 1, 1.0)
            and effect.max_trigger is None
            and effect.tick_interval is None
            and not effect.parameters
            and len(effect.triggers) == 1
        ):
            return False
        rule = effect.triggers[0]
        if rule.mode is not TriggerMode.EVENT or cls._stat_applied_event_stat(rule.event_key or "") is None:
            return False
        return (
            not effect.condition_rules
            or (
                len(effect.condition_rules) == 1
                and effect.condition_rules[0].mode is ConditionMode.NOT_SELF_STATE
                and bool(effect.condition_rules[0].key)
            )
        )

    @classmethod
    def stat_applied_dependency_score_safe(
        cls, squad: "CompiledSquad", effect: "CompiledEffect", key: str
    ) -> bool:
        """Prove recipient-scoped stat_applied source ownership without guessing."""
        stat = cls._stat_applied_event_stat(key)
        if stat is None:
            return False
        owner = effect.actor
        providers = tuple(
            provider
            for provider in squad.effects
            if provider.effect_id != effect.effect_id
            and (provider.stat or "") == stat
            and owner in possible_ally_targets(squad, provider)
        )
        if not providers:
            return False
        for provider in providers:
            if (
                provider.effect_type != "buff"
                or not provider.target_spec.runtime_supported
                or cls._named_event_keys(provider)
                or not cls.is_executable_effect(provider)
            ):
                return False

        # First slice may keep a NOT_SELF_STATE gate only when every matching
        # state is another stat_applied charge-speed branch whose source stat is
        # provably absent for this recipient. This makes the condition immutable.
        for condition in effect.condition_rules:
            if condition.mode is not ConditionMode.NOT_SELF_STATE or not condition.key:
                return False
            state_effects = tuple(
                candidate
                for candidate in squad.members[owner].effects
                if candidate.effect_id != effect.effect_id and candidate.name == condition.key
            )
            for state_effect in state_effects:
                if not cls._stat_applied_charge_speed_shape_supported(state_effect):
                    return False
                state_keys = cls._named_event_keys(state_effect)
                if len(state_keys) != 1:
                    return False
                opposite_stat = cls._stat_applied_event_stat(state_keys[0])
                if opposite_stat is None:
                    return False
                if any(
                    candidate.effect_id != state_effect.effect_id
                    and (candidate.stat or "") == opposite_stat
                    and owner in possible_ally_targets(squad, candidate)
                    for candidate in squad.effects
                ):
                    return False
        return True

    @staticmethod
    def _charge_speed_bullet_lifetime_shape_supported(effect: "CompiledEffect") -> bool:
        """Certify one-shot self charge-speed state from burst cast."""
        if (
            effect.capability.disposition is not CapabilityDisposition.PLANNED
            or set(effect.capability.blockers) != {"field:duration_bullets"}
            or effect.effect_type != "buff"
            or (effect.stat or "") != "charge_speed_pct"
            or effect.target_spec.mode is not TargetMode.SELF
            or effect.duration not in (None, -1.0)
            or effect.condition_rules
            or set(effect.parameters) != {"duration_bullets"}
        ):
            return False
        max_stack = effect.max_stack if effect.max_stack is not None else 1.0
        if float(max_stack) != 1.0:
            return False
        try:
            bullets = float(effect.parameters["duration_bullets"])
        except (TypeError, ValueError):
            return False
        if bullets != 1.0:
            return False
        return (
            len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.EVENT
            and effect.triggers[0].event_key == "burst_cast"
        )

    @staticmethod
    def is_executable_effect(effect: "CompiledEffect") -> bool:
        stat = effect.stat or ""
        if TriggerDispatcher._charge_speed_bullet_lifetime_shape_supported(effect):
            return True
        if (
            TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported(effect)
            or TriggerDispatcher._periodic_finite_self_crit_shape_supported(effect)
            or TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(effect)
            or TriggerDispatcher._self_stack_reach_marker_shape_supported(effect)
            or TriggerDispatcher._timed_self_named_state_marker_shape_supported(effect)
            or TriggerDispatcher._named_event_control_shape_supported(effect)
            or TriggerDispatcher._named_duration_extend_shape_supported(effect)
            or TriggerDispatcher._on_attack_charge_speed_shape_supported(effect)
            or TriggerDispatcher._full_charge_hit_permanent_self_charge_speed_shape_supported(effect)
            or TriggerDispatcher._stat_applied_charge_speed_shape_supported(effect)
            or TriggerDispatcher._charge_overflow_conversion_shape_supported(effect)
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
            if key == "event:heal_received":
                if not self.heal_received_dependency_score_safe(self.squad, effect):
                    return False
                continue
            if self._stat_applied_event_stat(key) is not None:
                if not self.stat_applied_dependency_score_safe(self.squad, effect, key):
                    return False
                continue
            name = key[len("event:"):]
            providers = tuple(
                provider
                for provider in self._effect_table
                if provider.effect_id != effect.effect_id
                and provider.name == name
            )
            if not providers:
                return False
            for provider in providers:
                if provider.effect_type == "instant":
                    if (
                        provider.actor != effect.actor
                        or (provider.stat or "") != "ammo_charge_pct"
                        or provider.value is None
                        or float(provider.value) < 0.0
                        or any(rule.event_key == "battle_start" for rule in provider.triggers)
                        or not provider.target_spec.runtime_supported
                        or not possible_ally_targets(self.squad, provider)
                        or not self.is_executable_effect(provider)
                    ):
                        return False
                    continue
                if provider.effect_type != "buff":
                    return False
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
        if self._temporary_self_charge_weapon_change_runtime_supported(effect):
            return True
        if self._trigger_count_reduce_runtime_supported(effect):
            return True
        if self._enemy_named_stack_marker_runtime_supported(effect):
            return True
        if self._enemy_remove_named_state_runtime_supported(effect):
            return True
        family = self._gauge_family(effect)
        if (
            family is not None
            and family not in self._unsafe_gauge_families
            and self._gauge_shape_supported(effect)
        ):
            return True
        if self._timed_shield_shape_supported(effect):
            return True
        if self._self_stack_remove_runtime_supported(effect):
            return True
        if self._self_stack_heal_runtime_supported(effect):
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

    @staticmethod
    def _self_stack_conditional_passive_shape_supported(effect: "CompiledEffect") -> bool:
        """Certify sparse Moris-style permanent passives gated by self stacks.

        Moris registers these passives at battle start even while their condition
        is false, then gates their contribution as the referenced named stack
        changes. Fast materializes only the true intervals instead: stack-provider
        transitions are sparse weapon boundaries, so no frame polling is needed.
        """
        return (
            effect.effect_type == "buff"
            and effect.duration in (None, -1.0)
            and effect.max_stack in (None, 1, 1.0)
            and target_scope_is_static(effect.target_spec)
            and effect.target_spec.runtime_supported
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.EVENT
            and effect.triggers[0].raw == "passive"
            and bool(effect.condition_rules)
            and all(
                rule.mode is ConditionMode.SELF_STACK_AT_LEAST and bool(rule.key)
                for rule in effect.condition_rules
            )
        )

    @staticmethod
    def _self_state_conditional_passive_shape_supported(effect: "CompiledEffect") -> bool:
        """Certify permanent passives gated only by a named self-state edge."""
        return (
            effect.effect_type == "buff"
            and effect.duration in (None, -1.0)
            and effect.max_stack in (None, 1, 1.0)
            and target_scope_is_static(effect.target_spec)
            and effect.target_spec.runtime_supported
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.EVENT
            and effect.triggers[0].raw == "passive"
            and bool(effect.condition_rules)
            and all(
                rule.mode in {ConditionMode.SELF_STATE, ConditionMode.NOT_SELF_STATE}
                and bool(rule.key)
                for rule in effect.condition_rules
            )
        )

    def _sync_self_stack_conditional_passives(self, *, now: float) -> None:
        """Materialize/de-materialize certified conditional passives on stack edges."""
        for effect_id in self._self_stack_passive_ids:
            effect = self._effect_table[effect_id]
            named_target = (
                effect.target_spec.count
                if effect.target_spec.mode.value == "named_actor"
                else None
            )
            should_be_active = self.conditions.evaluate_all(
                effect.condition_rules,
                effect_id=effect.effect_id,
                owner_actor=effect.actor,
                target_actor=named_target,
                now=now,
                context=SignalContext(),
            )
            targets = self.targets.resolve(
                effect.target_spec,
                owner_actor=effect.actor,
                now=now,
            )
            is_active = self.effects.group_active(effect.effect_id, targets, now=now)
            if should_be_active and not is_active:
                # Moris False->True here is a condition-gating transition, not
                # a fresh trigger count or generic named-buff event broadcast.
                self.effects.activate_group(effect, targets, now, self.scheduler)
            elif not should_be_active and is_active:
                self.effects.deactivate_group(effect.effect_id, targets, now=now)

    def _sync_self_state_conditional_passives(self, *, now: float) -> None:
        """Materialize/de-materialize certified permanent passives on self-state edges."""
        for effect_id in self._self_state_passive_ids:
            effect = self._effect_table[effect_id]
            targets = self.targets.resolve(
                effect.target_spec,
                owner_actor=effect.actor,
                now=now,
            )
            should_be_active = self.conditions.evaluate_all(
                effect.condition_rules,
                effect_id=effect.effect_id,
                owner_actor=effect.actor,
                target_actor=None,
                now=now,
                context=SignalContext(),
            )
            is_active = self.effects.group_active(effect.effect_id, targets, now=now)
            if should_be_active and not is_active:
                self.effects.activate_group(effect, targets, now, self.scheduler)
            elif not should_be_active and is_active:
                self.effects.deactivate_group(effect.effect_id, targets, now=now)

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

    def _effective_reducible_threshold(
        self, effect: "CompiledEffect", base: int, *, now: float
    ) -> int:
        if base <= 0 or not effect.name:
            return base
        total = 0
        for reducer, active in self.effects.iter_stat("trigger_count_reduce", now=now):
            if (
                active.source_actor == effect.actor
                and active.target == effect.actor
                and reducer.parameters.get("target_effect") == effect.name
                and self._trigger_count_reduce_runtime_supported(reducer)
            ):
                total += int(float(reducer.value or 0.0))
        return max(1, int(base) - total)

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
            if rule.trigger_count_reducible:
                n = self._effective_reducible_threshold(effect, n, now=now)
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
                # Moris emits event:{name} after successful percent refill only.
                if (
                    stat == "ammo_charge_pct"
                    and effect.name
                    and effect.name in self._named_event_names_needed
                ):
                    from .burst import BurstSignal
                    self.dispatch(
                        BurstSignal(now, f"event:{effect.name}", effect.actor, effect.actor)
                    )
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
            elif stat == "remove_named_buff" and self._self_stack_remove_runtime_supported(effect):
                name = str(effect.parameters.get("target_effect") or "")
                if tuple(targets) != (effect.actor,):
                    return False
                removed = self.effects.remove_named_state(effect.actor, name, now=now)
                if removed and name in self._self_stack_dependency_names:
                    self._sync_self_stack_conditional_passives(now=now)
                if removed and name in self._self_state_dependency_names:
                    self._sync_self_state_conditional_passives(now=now)
            elif stat == "heal_hp_pct" and self._self_stack_heal_runtime_supported(effect):
                if tuple(targets) != (effect.actor,):
                    return False
                from .burst import BurstSignal
                self.dispatch(
                    BurstSignal(now, "event:heal_received", effect.actor, effect.actor)
                )
            elif stat == "remove_named_buff" and self._enemy_remove_named_state_runtime_supported(effect):
                name = str(effect.parameters.get("target_effect") or "")
                if tuple(targets) != (ENEMY,):
                    return False
                self.effects.remove_named_state(ENEMY, name, now=now)
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
            marker_stack_before = (
                self.effects.named_stack(effect.actor, effect.name or "", now=now)
                if self._self_stack_reach_marker_shape_supported(effect)
                else None
            )
            was_active = self.effects.group_active(effect.effect_id, targets, now=now)
            activated_group = self.effects.activate_group(effect, targets, now, self.scheduler)
            if activated_group and marker_stack_before is not None and effect.name:
                marker_stack_after = self.effects.named_stack(
                    effect.actor, effect.name, now=now
                )
                if marker_stack_after > marker_stack_before + 1e-9:
                    stack_int = int(round(marker_stack_after))
                    if abs(marker_stack_after - stack_int) <= 1e-9:
                        from .burst import BurstSignal
                        self.dispatch(
                            BurstSignal(
                                now,
                                f"stack_reach:{effect.name}:{stack_int}",
                                effect.actor,
                                effect.actor,
                            )
                        )
            if (
                activated_group
                and effect.name
                and effect.name in self._self_stack_dependency_names
            ):
                self._sync_self_stack_conditional_passives(now=now)
            if (
                activated_group
                and effect.name
                and effect.name in self._self_state_dependency_names
            ):
                self._sync_self_state_conditional_passives(now=now)
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
            stat_event_name = f"stat_applied:{stat}"
            if (
                activated_group
                and stat in _STAT_APPLIED_EVENT_STATS
                and stat_event_name in self._named_event_names_needed
            ):
                from .burst import BurstSignal
                for target in targets:
                    if target != ENEMY:
                        observer = int(target)
                        self.dispatch(
                            BurstSignal(now, f"event:{stat_event_name}", observer, observer)
                        )
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
        elif effect.effect_type == "weapon_change":
            if (
                not self._temporary_self_charge_weapon_change_runtime_supported(effect)
                or tuple(targets) != (effect.actor,)
            ):
                return False
            self.effects.activate_group(effect, targets, now, self.scheduler)
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
            weapon_hit_key = self.damage_sink.post_damage_weapon_hit_key(effect)
            if weapon_hit_key is not None:
                from .burst import BurstSignal
                self.dispatch(
                    BurstSignal(now, weapon_hit_key, effect.actor, effect.actor),
                    context=context,
                )
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
            removed = self.effects.consume_dynamic_bullet(owner, now=signal.time, count=1)
            if any(
                self._effect_table[effect_id].name in self._self_stack_dependency_names
                for effect_id in removed
            ):
                self._sync_self_stack_conditional_passives(now=signal.time)
            if any(
                self._effect_table[effect_id].name in self._self_state_dependency_names
                for effect_id in removed
            ):
                self._sync_self_state_conditional_passives(now=signal.time)
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
        if expired.name and expired.name in self._self_stack_dependency_names:
            self._sync_self_stack_conditional_passives(now=event.time)
        if expired.name and expired.name in self._self_state_dependency_names:
            self._sync_self_state_conditional_passives(now=event.time)

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
