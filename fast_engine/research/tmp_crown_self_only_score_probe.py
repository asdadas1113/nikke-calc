from __future__ import annotations

from time import perf_counter

from calculator.timeline import simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import score_static_squad, static_score_blockers

from .public_ranking_probe import COMMON_CONFIG, COMMON_ENEMY, _fast_enemy, _source_corpus

SAFE_SELF_ONLY = {"레이드_델타", "레이드_루주", "레이드_라피앨리스"}


def main() -> None:
    rows = {
        source_name: tuple(members)
        for members, source_name in _source_corpus()
        if source_name in SAFE_SELF_ONLY
    }
    if set(rows) != SAFE_SELF_ONLY:
        raise AssertionError(f"unexpected self-only Crown corpus: {sorted(rows)}")

    print("=== CROWN SELF-ONLY SCORE PROBE ===")
    for source_name in sorted(rows):
        members = rows[source_name]
        moris_squad = spec.build_squad(list(members))
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(moris_squad, compiled, dict(COMMON_CONFIG))
        blockers = static_score_blockers(compiled)
        print(source_name, "members=", members)
        print(source_name, "blockers=", blockers)
        if blockers:
            continue

        moris_config = spec.build_config(moris_squad, dict(COMMON_CONFIG))
        t0 = perf_counter()
        moris = simulate(
            moris_squad,
            config=moris_config,
            enemy=dict(COMMON_ENEMY),
            seed=42,
            verbose=False,
        )
        moris_seconds = perf_counter() - t0

        t1 = perf_counter()
        fast = score_static_squad(compiled, policy, _fast_enemy(duration=policy.duration))
        fast_seconds = perf_counter() - t1

        moris_total = float(moris.squad_total)
        fast_total = float(fast.squad_total)
        rel = fast_total / moris_total - 1.0 if moris_total else 0.0
        print(
            source_name,
            "team=",
            {
                "moris": moris_total,
                "fast": fast_total,
                "relative_error": rel,
                "moris_seconds": moris_seconds,
                "fast_seconds": fast_seconds,
                "unsupported": tuple(fast.unsupported),
                "events_processed": fast.events_processed,
            },
        )

        moris_chars = tuple(float(value) for value in moris.char_total)
        for actor, name in enumerate(compiled.names):
            m = moris_chars[actor]
            f = float(fast.char_total[actor])
            err = f / m - 1.0 if m else (0.0 if f == 0.0 else float("inf"))
            print(
                source_name,
                "char=",
                {
                    "actor": actor,
                    "name": name,
                    "moris": m,
                    "fast": f,
                    "relative_error": err,
                },
            )


if __name__ == "__main__":
    main()
