from __future__ import annotations

import json
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.sim_result import _is_normal
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import StaticNormalAttackObserver, score_static_squad, static_score_blockers
from fast_engine.engine.state import ENEMY as ENEMY_TARGET

NAMES = (
    "미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인",
)
MIHARA = 4
DURATION = 180.0
CONFIG = {"duration": DURATION, "first_burst_time": 3.0, "rng_mode": "expected"}
ENEMY = dict(DEFAULT_ENEMY)
ENEMY.update({"def": 55000.0, "code": "작열", "core_px": 10.0})
PROFILE = EnemyStaticProfile(
    defense=55000.0,
    element="작열",
    core_uptime=1.0,
    core_px=10.0,
    duration=DURATION,
)


def main() -> None:
    raw = spec.build_squad(list(NAMES))
    compiled = compile_moris_squad(raw)
    assert static_score_blockers(compiled) == ()
    print("MIHARA_WEAPON=" + json.dumps(dict(compiled.members[MIHARA].weapon), ensure_ascii=False, sort_keys=True))

    original_notify = BuffManager.notify
    moris_stack_rows: list[tuple] = []

    def notify(manager, event, t, caster, **ctx):
        before = None
        if caster == NAMES[MIHARA] and event == "hit_count":
            before = max(
                (
                    ab.stack for ab in manager._active
                    if ab.caster == caster and ab.effect.get("name") == "사슬 감기"
                ),
                default=0,
            )
        out = original_notify(manager, event, t, caster, **ctx)
        if before is not None:
            after = max(
                (
                    ab.stack for ab in manager._active
                    if ab.caster == caster and ab.effect.get("name") == "사슬 감기"
                ),
                default=0,
            )
            if after != before:
                moris_stack_rows.append((float(t), int(before), int(after)))
        return out

    with patch.object(BuffManager, "notify", new=notify):
        moris = simulate(
            raw,
            config=spec.build_config(raw, dict(CONFIG)),
            enemy=dict(ENEMY),
            seed=42,
            verbose=False,
        )

    moris_normal = sum(
        float(hit.damage)
        for hit in moris.hits
        if hit.caster == NAMES[MIHARA] and _is_normal(hit)
    )
    moris_skill = float(moris.char_total[NAMES[MIHARA]]) - moris_normal

    old_dispatch = TriggerDispatcher.dispatch
    old_finish = StaticNormalAttackObserver.finish
    fast_boundaries: list[tuple] = []
    normal_capture: dict[str, tuple[float, ...]] = {}

    def dispatch(dispatcher, signal, **kwargs):
        owner = signal.owner_actor
        key = signal.event_key
        if owner == MIHARA and key == "hit_count":
            counter_key = (owner, key)
            before_count = dispatcher._event_counts[counter_key]
            before_stack = dispatcher.effects.named_stack(ENEMY_TARGET, "사슬 감기", now=signal.time)
            result = old_dispatch(dispatcher, signal, **kwargs)
            after_count = dispatcher._event_counts[counter_key]
            after_stack = dispatcher.effects.named_stack(ENEMY_TARGET, "사슬 감기", now=signal.time)
            crossed = before_count // 40 != after_count // 40
            changed = after_stack != before_stack
            if crossed or changed:
                activated = tuple(
                    (
                        effect_id,
                        dispatcher._effect_table[effect_id].name,
                        dispatcher._effect_table[effect_id].stat,
                    )
                    for effect_id in result.activated_effect_ids
                )
                fast_boundaries.append((
                    float(signal.time),
                    int(before_count),
                    int(after_count),
                    float(before_stack),
                    float(after_stack),
                    dispatcher.burst.phase,
                    activated,
                ))
            return result
        return old_dispatch(dispatcher, signal, **kwargs)

    def finish(observer, *, events_processed):
        out = old_finish(observer, events_processed=events_processed)
        normal_capture["totals"] = tuple(float(value) for value in out.char_total)
        return out

    with (
        patch.object(TriggerDispatcher, "dispatch", new=dispatch),
        patch.object(StaticNormalAttackObserver, "finish", new=finish),
    ):
        fast = score_static_squad(
            compiled,
            compile_burst_policy(raw, compiled, dict(CONFIG)),
            PROFILE,
            duration=DURATION,
        )

    fast_normal = normal_capture["totals"][MIHARA]
    fast_skill = float(fast.char_total[MIHARA]) - fast_normal

    print("BREAKDOWN=" + json.dumps({
        "moris_total": float(moris.char_total[NAMES[MIHARA]]),
        "moris_normal": moris_normal,
        "moris_skill": moris_skill,
        "fast_total": float(fast.char_total[MIHARA]),
        "fast_normal": fast_normal,
        "fast_skill": fast_skill,
        "total_rel": float(fast.char_total[MIHARA]) / float(moris.char_total[NAMES[MIHARA]]) - 1.0,
        "normal_rel": fast_normal / moris_normal - 1.0 if moris_normal else None,
        "skill_rel": fast_skill / moris_skill - 1.0 if moris_skill else None,
    }, ensure_ascii=False, sort_keys=True))
    print("MORIS_CHAIN_STACK_CHANGES=" + repr(moris_stack_rows))
    print("FAST_HIT40_BOUNDARIES=" + repr(fast_boundaries))


if __name__ == "__main__":
    main()
