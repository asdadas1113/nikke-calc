from __future__ import annotations

from dataclasses import dataclass, replace

from .damage import DamageTerms, HitSpec, expected_damage
from .model import CompiledCharacter, CompiledEffect, EnemyStaticProfile


@dataclass(frozen=True, slots=True)
class DamageEventSpec:
    """One compile-time scoreable damage effect without dynamic scaling/ticks.

    Several physical hits may share one spec. Fast evaluates the deterministic
    DealForm once per cache-valid state and multiplies by ``hit_count`` instead
    of allocating one HitEvent per hit.
    """

    effect_id: int
    name: str
    hit_count: int
    hit: HitSpec
    normal_formula: bool = False


_SUPPORTED_BASE_STATS = frozenset({
    "damage",
    "bonus_damage",
    "burst_damage",
    "pierce_damage",
    "armor_break_damage",
    "core_damage",
    "projectile_explosion_damage",
    "projectile_attachment_damage",
    "sequential_damage",
    "split_damage",
})
_UNSAFE_DYNAMIC_PARAMETER_KEYS = frozenset({
    "scaling",
    "scaling_ref",
    "hit_count_gauge_ref",
    "scaling_hp_pct",
})


def _compile_damage_event(
    effect: CompiledEffect,
    character: CompiledCharacter,
    *,
    allow_pending_b3_bonus: bool,
) -> DamageEventSpec | None:
    if effect.effect_type != "damage" or effect.value is None:
        return None
    if effect.tick_interval is not None:
        return None

    params = effect.parameters
    if any(key in params for key in _UNSAFE_DYNAMIC_PARAMETER_KEYS):
        return None
    if params.get("tick_start") is not None:
        return None
    if params.get("hits_parts"):
        # The initial EnemyStaticProfile does not yet carry part-presence state.
        return None

    raw_target = effect.target
    if raw_target == "all_projectiles":
        return None
    if isinstance(raw_target, str) and raw_target.startswith("same_target:"):
        return None

    stat = effect.stat or "damage"
    parts = stat.split(":", 1)
    base_stat = parts[0]
    if base_stat not in _SUPPORTED_BASE_STATS:
        return None

    hit_count = 1
    if len(parts) == 2:
        raw_hits = parts[1]
        if not raw_hits.lstrip("-").isdigit():
            return None
        hit_count = int(raw_hits)
        if hit_count <= 0:
            return None

    # Moris delays only the *exact* stat ``bonus_damage`` for a B3 burst cast.
    # Numeric variants such as ``bonus_damage:5`` stay immediate multi-hit
    # damage and must not enter the pending full-burst lane.
    is_pending_b3_bonus = (
        stat == "bonus_damage"
        and character.burst_stage == "3"
        and any(rule.raw == "burst_cast" for rule in effect.triggers)
    )
    if is_pending_b3_bonus and not allow_pending_b3_bonus:
        return None

    normal_formula = params.get("damage_formula") == "normal_attack"
    is_core_damage = base_stat == "core_damage"
    is_projectile_explosion = (
        base_stat == "projectile_explosion_damage"
        or (normal_formula and character.weapon_type == "RL")
    )

    hit = HitSpec(
        coeff=float(effect.value),
        is_normal_atk=normal_formula,
        core_prob=1.0 if is_core_damage else 0.0,
        is_core_damage=is_core_damage,
        is_burst_damage=base_stat == "burst_damage",
        is_aoe_burst=(
            base_stat == "burst_damage" and raw_target == "all_enemies"
        ),
        is_pierce_damage=base_stat == "pierce_damage",
        is_armor_break_damage=base_stat == "armor_break_damage",
        is_projectile_explosion=is_projectile_explosion,
        is_projectile_attachment=base_stat == "projectile_attachment_damage",
        is_sequential=base_stat == "sequential_damage",
        is_split=base_stat == "split_damage",
    )
    return DamageEventSpec(
        effect_id=effect.effect_id,
        name=effect.name,
        hit_count=hit_count,
        hit=hit,
        normal_formula=normal_formula,
    )


def compile_simple_damage_event(
    effect: CompiledEffect,
    character: CompiledCharacter,
) -> DamageEventSpec | None:
    """Lower immediate damage whose coefficient/hit count is compile-time fixed.

    B3 ``burst_cast`` bonus damage deliberately stays out of this lane because
    Moris delays it until full-burst entry. Use
    :func:`compile_pending_b3_bonus_damage_event` for that distinct primitive.
    """

    return _compile_damage_event(
        effect,
        character,
        allow_pending_b3_bonus=False,
    )


def compile_pending_b3_bonus_damage_event(
    effect: CompiledEffect,
    character: CompiledCharacter,
) -> DamageEventSpec | None:
    """Lower the fixed-coefficient subset of Moris' delayed B3 bonus damage.

    This function only establishes the damage shape. Runtime still has to prove
    source-order safety before accepting it: later same-caster ``burst_cast``
    buffs are excluded by Moris from the delayed hit and therefore remain a
    fail-closed blocker in ``SimpleDamageScoreSink``.
    """

    if (effect.stat or "") != "bonus_damage":
        return None
    if character.burst_stage != "3":
        return None
    if not any(rule.raw == "burst_cast" for rule in effect.triggers):
        return None
    return _compile_damage_event(
        effect,
        character,
        allow_pending_b3_bonus=True,
    )


def expected_damage_event(
    spec: DamageEventSpec,
    character: CompiledCharacter,
    enemy: EnemyStaticProfile,
    terms: DamageTerms,
    *,
    full_burst: bool,
) -> float:
    """Score a simple damage effect in one DealForm call × aggregated hit count."""

    core_prob = spec.hit.core_prob
    if spec.normal_formula and not spec.hit.is_core_damage:
        core_prob = enemy.effective_core_rate
    hit = replace(
        spec.hit,
        core_prob=core_prob,
        is_full_burst=bool(full_burst),
    )
    per_hit = expected_damage(
        base_atk=character.base_atk,
        enemy_def=enemy.defense,
        core_dmg_mult=float(character.weapon.get("core_dmg_mult", 200.0)),
        full_charge_mult=float(character.weapon.get("full_charge_mult", 100.0)),
        terms=terms,
        hit=hit,
    )
    return per_hit * spec.hit_count
