from __future__ import annotations

from dataclasses import dataclass
from math import inf, nextafter
from typing import TYPE_CHECKING

from .conditions import SignalContext
from .core_events import is_static_expected_core_count_rule
from .damage_events import (
    DamageEventSpec,
    FixedDotSpec,
    compile_fixed_dot_damage_event,
    compile_pending_b3_bonus_damage_event,
    compile_simple_damage_event,
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


# Event sources that BurstRuntime currently produces exactly. Periodic has no
# event_key and is checked by TriggerMode below.
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
_DOT_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class DotTickToken:
    effect_id: int
    generation: int
    expires_at: float


class SimpleDamageScoreSink:
    """Score fail-closed immediate, pending-B3 and fixed periodic damage.

    Immediate damage is one cached DamageTerms lookup + one expected DealForm ×
    hit_count. Delayed B3 bonus damage is queued until full-burst entry. The first
    DoT slice schedules only its meaningful damage ticks: no frame loop and no
    per-frame polling. Reactivation invalidates old reservations by generation.

    Source-order-sensitive B3 cases and state-observable/stack-scaled DoTs remain
    unsupported until their distinct semantics are explicitly compiled.
    """

    __slots__ = (
        "squad", "enemy", "specs", "pending_specs", "dot_specs",
        "unsupported_effect_ids", "char_total", "runtime", "resolver",
        "_pending_effect_ids", "_effect_actor", "_dot_generation",
    )

    def __init__(self, squad: "CompiledSquad", enemy: "EnemyStaticProfile") -> None:
        self.squad = squad
        self.enemy = enemy
        self.specs: dict[int, DamageEventSpec] = {}
        self.pending_specs: dict[int, DamageEventSpec] = {}
        self.dot_specs: dict[int, FixedDotSpec] = {}
        self.unsupported_effect_ids: set[int] = set()
        self.char_total = [0.0] * len(squad.members)
        self.runtime: "BurstRuntime | None" = None
        self.resolver: DamageTermResolver | None = None
        self._pending_effect_ids: list[int] = []
        self._effect_actor = {
            effect.effect_id: effect.actor for effect in squad.effects
        }
        self._dot_generation: dict[int, int] = {}

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
            if spec is None:
                pending = compile_pending_b3_bonus_damage_event(
                    effect, squad.members[effect.actor]
                )
            if spec is None and pending is None:
                dot = compile_fixed_dot_damage_event(
                    effect, squad.members[effect.actor]
                )

            if (
                (spec is None and pending is None and dot is None)
                or not self._delivery_supported(effect)
            ):
                self.unsupported_effect_ids.add(effect.effect_id)
                continue
            if effect.name and (
                f"hit_count:{effect.name}" in downstream_keys
                or f"weapon_hit:{effect.name}" in downstream_keys
                or effect.name in scaled_names
            ):
                self.unsupported_effect_ids.add(effect.effect_id)
                continue

            if pending is not None:
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

    def _has_later_same_actor_burst_cast_buff(self, effect: "CompiledEffect") -> bool:
        """Conservatively guard Moris' source-order exclusion rule.

        Moris records names of later same-skill ``burst_cast`` buffs and excludes
        them while firing the delayed B3 hit. Fast has no compiled exclusion mask
        yet, so rejecting any later same-actor burst-cast buff is deliberately
        broader but cannot over-credit the hit.
        """
        return any(
            other.actor == effect.actor
            and other.actor_effect_index > effect.actor_effect_index
            and other.effect_type == "buff"
            and any(rule.raw == "burst_cast" for rule in other.triggers)
            for other in self.squad.effects
        )

    def _dot_state_is_observed(self, effect: "CompiledEffect") -> bool:
        """Reject DoTs whose active debuff identity is part of other mechanics.

        Moris registers periodic damage in ActiveBuff as well as in its timer map.
        This first Fast slice intentionally models only damage/timer semantics, so
        any mechanic that reads/removes that named state must remain fail-closed.
        """
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

    @staticmethod
    def _delivery_supported(effect: "CompiledEffect") -> bool:
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
                return False
            if rule.event_key == "core_hit" and not is_static_expected_core_count_rule(rule):
                return False
        return True

    def supports(self, effect: "CompiledEffect") -> bool:
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
        dot = self.dot_specs.get(effect_id)
        return None if dot is None else dot.damage

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
        terms = resolver.resolve(actor, now=now)
        self.char_total[actor] += expected_damage_event(
            spec,
            runtime.squad.members[actor],
            runtime.enemy,
            terms,
            full_burst=full_burst,
        )
        return True

    @staticmethod
    def _dot_tick_allowed(spec: FixedDotSpec, tick_t: float, expires_at: float) -> bool:
        if spec.immediate:
            return tick_t < expires_at - _DOT_EPS
        return tick_t <= expires_at + _DOT_EPS

    def _activate_dot(self, effect_id: int, *, now: float) -> bool:
        spec = self.dot_specs.get(effect_id)
        runtime = self.runtime
        actor = self._effect_actor.get(effect_id)
        if spec is None or runtime is None or actor is None:
            return False

        generation = self._dot_generation.get(effect_id, 0) + 1
        self._dot_generation[effect_id] = generation
        expires_at = float(now) + spec.duration
        first_t = float(now) if spec.immediate else float(now) + spec.interval
        if self._dot_tick_allowed(spec, first_t, expires_at):
            runtime.scheduler.schedule(
                first_t,
                EventKind.DAMAGE_TICK,
                actor=actor,
                payload=DotTickToken(effect_id, generation, expires_at),
            )
        return True

    def activate(
        self,
        effect: "CompiledEffect",
        *,
        now: float,
        targets: tuple[int, ...],
        context: SignalContext,
    ) -> bool:
        del context  # reserved for future crit/core trigger chaining
        if ENEMY not in targets:
            return False

        if effect.effect_id in self.pending_specs:
            # Moris postpones B3 bonus damage until the full-burst entry event.
            # Preserve duplicate activations if future burst patterns legitimately
            # produce more than one pending cast before entry.
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
        """Score one current DoT timer boundary and reserve its next tick."""
        token = event.payload
        if not isinstance(token, DotTickToken):
            return False
        spec = self.dot_specs.get(token.effect_id)
        runtime = self.runtime
        if spec is None or runtime is None:
            return False
        if self._dot_generation.get(token.effect_id) != token.generation:
            return False
        if not self._dot_tick_allowed(spec, event.time, token.expires_at):
            return False

        # Moris type-2 DoT includes the tick exactly at expiry but evaluates it
        # with the immediately-pre-expiry buff state. Event ordering alone is not
        # sufficient because DamageTermResolver excludes t >= expires_at buffs.
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
        """Fire queued B3 bonus damage after full-burst-start state is active."""
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
        return len(self.specs) + len(self.pending_specs) + len(self.dot_specs)

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported_effect_ids)
