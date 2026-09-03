from __future__ import annotations

from collections import defaultdict

from calculator import timeline
from calculator.buff_manager import BuffManager
from context import spec
from fast_engine.engine.burst import BurstSignal, compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers

from .public_ranking_probe import COMMON_CONFIG, COMMON_ENEMY, _source_corpus

CROWN = "크라운"
ROYAL = "로얄 에타이어 4"
STACK_EVENT = "stack_reach:릴렉스:20"
HEAL_EVENT = "event:heal_received"
SAFE_SELF_ONLY = {"레이드_델타", "레이드_루드밀라루주", "레이드_라피앨리스"}
EXTERNAL_PROVIDER = {"스쿼드1", "스쿼드5", "레이드_일레그", "레이드_아스카루드밀라"}


def _enemy(duration: float) -> EnemyStaticProfile:
    core_px = float(COMMON_ENEMY.get("core_px", 0.0) or 0.0)
    return EnemyStaticProfile(
        defense=float(COMMON_ENEMY.get("def", 31784.0)),
        element=COMMON_ENEMY.get("code"),
        core_uptime=1.0 if core_px > 0 else 0.0,
        core_px=core_px,
        duration=duration,
    )


def _royal_blockers(compiled) -> tuple[str, ...]:
    return tuple(
        b
        for b in static_score_blockers(compiled)
        if f"{CROWN}:{ROYAL}:atk_dmg_pct" in b
    )


def _moris_heals(members: tuple[str, ...]) -> list[float]:
    out: list[float] = []
    original = BuffManager.notify

    def traced(self, event: str, t: float, caster: str, **ctx):
        if event == HEAL_EVENT and caster == CROWN:
            out.append(float(t))
        return original(self, event, t, caster, **ctx)

    BuffManager.notify = traced
    try:
        squad = spec.build_squad(list(members))
        config = spec.build_config(squad, dict(COMMON_CONFIG))
        timeline.simulate(
            squad,
            config=config,
            enemy=dict(COMMON_ENEMY),
            seed=42,
            verbose=False,
        )
    finally:
        BuffManager.notify = original
    return out


def _fast_events(members: tuple[str, ...]):
    moris_squad = spec.build_squad(list(members))
    compiled = compile_moris_squad(moris_squad)
    policy = compile_burst_policy(moris_squad, compiled, dict(COMMON_CONFIG))
    runtime = BurstRuntime(compiled, policy, _enemy(policy.duration))
    crown = compiled.names.index(CROWN)
    trace: dict[str, list[float]] = defaultdict(list)
    original = TriggerDispatcher.dispatch

    def traced(self, signal: BurstSignal, *, context=None):
        if self is runtime.dispatcher and signal.owner_actor == crown and signal.event_key in {STACK_EVENT, HEAL_EVENT}:
            trace[signal.event_key].append(float(signal.time))
        if context is None:
            return original(self, signal)
        return original(self, signal, context=context)

    TriggerDispatcher.dispatch = traced
    try:
        runtime.run(duration=policy.duration)
    finally:
        TriggerDispatcher.dispatch = original
    relevant = {
        effect.name: runtime.dispatcher._activation_counts.get(effect.effect_id, 0)
        for effect in compiled.members[crown].effects
        if effect.name in {"릴렉스", "로얄 에타이어", "로얄 에타이어 3", "로얄 에타이어 4"}
    }
    return trace, relevant, runtime.dispatcher.effects.named_stack(crown, "릴렉스", now=policy.duration)


def main() -> None:
    rows = {
        source_name: tuple(members)
        for members, source_name in _source_corpus()
        if CROWN in members
    }
    if set(rows) != SAFE_SELF_ONLY | EXTERNAL_PROVIDER:
        raise AssertionError(f"unexpected Crown corpus: {sorted(rows)}")

    print("=== SCORE SAFETY SPLIT ===")
    for source_name, members in rows.items():
        compiled = compile_moris_squad(spec.build_squad(list(members)))
        blockers = _royal_blockers(compiled)
        print(source_name, "royal_blockers=", blockers)
        if source_name in SAFE_SELF_ONLY and blockers:
            raise AssertionError(f"self-only Crown team stayed blocked: {source_name}: {blockers}")
        if source_name in EXTERNAL_PROVIDER and not blockers:
            raise AssertionError(f"external-heal Crown team widened unsafely: {source_name}")

    # Delta is the cleanest real source case: Crown is the only possible heal provider.
    delta = rows["레이드_델타"]
    moris = _moris_heals(delta)
    fast, activations, residual = _fast_events(delta)
    fast_stack = fast[STACK_EVENT]
    fast_heal = fast[HEAL_EVENT]
    print("=== DELTA REAL-CORPUS TRACE ===")
    print("moris_heal", len(moris), moris)
    print("fast_stack", len(fast_stack), fast_stack)
    print("fast_heal", len(fast_heal), fast_heal)
    print("activations", activations, "residual_relax_stack", residual)

    if fast_stack != fast_heal:
        raise AssertionError("stack reach and self heal must be same-edge one-for-one")
    if len(fast_heal) != len(moris):
        raise AssertionError(f"heal count mismatch: Fast={len(fast_heal)} Moris={len(moris)}")
    if activations.get("로얄 에타이어 3", 0) != len(fast_heal):
        raise AssertionError("self-heal activation count mismatch")
    if activations.get("로얄 에타이어 4", 0) != len(fast_heal):
        raise AssertionError("heal_received consumer activation count mismatch")
    if residual >= 20.0:
        raise AssertionError(f"reset failed, residual Relax stack={residual}")

    diffs = [f - m for f, m in zip(fast_heal, moris)]
    print("time_diff_fast_minus_moris", diffs)
    print("max_abs_time_diff", max(map(abs, diffs), default=0.0))


if __name__ == "__main__":
    main()
