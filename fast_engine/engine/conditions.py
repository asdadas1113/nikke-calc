from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isclose
from typing import TYPE_CHECKING

from .state import ENEMY, StateStore

if TYPE_CHECKING:
    from .burst import BurstMachine
    from .effects import ActiveEffectStore
    from .model import CompiledSquad, EnemyStaticProfile


class ConditionMode(str, Enum):
    DURING_CHARGE = "during_charge"
    DURING_FULL_BURST = "during_full_burst"
    NOT_DURING_FULL_BURST = "not_during_full_burst"
    BURST_CASTED = "burst_casted"
    BURST_NOT_CASTED = "burst_not_casted"
    SELF_STATE = "self_state"
    NOT_SELF_STATE = "not_self_state"
    TARGET_STATE = "target_state"
    NOT_TARGET_STATE = "not_target_state"
    SELF_STACK_AT_LEAST = "self_stack_at_least"
    TARGET_STACK_AT_LEAST = "target_stack_at_least"
    GAUGE_AT_LEAST = "gauge_at_least"
    GAUGE_BELOW = "gauge_below"
    GAUGE_EQUAL = "gauge_equal"
    GAUGE_MOD = "gauge_mod"
    SELF_HP_AT_LEAST = "self_hp_at_least"
    SELF_HP_AT_MOST = "self_hp_at_most"
    SELF_HP_MAX = "self_hp_max"
    ALLY_HP_AT_MOST = "ally_hp_at_most"
    TARGET_CODE = "target_code"
    ENEMY_COUNT_AT_MOST = "enemy_count_at_most"
    ENEMY_COUNT_AT_LEAST = "enemy_count_at_least"
    BACK_ROW = "back_row"
    SQUAD_ALLY_EXISTS = "squad_ally_exists"
    HAS_BURST1_ALLY = "has_burst1_ally"
    NO_BURST1_ALLY = "no_burst1_ally"
    HAS_DEFENDER_ALLY = "has_defender_ally"
    NO_DEFENDER_ALLY = "no_defender_ally"
    DURING_SHIELD = "during_shield"
    TARGET_STUNNED = "target_stunned"
    TRIGGER_HIT_CRIT = "trigger_hit_crit"
    PROBABILITY = "probability"
    CORE_HIT = "core_hit"
    SELF_STAT_ABOVE = "self_stat_above"
    MODEL_EXCLUDED = "model_excluded"
    SPECIAL = "special"


@dataclass(frozen=True, slots=True)
class ConditionRule:
    raw: str
    mode: ConditionMode
    key: str | None = None
    value: float | None = None
    value2: float | None = None

    @property
    def is_runtime_supported(self) -> bool:
        return self.mode not in {ConditionMode.MODEL_EXCLUDED, ConditionMode.SPECIAL, ConditionMode.SELF_STAT_ABOVE}


def _parts(raw: str, expected: int) -> list[str]:
    parts = raw.split(":")
    if len(parts) != expected:
        raise ValueError(f"invalid condition: {raw!r}")
    return parts


