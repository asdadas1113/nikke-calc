from __future__ import annotations

from typing import TYPE_CHECKING

from .conditions import SignalContext
from .damage_events import DamageEventSpec, compile_simple_damage_event, expected_damage_event
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
    """First score-runtime bridge for fail-closed immediate damage effects.

    The sink precompiles supported damage effects once. During combat activation
    is one cached DamageTerms lookup + one expected DealForm × hit_count; no
    HitEvent objects are created. Effects with downstream named-hit semantics or
    coefficient magnifiers remain unsupported until those chains are implemented.
    """

    __slots__ = (
        "squad", "enemy", "specs", "unsupported_effect_ids", "char_total",
        "runtime", "resolver",
    )

    def __init__(self, squad: "CompiledSquad", enemy: "EnemyStaticProfile") -> None:
        self.squad = squad
        self.enemy = enemy
        self.specs: dict[int, DamageEventSpec] = {}
        self.unsupported_effect_ids: set[int] = set()
        self.char_total = [0.0] * len(squad.members)
        self.runtime: "BurstRuntime | None" = None
        self.resolver: DamageTermResolver | None = None

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
            if spec is None or not self._delivery_supported(effect):
                self.unsupported_effect_ids.add(effect.effect_id)
                continue
            if effect.name and (
                f"hit_count:{effect.name}" in downstream_keys
                or f"weapon_hit:{effect.name}" in downstream_keys
                or effect.name in scaled_names
            ):
                self.unsupported_effect_ids.add(effect.effect_id)
                continue
            self.specs[effect.effect_id] = spec

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
        return effect.effect_id in self.specs

    def attach(self, runtime: "BurstRuntime") -> None:
        self.runtime = runtime
        self.resolver = DamageTermResolver(
            runtime.squad,
            runtime.dispatcher.effects,
            runtime.state,
            runtime.enemy,
        )

    def activate(
        self,
        effect: "CompiledEffect",
        *,
        now: float,
        targets: tuple[int, ...],
        context: SignalContext,
    ) -> bool:
        del context  # reserved for future crit/core trigger chaining
        spec = self.specs.get(effect.effect_id)
        runtime = self.runtime
        resolver = self.resolver
        if spec is None or runtime is None or resolver is None:
            return False
        if ENEMY not in targets:
            return False

        actor = effect.actor
        terms = resolver.resolve(actor, now=now)
        self.char_total[actor] += expected_damage_event(
            spec,
            runtime.squad.members[actor],
            runtime.enemy,
            terms,
            full_burst=runtime.machine.phase == "full_burst",
        )
        return True

    @property
    def supported_count(self) -> int:
        return len(self.specs)

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported_effect_ids)
