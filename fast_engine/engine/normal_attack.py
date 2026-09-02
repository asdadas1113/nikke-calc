from __future__ import annotations

from dataclasses import dataclass

from .damage import DamageTerms, HitSpec, expected_damage
from .model import CompiledCharacter
from .weapon import compile_static_cadence_modifiers, _round_half_up


@dataclass(frozen=True, slots=True)
class NormalAttackSpec:
    """Compile-time normal-attack shape for score-only aggregation."""

    coeff_per_hit: float
    hits_per_shot: int
    core_dmg_mult: float
    full_charge_mult: float
    normal_hit_coeff: float
    is_full_charge: bool
    is_projectile_explosion: bool


def compile_normal_attack_spec(character: CompiledCharacter) -> NormalAttackSpec:
    """Lower one compiled weapon to a branch-light normal attack descriptor.

    SG total coefficient is split across pellets exactly like Moris. Muzzles
    multiply hit count but do not divide the coefficient again. Permanent
    battle-start pellet modifiers are folded here; live pellet changes are a
    future state dependency and must not silently use this static descriptor.

    Moris marks ordinary RL shots as projectile-explosion damage for factor-5
    buff routing, so Fast carries that weapon-type fact explicitly as well.
    """

    weapon = character.weapon
    mods = compile_static_cadence_modifiers(character)
    if mods.pellet_count_fixed > 0:
        pellets = max(1, _round_half_up(mods.pellet_count_fixed))
    else:
        pellets = max(
            1,
            int(weapon.get("pellets", 1)) + _round_half_up(mods.pellet_count),
        )
    muzzles = max(1, int(weapon.get("muzzles", 1)))
    hits_per_shot = pellets * muzzles
    total_coeff = float(weapon.get("damage_coeff", 0.0))
    coeff_per_hit = total_coeff / pellets if pellets > 1 else total_coeff
    weapon_type = str(weapon.get("weapon_type") or character.weapon_type or "")

    return NormalAttackSpec(
        coeff_per_hit=coeff_per_hit,
        hits_per_shot=hits_per_shot,
        core_dmg_mult=float(weapon.get("core_dmg_mult", 200.0)),
        full_charge_mult=float(weapon.get("full_charge_mult", 100.0)),
        normal_hit_coeff=float(weapon.get("normal_hit_coeff", 1.0)),
        is_full_charge=str(weapon.get("fire_mode") or "") == "charge",
        is_projectile_explosion=weapon_type == "RL",
    )


def expected_normal_shot_damage(
    spec: NormalAttackSpec,
    *,
    base_atk: float,
    enemy_def: float,
    terms: DamageTerms,
    core_prob: float,
    is_full_burst: bool = False,
    is_optimal_range: bool = False,
) -> float:
    """Expected total damage from one trigger pull / charge release.

    All pellets/muzzles share the same expected DealForm under Fast's static
    target model, so linearity lets the engine evaluate one representative hit
    and multiply by ``hits_per_shot``. This avoids per-pellet work while matching
    Moris expectation except for intentionally omitted per-hit integer rounding.
    """

    per_hit = expected_damage(
        base_atk=base_atk,
        enemy_def=enemy_def,
        core_dmg_mult=spec.core_dmg_mult,
        full_charge_mult=spec.full_charge_mult,
        terms=terms,
        hit=HitSpec(
            coeff=spec.coeff_per_hit,
            is_normal_atk=True,
            core_prob=core_prob,
            is_full_burst=is_full_burst,
            is_optimal_range=is_optimal_range,
            is_full_charge=spec.is_full_charge,
            is_pierce_damage=terms.pierce_enabled,
            is_armor_break_damage=terms.armor_break_enabled,
            is_projectile_explosion=spec.is_projectile_explosion,
        ),
    )
    return per_hit * spec.hits_per_shot * spec.normal_hit_coeff


def expected_normal_block_damage(
    spec: NormalAttackSpec,
    *,
    shot_count: int,
    base_atk: float,
    enemy_def: float,
    terms: DamageTerms,
    core_prob: float,
    is_full_burst: bool = False,
    is_optimal_range: bool = False,
) -> float:
    """Score N identical shots with one DealForm evaluation."""

    if shot_count <= 0:
        return 0.0
    return expected_normal_shot_damage(
        spec,
        base_atk=base_atk,
        enemy_def=enemy_def,
        terms=terms,
        core_prob=core_prob,
        is_full_burst=is_full_burst,
        is_optimal_range=is_optimal_range,
    ) * shot_count