def compile_condition(raw: str, *, trigger_value: float | None = None) -> ConditionRule:
    raw = str(raw)
    exact = {
        "during_charge": ConditionMode.DURING_CHARGE,
        "during_full_burst": ConditionMode.DURING_FULL_BURST,
        "not_during_full_burst": ConditionMode.NOT_DURING_FULL_BURST,
        "burst_casted": ConditionMode.BURST_CASTED,
        "burst_not_casted": ConditionMode.BURST_NOT_CASTED,
        "self_hp_max": ConditionMode.SELF_HP_MAX,
        "back_row": ConditionMode.BACK_ROW,
        "squad_ally_exists": ConditionMode.SQUAD_ALLY_EXISTS,
        "has_burst1_ally": ConditionMode.HAS_BURST1_ALLY,
        "no_burst1_ally": ConditionMode.NO_BURST1_ALLY,
        "has_defender_ally": ConditionMode.HAS_DEFENDER_ALLY,
        "no_defender_ally": ConditionMode.NO_DEFENDER_ALLY,
        "during_shield": ConditionMode.DURING_SHIELD,
        "target_stunned": ConditionMode.TARGET_STUNNED,
        "trigger_hit_crit": ConditionMode.TRIGGER_HIT_CRIT,
        "core_hit": ConditionMode.CORE_HIT,
    }
    if raw in exact:
        return ConditionRule(raw, exact[raw])
    if raw in {"allies_cover_destroyed", "no_allies_cover_destroyed", "self_cover_destroyed"}:
        return ConditionRule(raw, ConditionMode.MODEL_EXCLUDED)
    if raw == "focusing":
        return ConditionRule(raw, ConditionMode.SPECIAL)

    for prefix, mode in (
        ("self_state:", ConditionMode.SELF_STATE),
        ("not_self_state:", ConditionMode.NOT_SELF_STATE),
        ("target_state:", ConditionMode.TARGET_STATE),
        ("not_target_state:", ConditionMode.NOT_TARGET_STATE),
    ):
        if raw.startswith(prefix):
            return ConditionRule(raw, mode, key=raw[len(prefix):])

    for prefix, mode in (
        ("self_hp_above:", ConditionMode.SELF_HP_AT_LEAST),
        ("self_hp_below:", ConditionMode.SELF_HP_AT_MOST),
        ("ally_hp_below:", ConditionMode.ALLY_HP_AT_MOST),
        ("enemy_count_below:", ConditionMode.ENEMY_COUNT_AT_MOST),
        ("enemy_count_above:", ConditionMode.ENEMY_COUNT_AT_LEAST),
    ):
        if raw.startswith(prefix):
            return ConditionRule(raw, mode, value=float(raw[len(prefix):]))

    for prefix, mode in (
        ("self_stack_above:", ConditionMode.SELF_STACK_AT_LEAST),
        ("target_stack_above:", ConditionMode.TARGET_STACK_AT_LEAST),
        ("gauge_above:", ConditionMode.GAUGE_AT_LEAST),
        ("gauge_below:", ConditionMode.GAUGE_BELOW),
        ("gauge_eq:", ConditionMode.GAUGE_EQUAL),
    ):
        if raw.startswith(prefix):
            body = raw[len(prefix):]
            key, threshold = body.rsplit(":", 1)
            return ConditionRule(raw, mode, key=key, value=float(threshold))

    if raw.startswith("gauge_mod:"):
        parts = _parts(raw, 4)
        return ConditionRule(raw, ConditionMode.GAUGE_MOD, key=parts[1], value=float(parts[2]), value2=float(parts[3]))
    if raw.startswith("target_code:"):
        return ConditionRule(raw, ConditionMode.TARGET_CODE, key=raw.split(":", 1)[1])
    if raw.startswith("prob:"):
        token = raw.split(":", 1)[1]
        if token == "{0}":
            if trigger_value is None:
                raise ValueError(f"probability placeholder has no trigger value: {raw!r}")
            p = float(trigger_value)
        else:
            p = float(token)
        return ConditionRule(raw, ConditionMode.PROBABILITY, value=p / 100.0)
    if raw.startswith("self_stat_above:"):
        parts = _parts(raw, 3)
        return ConditionRule(raw, ConditionMode.SELF_STAT_ABOVE, key=parts[1], value=float(parts[2]))
    raise ValueError(f"unknown Fast condition grammar: {raw!r}")


@dataclass(frozen=True, slots=True)
class SignalContext:
    hit_crit: bool = False
    core_hit: bool = False
    value: float | None = None


