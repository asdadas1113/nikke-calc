from __future__ import annotations

from calculator import timeline
from calculator.buff_manager import BuffManager
from context import spec
from fast_engine.engine.burst import BurstSignal, compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile

from .public_ranking_probe import COMMON_CONFIG, COMMON_ENEMY, _source_corpus

CROWN = "크라운"


def _delta() -> tuple[str, ...]:
    return next(tuple(m) for m, name in _source_corpus() if name == "레이드_델타")


def _enemy(duration: float) -> EnemyStaticProfile:
    core_px = float(COMMON_ENEMY.get("core_px", 0.0) or 0.0)
    return EnemyStaticProfile(
        defense=float(COMMON_ENEMY.get("def", 31784.0)),
        element=COMMON_ENEMY.get("code"),
        core_uptime=1.0 if core_px > 0 else 0.0,
        core_px=core_px,
        duration=duration,
    )


def moris_trace(members: tuple[str, ...]):
    hit43: list[float] = []
    heals: list[float] = []
    original = BuffManager.notify

    def traced(self, event: str, t: float, caster: str, **ctx):
        result = original(self, event, t, caster, **ctx)
        if caster == CROWN and event == "hit_count":
            count = self._event_counts.get(CROWN, {}).get("hit_count", 0)
            if count % 43 == 0:
                hit43.append(float(t))
        if caster == CROWN and event == "event:heal_received":
            heals.append(float(t))
        return result

    BuffManager.notify = traced
    try:
        squad = spec.build_squad(list(members))
        config = spec.build_config(squad, dict(COMMON_CONFIG))
        timeline.simulate(squad, config=config, enemy=dict(COMMON_ENEMY), seed=42, verbose=False)
    finally:
        BuffManager.notify = original
    return hit43, heals


def fast_trace(members: tuple[str, ...]):
    squad = spec.build_squad(list(members))
    compiled = compile_moris_squad(squad)
    policy = compile_burst_policy(squad, compiled, dict(COMMON_CONFIG))
    runtime = BurstRuntime(compiled, policy, _enemy(policy.duration))
    crown = compiled.names.index(CROWN)
    hit_signals: list[tuple[float, int | None]] = []
    stack_reach: list[float] = []
    original = TriggerDispatcher.dispatch

    def traced(self, signal: BurstSignal, *, context=None):
        if self is runtime.dispatcher and signal.owner_actor == crown:
            if signal.event_key == "hit_count":
                hit_signals.append((float(signal.time), signal.count))
            elif signal.event_key == "stack_reach:릴렉스:20":
                stack_reach.append(float(signal.time))
        if context is None:
            return original(self, signal)
        return original(self, signal, context=context)

    TriggerDispatcher.dispatch = traced
    try:
        runtime.run(duration=policy.duration)
    finally:
        TriggerDispatcher.dispatch = original
    return compiled.members[crown].weapon, hit_signals, stack_reach


def main() -> None:
    members = _delta()
    mh, heals = moris_trace(members)
    weapon, fh, stack = fast_trace(members)
    print("members", members)
    print("weapon", weapon)
    print("moris_hit43_count", len(mh))
    print("moris_hit43_first30", mh[:30])
    print("moris_heals", heals)
    print("fast_hit_signal_count", len(fh))
    print("fast_hit_signals_first30", fh[:30])
    print("fast_stack_reach", stack)
    if fh:
        print("first_threshold_diff", fh[0][0] - mh[0])


if __name__ == "__main__":
    main()
