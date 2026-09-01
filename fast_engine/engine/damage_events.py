from __future__ import annotations

from dataclasses import dataclass, replace

from .damage import DamageTerms, HitSpec, expected_damage
from .model import CompiledCharacter, CompiledEffect, EnemyStaticProfile


@dataclass(frozen=True, slots=True)
class DamageEventSpec:
    """One scoreable damage shape with compile-time hit semantics.

    Several physical hits may share one spec. Fast evaluates the deterministic
    DealForm once per cache-valid state and multiplies by ``hit_count`` instead
    of allocating one HitEvent per hit. Runtime-scaled variants keep their live
    multiplier in a separate wrapper rather than mutating this immutable shape.
    """

    effect_id: int
    name: str
    hit_count: int
    hit: HitSpec
    normal_formula: bool = False


@dataclass(frozen=True, slots=True)
class StackCountDamageSpec:
    """Immediate non-DoT damage whose Moris hit count comes from one gauge.

    Moris treats ``scaling: stack_count`` differently for direct damage and DoT:
    direct damage repeats the physical hit ``ref_count`` times, while DoT scales
    the per-tick coefficient. This wrapper is deliberately only the former.
    """

    damage: DamageEventSpec
    ref: str


@dataclass(frozen=True, slots=True)
class FixedDotSpec:
    """Finite, fixed-coefficient periodic damage timer.

    The timer itself is runtime state; the damage shape stays immutable and can
    reuse the same expected-value kernel as immediate damage. Complex DoT ramps,
    stack scaling and infinite/removal-coupled lifetimes deliberately remain out
    of this first slice.
    """

    damage: DamageEventSpec
    interval: float
    duration: float
    immediate: bool


_SUPPORTED_BASE_STATS = frozenset({
    "damage",
    "bonus_damage",
    "burst_damage",
    "pierce_damage",
    "armor_break_damage",
    "core_damage",
    "dot_damage",
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
    allow_tick_interval: bool = False,
    allowed_dynamic_parameter_keys: frozenset[str] = frozenset(),
) -> DamageEventSpec | None:
    if effect.effect_type != "damage" or effect.value is None:
        return None
    if effect.tick_interval is not None and not allow_tick_interval:
        return None

    params = effect.parameters
    dynamic_keys = {
        key for key in _UNSAFE_DYNAMIC_PARAMETER_KEYS if key in params
    }
    if not dynamic_keys.issubset(allowed_dynamic_parameter_keys):
        return None
    if params.get("tick_start") is not None and not allow_tick_interval:
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
        is_dot=base_stat == "dot_damage",
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


def compile_stack_count_damage_event(
    effect: CompiledEffect,
    character: CompiledCharacter,
) -> StackCountDamageSpec | None:
    """Lower Moris' non-DoT ``scaling:stack_count`` hit-repeat primitive.

    This first slice accepts exactly one unsuffixed immediate damage stat whose
    repeat count is read from ``scaling_ref``. Named-stack/DoT semantics remain
    separate; runtime additionally requires the ref to be a certified Fast gauge
    family before the effect is considered supported.
    """

    if effect.effect_type != "damage" or effect.tick_interval is not None:
        return None
    params = effect.parameters
    if params.get("scaling") != "stack_count":
        return None
    ref = params.get("scaling_ref")
    if not isinstance(ref, str) or not ref:
        return None
    stat = effect.stat or "damage"
    if ":" in stat or stat.split(":", 1)[0] == "dot_damage":
        # Moris gives explicit stat suffixes precedence over stack_count when
        # choosing hit_count. Do not multiply both interpretations together.
        return None

    damage = _compile_damage_event(
        effect,
        character,
        allow_pending_b3_bonus=False,
        allowed_dynamic_parameter_keys=frozenset({"scaling", "scaling_ref"}),
    )
    if damage is None or damage.hit.is_dot:
        return None
    return StackCountDamageSpec(damage=damage, ref=ref)


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


def compile_fixed_dot_damage_event(
    effect: CompiledEffect,
    character: CompiledCharacter,
) -> FixedDotSpec | None:
    """Lower the first safe periodic-damage slice.

    Supported here means exactly: ``dot_damage`` with a positive fixed interval,
    finite positive duration, one non-scaling stack, and either Moris' default
    delayed first tick or ``tick_start: immediate``. DoT state dependencies,
    same-target ramps, infinite/remove-coupled lifetimes and dynamic coefficient
    scaling stay fail-closed in the runtime sink.
    """

    if effect.effect_type != "damage" or effect.tick_interval is None:
        return None
    stat = effect.stat or ""
    if stat.split(":", 1)[0] != "dot_damage":
        return None
    interval = float(effect.tick_interval)
    duration = effect.duration
    if interval <= 0.0 or duration is None or float(duration) <= 0.0:
        return None
    if float(duration) == -1.0:
        return None
    if effect.max_stack not in (None, 1, 1.0):
        return None

    tick_start = effect.parameters.get("tick_start")
    if tick_start not in (None, "immediate"):
        return None
    if effect.parameters.get("ramp_interval") is not None:
        return None

    damage = _compile_damage_event(
        effect,
        character,
        allow_pending_b3_bonus=False,
        allow_tick_interval=True,
    )
    if damage is None or not damage.hit.is_dot:
        return None
    return FixedDotSpec(
        damage=damage,
        interval=interval,
        duration=float(duration),
        immediate=tick_start == "immediate",
    )


def expected_damage_event(
    spec: DamageEventSpec,
    character: CompiledCharacter,
    enemy: EnemyStaticProfile,
    terms: DamageTerms,
    *,
    full_burst: bool,
    hit_count: int | None = None,
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
    count = spec.hit_count if hit_count is None else max(0, int(hit_count))
    return per_hit * count