class ConditionEvaluator:
    __slots__ = ("squad", "state", "effects", "enemy", "burst", "_prob_acc")

    def __init__(
        self,
        squad: "CompiledSquad",
        state: StateStore,
        effects: "ActiveEffectStore",
        enemy: "EnemyStaticProfile",
        burst: "BurstMachine",
    ) -> None:
        self.squad = squad
        self.state = state
        self.effects = effects
        self.enemy = enemy
        self.burst = burst
        self._prob_acc: dict[tuple[int, int], float] = {}

    def evaluate_all(
        self,
        rules: tuple[ConditionRule, ...],
        *,
        effect_id: int,
        owner_actor: int,
        target_actor: int | None,
        now: float,
        context: SignalContext = SignalContext(),
    ) -> bool:
        return all(self.evaluate(rule, effect_id=effect_id, owner_actor=owner_actor,
                                 target_actor=target_actor, now=now, context=context)
                   for rule in rules)

    def _hp_pct(self, actor: int) -> float:
        base = self.squad.members[actor].base_hp
        return 100.0 if base <= 0 else 100.0 * self.state.actors[actor].hp / base

    def evaluate(
        self,
        rule: ConditionRule,
        *,
        effect_id: int,
        owner_actor: int,
        target_actor: int | None,
        now: float,
        context: SignalContext,
    ) -> bool:
        mode = rule.mode
        if mode is ConditionMode.DURING_CHARGE:
            return self.state.actors[owner_actor].counters.get("charging", 0.0) > 0
        if mode is ConditionMode.DURING_FULL_BURST:
            return self.burst.phase == "full_burst"
        if mode is ConditionMode.NOT_DURING_FULL_BURST:
            return self.burst.phase != "full_burst"
        if mode is ConditionMode.BURST_CASTED:
            actor = owner_actor if target_actor is None else target_actor
            return self.burst.casted[actor]
        if mode is ConditionMode.BURST_NOT_CASTED:
            actor = owner_actor if target_actor is None else target_actor
            return not self.burst.casted[actor]
        if mode is ConditionMode.SELF_STATE:
            return self.effects.has_named_state(owner_actor, rule.key or "", now=now)
        if mode is ConditionMode.NOT_SELF_STATE:
            return not self.effects.has_named_state(owner_actor, rule.key or "", now=now)
        if mode is ConditionMode.TARGET_STATE:
            return self.effects.has_named_state(ENEMY, rule.key or "", now=now)
        if mode is ConditionMode.NOT_TARGET_STATE:
            return not self.effects.has_named_state(ENEMY, rule.key or "", now=now)
        if mode is ConditionMode.SELF_STACK_AT_LEAST:
            return self.effects.named_stack(owner_actor, rule.key or "", now=now) >= (rule.value or 0.0)
        if mode is ConditionMode.TARGET_STACK_AT_LEAST:
            return self.effects.named_stack(ENEMY, rule.key or "", now=now) >= (rule.value or 0.0)
        if mode in {ConditionMode.GAUGE_AT_LEAST, ConditionMode.GAUGE_BELOW, ConditionMode.GAUGE_EQUAL, ConditionMode.GAUGE_MOD}:
            current = self.state.actors[owner_actor].gauges.get(rule.key or "", 0.0)
            if mode is ConditionMode.GAUGE_AT_LEAST:
                return current >= (rule.value or 0.0)
            if mode is ConditionMode.GAUGE_BELOW:
                return current < (rule.value or 0.0)
            if mode is ConditionMode.GAUGE_EQUAL:
                return isclose(current, rule.value or 0.0, abs_tol=1e-9)
            mod = int(rule.value or 1)
            return mod > 0 and int(current) % mod == int(rule.value2 or 0)
        if mode is ConditionMode.SELF_HP_AT_LEAST:
            return self._hp_pct(owner_actor) >= (rule.value or 0.0)
        if mode is ConditionMode.SELF_HP_AT_MOST:
            return self._hp_pct(owner_actor) <= (rule.value or 0.0)
        if mode is ConditionMode.SELF_HP_MAX:
            return self._hp_pct(owner_actor) >= 100.0 - 1e-6
        if mode is ConditionMode.ALLY_HP_AT_MOST:
            return min(self._hp_pct(i) for i in range(len(self.squad.members))) <= (rule.value or 0.0)
        if mode is ConditionMode.TARGET_CODE:
            return not self.enemy.element or self.enemy.element == rule.key
        if mode is ConditionMode.ENEMY_COUNT_AT_MOST:
            return 1 <= int(rule.value or 0)
        if mode is ConditionMode.ENEMY_COUNT_AT_LEAST:
            return 1 >= int(rule.value or 0)
        if mode is ConditionMode.BACK_ROW:
            return owner_actor in {1, 3}
        if mode is ConditionMode.SQUAD_ALLY_EXISTS:
            group = self.squad.members[owner_actor].squad_group
            return bool(group) and any(i != owner_actor and m.squad_group == group for i, m in enumerate(self.squad.members))
        if mode in {ConditionMode.HAS_BURST1_ALLY, ConditionMode.NO_BURST1_ALLY}:
            has = any(i != owner_actor and self.burst.stage_for(i) == "1" for i in range(len(self.squad.members)))
            return has if mode is ConditionMode.HAS_BURST1_ALLY else not has
        if mode in {ConditionMode.HAS_DEFENDER_ALLY, ConditionMode.NO_DEFENDER_ALLY}:
            has = any(i != owner_actor and m.character_class == "방어형" for i, m in enumerate(self.squad.members))
            return has if mode is ConditionMode.HAS_DEFENDER_ALLY else not has
        if mode is ConditionMode.DURING_SHIELD:
            return self.state.actors[owner_actor].shield > 0.0
        if mode is ConditionMode.TARGET_STUNNED:
            return self.effects.has_stat(ENEMY, "stun", now=now)
        if mode is ConditionMode.TRIGGER_HIT_CRIT:
            return context.hit_crit
        if mode is ConditionMode.CORE_HIT:
            return context.core_hit
        if mode is ConditionMode.PROBABILITY:
            p = min(max(rule.value or 0.0, 0.0), 1.0)
            key = (effect_id, owner_actor)
            total = self._prob_acc.get(key, 0.0) + p
            if total + 1e-12 < 1.0:
                self._prob_acc[key] = total
                return False
            self._prob_acc[key] = total - 1.0
            return True
        # self_stat_above requires the future resolved-buff snapshot; cover/focusing
        # are outside the patternless initial model. Do not guess.
        return False
