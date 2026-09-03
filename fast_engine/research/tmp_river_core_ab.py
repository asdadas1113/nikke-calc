from __future__ import annotations

import argparse
from dataclasses import replace

from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.triggers import compile_trigger_rule

from .public_ranking_probe import _source_corpus

RIVER = "리버렐리오"
STATE = "차분한 수심 2"
LABEL = f"{RIVER}:{STATE}:atk_dmg_pct"


def _river_rows():
    rows = tuple((members, name) for members, name in _source_corpus() if RIVER in members)
    if len(rows) != 3:
        raise AssertionError(f"expected 3 Riverellio source rows, got {len(rows)}: {rows}")
    return rows


def _compiled(members):
    return compile_moris_squad(spec.build_squad(list(members)))


def _river_effect(compiled):
    matches = tuple(
        effect
        for effect in compiled.effects
        if compiled.members[effect.actor].name == RIVER
        and effect.name == STATE
        and (effect.stat or "") == "atk_dmg_pct"
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one Riverellio effect, got {len(matches)}")
    return matches[0]


def baseline() -> None:
    print("=== BASELINE ===")
    for members, source_name in _river_rows():
        compiled = _compiled(members)
        blockers = static_score_blockers(compiled)
        river = tuple(b for b in blockers if LABEL in b)
        print(source_name, "river_blockers=", river)
        if set(river) != {
            f"normal_delivery:{LABEL}",
            f"skill_state_delivery:{LABEL}",
        }:
            raise AssertionError(f"unexpected baseline blockers for {source_name}: {river}")
        effect = _river_effect(compiled)
        if is_direct_damage_buff_runtime_supported(effect):
            raise AssertionError("baseline unexpectedly supports Riverellio core condition")


def _trace(members, core_px: float, *, duration: float = 66.0):
    moris_squad = spec.build_squad(list(members))
    compiled = compile_moris_squad(moris_squad)
    config = spec.build_config(
        moris_squad,
        {"duration": duration, "first_burst_time": 3.0, "rng_mode": "expected"},
    )
    policy = compile_burst_policy(moris_squad, compiled, config)
    enemy = EnemyStaticProfile(
        defense=31784.0,
        core_uptime=1.0 if core_px >= 1.0 else 0.0,
        core_px=core_px,
        duration=duration,
    )
    runtime = BurstRuntime(compiled, policy, enemy)
    actor = compiled.names.index(RIVER)
    shots: list[tuple[float, bool]] = []

    def observe(_actor: int, now: float) -> None:
        shots.append(
            (
                now,
                runtime.dispatcher.effects.has_named_state(actor, STATE, now=now),
            )
        )

    runtime.weapons.attach_score_shot_sink((actor,), observe)
    runtime.run(duration=duration)
    return shots, runtime.dispatcher.effects.has_named_state(actor, STATE, now=duration - 1e-6)


def patched() -> None:
    print("=== PATCHED ===")
    rows = _river_rows()
    for members, source_name in rows:
        compiled = _compiled(members)
        blockers = static_score_blockers(compiled)
        river = tuple(b for b in blockers if LABEL in b)
        print(source_name, "river_blockers=", river)
        if river:
            raise AssertionError(f"Riverellio blockers survived patch for {source_name}: {river}")
        effect = _river_effect(compiled)
        if not is_direct_damage_buff_runtime_supported(effect):
            raise AssertionError("patched Riverellio shape still not runtime-supported")

        # The opening is deliberately shape-specific. A CORE_HIT condition on a
        # different trigger must remain fail-closed.
        wrong = replace(effect, triggers=(compile_trigger_rule("burst_cast"),))
        if is_direct_damage_buff_runtime_supported(wrong):
            raise AssertionError("CORE_HIT widened beyond raw full_charge_hit")
        wrong_count = replace(effect, triggers=(compile_trigger_rule("full_charge_count:2"),))
        if is_direct_damage_buff_runtime_supported(wrong_count):
            raise AssertionError("CORE_HIT widened to full_charge_count")

    members, source_name = rows[0]
    no_core, no_core_final = _trace(members, 0.0)
    core, core_final = _trace(members, 10.0)
    print("trace_source=", source_name)
    print("no_core_first10=", no_core[:10])
    print("core_first10=", core[:10])
    print("core_tail=", core[-10:])

    if len(no_core) < 2 or len(core) < 2:
        raise AssertionError("not enough Riverellio charge shots observed")
    if any(active for _t, active in no_core) or no_core_final:
        raise AssertionError("core-absent target activated Calm Depth 2")

    # The physical shot is observed before the post-shot full_charge_hit notify.
    # Therefore shot 1 must be unbuffed, and shot 2 must see the state activated
    # by shot 1 when a target core exists.
    if core[0][1]:
        raise AssertionError("triggering first full-charge shot incorrectly received the buff")
    if not core[1][1]:
        raise AssertionError("second full-charge shot did not receive the post-shot buff")

    first_t = core[0][0]
    refreshed = [(t, active) for t, active in core if t > first_t + 60.0]
    if not refreshed:
        raise AssertionError("trace did not cross the original 60s expiry horizon")
    if not all(active for _t, active in refreshed) or not core_final:
        raise AssertionError("repeated full-charge hits did not refresh the 60s state")

    print("PASS: core absent never activates")
    print("PASS: first core-present shot is unbuffed, second is buffed")
    print("PASS: repeated full-charge hits keep the 60s state refreshed")
    print("PASS: alternate CORE_HIT trigger shapes remain fail-closed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("baseline", "patched"))
    args = parser.parse_args()
    if args.mode == "baseline":
        baseline()
    else:
        patched()


if __name__ == "__main__":
    main()
