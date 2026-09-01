from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DamageTerms:
    """Resolved numeric damage state for one cache-valid interval.

    No parsed effect strings or dictionaries belong in the hot damage path.
    A future derived-state resolver builds this once per relevant state-version
    change, then many identical hits can reuse it.
    """

    atk_pct: float = 0.0
    atk_flat: float = 0.0
    enemy_def_down_pct: float = 0.0
    def_ignore_pct: float = 0.0

    crit_rate: float = 0.15
    crit_dmg: float = 0.0
    crit_rate_skill: float | None = None
    crit_dmg_skill: float | None = None
    core_dmg_pct: float = 0.0
    accuracy_pct: float = 0.0

    normal_atk_dmg_pct: float = 0.0
    atk_dmg_pct: float = 0.0
    burst_dmg_pct: float = 0.0
    burst_dmg_aoe_pct: float = 0.0
    pierce_dmg_pct: float = 0.0
    armor_break_dmg_pct: float = 0.0
    pierce_enabled: bool = False
    armor_break_enabled: bool = False
    dot_dmg_pct: float = 0.0
    projectile_explosion_dmg_pct: float = 0.0
    projectile_attachment_dmg_pct: float = 0.0
    sequential_dmg_pct: float = 0.0
    part_dmg_pct: float = 0.0

    charge_dmg_pct: float = 0.0
    charge_dmg_mag_pct: float = 0.0
    received_dmg_pct: float = 0.0
    split_dmg_pct: float = 0.0

    element_bonus_pct: float = 0.0
    element_match: bool = False


@dataclass(frozen=True, slots=True)
class HitSpec:
    """Compile-time hit semantics; expected-value only by Fast policy."""

    coeff: float
    is_normal_atk: bool = True
    core_prob: float = 0.0
    is_core_damage: bool = False
    is_weapon_mode_skill: bool = False
    is_full_burst: bool = False
    is_optimal_range: bool = False
    is_full_charge: bool = False
    is_burst_damage: bool = False
    is_aoe_burst: bool = False
    is_pierce_damage: bool = False
    is_armor_break_damage: bool = False
    is_dot: bool = False
    is_projectile_explosion: bool = False
    is_projectile_attachment: bool = False
    is_sequential: bool = False
    is_split: bool = False
    is_part: bool = False


def expected_damage(
    *,
    base_atk: float,
    enemy_def: float,
    core_dmg_mult: float,
    full_charge_mult: float,
    terms: DamageTerms,
    hit: HitSpec,
) -> float:
    """Moris DealForm semantics lowered to a branch-light deterministic kernel.

    This mirrors calculator.damage.calc_damage_avg(), but does not call Moris and
    does not allocate dictionaries. Fast deliberately returns float expectation;
    rounding every individual hit would add needless work and ranking noise.
    """

    # ① coefficient / normal-attack coefficient bonus
    f1 = hit.coeff
    if hit.is_normal_atk:
        f1 *= 1.0 + terms.normal_atk_dmg_pct / 100.0

    # ② effective ATK - effective DEF
    atk_term = base_atk * (1.0 + terms.atk_pct / 100.0) + terms.atk_flat
    if hit.is_armor_break_damage:
        def_term = 0.0
    else:
        effective_def = max(
            enemy_def * (1.0 + terms.enemy_def_down_pct / 100.0),
            0.0,
        )
        def_term = effective_def * (1.0 - terms.def_ignore_pct / 100.0)
    f2 = max(atk_term - def_term, 0.0)

    # ③ additive bonus layer: expected crit/core + FB/optimal-range
    f3 = 1.0
    if hit.is_normal_atk:
        crit_rate = terms.crit_rate
        crit_dmg = terms.crit_dmg
    else:
        crit_rate = (
            terms.crit_rate
            if terms.crit_rate_skill is None
            else terms.crit_rate_skill
        )
        crit_dmg = (
            terms.crit_dmg
            if terms.crit_dmg_skill is None
            else terms.crit_dmg_skill
        )
    f3 += min(crit_rate, 1.0) * (0.5 + crit_dmg / 100.0)

    if hit.is_full_burst:
        f3 += 0.5
    if hit.is_optimal_range and hit.is_normal_atk:
        f3 += 0.3

    core_weight = max(0.0, min(hit.core_prob, 1.0))
    if core_weight and (
        hit.is_normal_atk or hit.is_core_damage or hit.is_weapon_mode_skill
    ):
        core_base = (core_dmg_mult - 100.0) / 100.0
        f3 += core_weight * (core_base + terms.core_dmg_pct / 100.0)

    # ④ charge layer
    if hit.is_full_charge:
        f4 = (
            (full_charge_mult / 100.0)
            * (1.0 + terms.charge_dmg_mag_pct / 100.0)
            + terms.charge_dmg_pct / 100.0
        )
    else:
        f4 = 1.0

    # ⑤ attack/type layer
    f5 = 1.0 + terms.atk_dmg_pct / 100.0
    if hit.is_burst_damage:
        f5 += terms.burst_dmg_pct / 100.0
        if hit.is_aoe_burst:
            f5 += terms.burst_dmg_aoe_pct / 100.0
    if hit.is_pierce_damage:
        f5 += terms.pierce_dmg_pct / 100.0
    if hit.is_armor_break_damage:
        f5 += terms.armor_break_dmg_pct / 100.0
    if hit.is_dot:
        f5 += terms.dot_dmg_pct / 100.0
    if hit.is_projectile_explosion:
        f5 += terms.projectile_explosion_dmg_pct / 100.0
    if hit.is_projectile_attachment:
        f5 += terms.projectile_attachment_dmg_pct / 100.0
    if hit.is_sequential:
        f5 += terms.sequential_dmg_pct / 100.0
    if hit.is_part:
        f5 += terms.part_dmg_pct / 100.0

    # ⑥ received/split layer
    f6 = 1.0 + terms.received_dmg_pct / 100.0
    if hit.is_split:
        f6 += terms.split_dmg_pct / 100.0

    # ⑦ elemental advantage
    f7 = 1.0
    if terms.element_match:
        f7 += 0.1 + terms.element_bonus_pct / 100.0

    return f1 / 100.0 * f2 * f3 * f4 * f5 * f6 * f7
