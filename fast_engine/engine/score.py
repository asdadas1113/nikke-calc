from __future__ import annotations

from math import inf, nextafter
from typing import TYPE_CHECKING

from .damage_policy import is_direct_damage_buff_runtime_supported
from .damage_state import DamageTermResolver
from .model import CompiledSquad, EnemyStaticProfile, FastScore
from .normal_attack import compile_normal_attack_spec, expected_normal_block_damage
from .shot_blocks import ShotBlockCursor, compile_static_shot_blocks
from .triggers import TriggerMode
from .weapon import StaticCadenceModifiers

if TYPE_CHECKING:
    from .burst import BurstPolicy
    from .burst_runtime import BurstRuntime


# Any live change to one of these can invalidate precompiled shot timestamps or
# the number of damage-bearing hits inside a shot. Permanent unconditional self
# modifiers that compile_static_cadence_modifiers() already folds are safe.
_CADENCE_OR_SHAPE_STATS = frozenset({
    "reload_speed_pct",
    "max_ammo_pct",
    "max_ammo_flat",
    "max_ammo_infinite",
    "charge_speed_pct",
    "charge_speed_caster_based_pct",
    "charge_time_flat",
    "charge_time_fixed",
    "attack_speed_pct",
    "mg_warmup_speed_pct",
    "pellet_count",
    "pellet_count_fixed",
})
_STATIC_FOLDABLE = frozenset(StaticCadenceModifiers.__dataclass_fields__)

# Direct numeric states that can change ordinary weapon damage in the initial
# static-target model. A stat being numerically resolvable is not enough: its
# trigger/condition/target path must also be deliverable by the score runtime.
_NORMAL_DIRECT_DAMAGE_STATS = frozenset({
    "atk_pct",
    "atk_flat",
    "atk_caster_based_pct",
    "def_ignore_pct",
    "crit_rate",
    "normal_atk_crit_rate",
    "crit_dmg",
    "normal_atk_crit_dmg",
    "core_dmg_pct",
    "normal_atk_dmg_pct",
    "atk_dmg_pct",
    "charge_dmg_pct",
    "charge_dmg_mag_pct",
    "received_dmg_pct",
    "personal_received_dmg_pct",
    "element_bonus",
    "element_bonus_pct",
    "def_pct",
    "personal_enemy_def_down_pct",
})

# These are known Moris mechanisms that can alter normal-attack damage but are
# not yet lowered into DamageTerms/HitSpec. Their presence must block a score,
# otherwise some archetypes would be systematically undervalued.
_UNRESOLVED_NORMAL_DAMAGE_STATS = frozenset({
    "atk_from_hp_pct",
    "atk_copy",
    "atk_buff_mag_pct",
    "charge_dmg_per_max_ammo_pct",
    "charge_speed_overflow_conversion_pct",
    "dmg_scale_mag_pct",
    "armor_break_enabled",
    "pierce_enabled",
    "element_code_override",
})

# A fixed periodic ATK state is the one deliberate exception outside the direct
# timing policy: the periodic scheduler has already been parity-tested (Milk).
# Effects that can move that periodic grid are not yet score-safe.
_PERIODIC_AUX_STATS = frozenset({"atk_pct", "atk_flat", "atk_caster_based_pct"})
_PERIODIC_GRID_INVALIDATORS = frozenset({
    "effect_interval",
    "skill_cooldown_pct",
    "skill_cooldown_reduce_pct",
    "force_skill_use",
})

# The initial Fast enemy never attacks the squad. Effects that require an enemy
# received-hit notification are therefore not "unsupported" for this scoring
# problem; they are unreachable by construction. If incoming attacks are added
# to the enemy model later this exemption must disappear with that model change.
_PATTERNLESS_UNREACHABLE_EVENT_KEYS = frozenset({"received_hit"})


def _is_folded_static_self_modifier(effect) -> bool:
    return (
        (effect.stat or "") in _STATIC_FOLDABLE
        and effect.effect_type == "buff"
        and effect.target_spec.mode.value == "self"
        and effect.duration in (None, -1.0)
        and not effect.condition_rules
        and bool(effect.triggers)
        and all(rule.event_key == "battle_start" for rule in effect.triggers)
    )


def _is_score_safe_fixed_periodic(effect) -> bool:
    return (
        (effect.stat or "") in _PERIODIC_AUX_STATS
        and effect.effect_type == "buff"
        and effect.target_spec.runtime_supported
        and all(rule.is_runtime_supported for rule in effect.condition_rules)
        and bool(effect.triggers)
        and all(
            rule.mode is TriggerMode.PERIODIC
            and rule.interval is not None
            and float(rule.interval) > 0.0
            for rule in effect.triggers
        )
    )


def _is_patternless_unreachable(effect) -> bool:
    return (
        bool(effect.triggers)
        and all(
            rule.event_key in _PATTERNLESS_UNREACHABLE_EVENT_KEYS
            for rule in effect.triggers
        )
    )


def _direct_normal_effect_needs_score_support(effect) -> bool:
    stat = effect.stat or ""
    if stat != "def_pct":
        return True
    # Ally DEF buffs do not enter outgoing normal-attack DealForm. Enemy-target
    # def_pct is the Moris defense-down path and does matter.
    return effect.target_spec.mode.value == "enemy"


