from __future__ import annotations

from math import inf, nextafter
from typing import TYPE_CHECKING

from .damage_state import DamageTermResolver
from .model import CompiledSquad, EnemyStaticProfile, FastScore
from .normal_attack import compile_normal_attack_spec, expected_normal_block_damage
from .shot_blocks import ShotBlockCursor, compile_static_shot_blocks
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


def static_normal_score_blockers(squad: CompiledSquad) -> tuple[str, ...]:
    """Return cadence/shot-shape mechanics that make static shot blocks unsafe.

    This intentionally scans *all* compiled effects, not only currently
    executable ones. An unsupported cadence buff is still a reason not to emit a
    deceptively precise static score.
    """

    blockers: list[str] = []
    for effect in squad.effects:
        stat = effect.stat or ""
        if stat not in _CADENCE_OR_SHAPE_STATS:
            continue
        if _is_folded_static_self_modifier(effect):
            continue
        owner = squad.members[effect.actor].name
        blockers.append(f"{owner}:{effect.name or stat}:{stat}")
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
                "Fast static normal score blocked by live cadence/shot-shape effects: "
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
        self.consume_until(self.duration, inclusive=True)
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
