from __future__ import annotations

from typing import TYPE_CHECKING

from .conditions import SignalContext
from .damage_events import (
    DamageEventSpec,
    compile_pending_b3_bonus_damage_event,
    compile_simple_damage_event,
    expected_damage_event,
)
from .damage_state import DamageTermResolver
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
    "pellet_hit",
    "burst_enter:1",
    "burst_enter:2",
    "burst_enter:3",
    "squad_burst_cast:1",
    "squad_burst_cast:2",
    "squad_burst_cast:3",
})


class SimpleDamageScoreSink:
    """Score fail-closed immediate and first pending B3 damage primitives.

    Supported immediate damage is one cached DamageTerms lookup + one expected
    DealForm × hit_count; no HitEvent objects are created. The first delayed
    primitive mirrors Moris B3 ``burst_cast`` bonus damage by queueing at cast
    and evaluating only after ``full_burst_start`` buffs have been dispatched.

    Source-order-sensitive B3 cases remain unsupported: if any later same-caster
    ``burst_cast`` buff exists, Moris excludes it from the delayed damage and
    Fast refuses the effect until explicit exclusion masks are compiled.
    """

    __slots__ = (
        "squad", "enemy", "specs", "pending_specs", "unsupported_effect_ids",
        "char_total", "runtime", "resolver", "_pending_effect_ids",
    )

    def __init__(self, squad: "CompiledSquad", enemy: "EnemyStaticProfile") -> None:
        self.squad = squad
        self.enemy = enemy
        self.specs: dict[int, DamageEventSpec] = {}
        self.pending_specs: dict[int, DamageEventSpec] = {}
        self.unsupported_effect_ids: set[int] = set()
        self.char_total = [0.0] * len(squad.members)
        self.runtime: "BurstRuntime | None" = None
        self.resolver: DamageTermResolver | None = None
        self._pending_effect_ids: list[int] = []

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
            if spec is None:
                pending = compile_pending_b3_bonus_damage_event(
                    effect, squad.members[effect.actor]
                )

            if (spec is None and pending is None) or not self._delivery_supported(effect):
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
        return True

    def supports(self, effect: "CompiledEffect") -> bool:
        return effect.effect_id in self.specs or effect.effect_id in self.pending_specs

    def attach(self, runtime: "BurstRuntime") -> None:
        self.runtime = runtime
        self.resolver = DamageTermResolver(
            runtime.squad,
            runtime.dispatcher.effects,
            runtime.state,
            runtime.enemy,
        )

    def _score_spec(self, effect_id: int, *, now: float, full_burst: bool) -> bool:
        spec = self.specs.get(effect_id) or self.pending_specs.get(effect_id)
        runtime = self.runtime
        resolver = self.resolver
        if spec is None or runtime is None or resolver is None:
            return False
        effect = runtime.squad.effects[effect_id]
        actor = effect.actor
        terms = resolver.resolve(actor, now=now)
        self.char_total[actor] += expected_damage_event(
            spec,
            runtime.squad.members[actor],
            runtime.enemy,
            terms,
            full_burst=full_burst,
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

        return self._score_spec(
            effect.effect_id,
            now=now,
            full_burst=bool(self.runtime and self.runtime.machine.phase == "full_burst"),
        )

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
        return len(self.specs) + len(self.pending_specs)

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported_effect_ids)