def static_normal_score_blockers(squad: CompiledSquad) -> tuple[str, ...]:
    """Return mechanics that make the current static normal score unsafe.

    This intentionally scans *all* compiled effects, not only effects currently
    marked executable. Unsupported mechanics are exactly where a silent ranking
    bias would otherwise enter. Effects that cannot fire under the patternless
    static enemy contract are ignored explicitly rather than pretending they are
    implemented.
    """

    blockers: list[str] = []
    has_score_periodic = any(_is_score_safe_fixed_periodic(effect) for effect in squad.effects)

    for effect in squad.effects:
        stat = effect.stat or ""
        owner = squad.members[effect.actor].name
        label = f"{owner}:{effect.name or stat}:{stat}"

        if _is_patternless_unreachable(effect):
            continue

        if stat in _CADENCE_OR_SHAPE_STATS:
            if not _is_folded_static_self_modifier(effect):
                blockers.append(f"cadence:{label}")
            continue

        if stat in _UNRESOLVED_NORMAL_DAMAGE_STATS:
            blockers.append(f"normal_state:{label}")
            continue

        if stat in _NORMAL_DIRECT_DAMAGE_STATS and _direct_normal_effect_needs_score_support(effect):
            if is_direct_damage_buff_runtime_supported(effect):
                continue
            if _is_score_safe_fixed_periodic(effect):
                continue
            blockers.append(f"normal_delivery:{label}")
            continue

        if has_score_periodic and stat in _PERIODIC_GRID_INVALIDATORS:
            blockers.append(f"periodic_grid:{label}")

    return tuple(dict.fromkeys(blockers))


class StaticNormalAttackObserver:
    """Score normal attacks from compressed static shot blocks.

    The observer is called at scheduler boundaries. Between boundaries combat
    state is unchanged, so each actor performs at most one DealForm evaluation
    and multiplies it by the number of shots consumed in that span.
    """

    __slots__ = (
        "runtime", "duration", "resolver", "specs", "cursors", "char_total",
    )

    def __init__(self, runtime: "BurstRuntime", *, duration: float) -> None:
        blockers = static_normal_score_blockers(runtime.squad)
        if blockers:
            detail = ", ".join(blockers[:8])
            if len(blockers) > 8:
                detail += f", +{len(blockers) - 8} more"
            raise NotImplementedError(
                "Fast static normal score blocked by unsupported comparison-critical effects: "
                + detail
            )

        self.runtime = runtime
        self.duration = float(duration)
        self.resolver = DamageTermResolver(
            runtime.squad,
            runtime.dispatcher.effects,
            runtime.state,
            runtime.enemy,
        )
        self.specs = tuple(compile_normal_attack_spec(member) for member in runtime.squad.members)
        blocks = compile_static_shot_blocks(runtime.squad, duration=self.duration)
        self.cursors = tuple(ShotBlockCursor(rows) for rows in blocks)
        self.char_total = [0.0] * len(runtime.squad.members)

    def consume_until(self, time: float, *, inclusive: bool) -> None:
        """Consume all unscored shots before/through ``time`` under current state.

        For an exclusive boundary the current ActiveEffectStore still represents
        the interval immediately *before* the event. Resolve at the previous
        representable float so a buff expiring exactly at ``time`` remains active
        for shots strictly earlier than that boundary.
        """

        eval_time = float(time) if inclusive else nextafter(float(time), -inf)
        full_burst = self.runtime.machine.phase == "full_burst"
        core_prob = self.runtime.enemy.effective_core_rate

        for actor, cursor in enumerate(self.cursors):
            count = cursor.consume_until(time, inclusive=inclusive)
            if count <= 0:
                continue
            member = self.runtime.squad.members[actor]
            terms = self.resolver.resolve(actor, now=eval_time)
            self.char_total[actor] += expected_normal_block_damage(
                self.specs[actor],
                shot_count=count,
                base_atk=member.base_atk,
                enemy_def=self.runtime.enemy.defense,
                terms=terms,
                core_prob=core_prob,
                is_full_burst=full_burst,
                is_optimal_range=False,
            )

    def finish(self, *, events_processed: int) -> FastScore:
        # Combat is [0, duration): a shot exactly at the nominal horizon is not
        # damage-bearing, matching the final Moris frame immediately before it.
        self.consume_until(self.duration, inclusive=False)
        totals = tuple(self.char_total)
        return FastScore(
            squad_total=sum(totals),
            char_total=totals,
            duration=self.duration,
            events_processed=events_processed,
            unsupported=("skill_damage:not_implemented",),
        )


def score_static_normal_squad(
    squad: CompiledSquad,
    policy: "BurstPolicy",
    enemy: EnemyStaticProfile | None = None,
    *,
    duration: float | None = None,
) -> FastScore:
    """Run the first score-only vertical slice: stateful normal attacks only."""

    from .burst_runtime import BurstRuntime

    horizon = policy.duration if duration is None else min(float(duration), policy.duration)
    runtime = BurstRuntime(squad, policy, enemy)
    observer = StaticNormalAttackObserver(runtime, duration=horizon)
    result = runtime.run(duration=horizon, score_observer=observer)
    return observer.finish(events_processed=result.events_processed)
