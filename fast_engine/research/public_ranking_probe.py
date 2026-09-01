from __future__ import annotations

"""Public, optimizer-independent Fast-vs-Moris ranking probe.

This is intentionally *not* an end-to-end optimizer benchmark.  It scores the
fixed public squads in ``context.snapshot.SQUADS`` so candidate-generation
heuristics cannot contaminate the first Fast ranking diagnosis.

A Fast numeric subtotal is considered comparable only when both conditions hold:

- static comparison-critical state has no fail-closed blockers;
- ``FastScore.unsupported`` is empty.

Rows that fail either condition remain in the Moris ranking but are reported as
coverage gaps, not as Fast scoring errors.
"""

from collections import Counter
from dataclasses import asdict, dataclass
import json
from statistics import median
from time import perf_counter
from typing import Any

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers
from optimizer.validation import RankingObservation, analyze_fast_moris_ranking


@dataclass(frozen=True)
class ProbeRow:
    name: str
    members: tuple[str, ...]
    moris_score: float
    raw_fast_score: float | None
    certified_fast_score: float | None
    relative_error: float | None
    blockers: tuple[str, ...]
    unsupported: tuple[str, ...]
    groups: tuple[str, ...]
    moris_seconds: float
    fast_seconds: float


def _input_blockers(config: dict[str, Any], enemy: dict[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    if config.get("normal_hit_coeff"):
        blockers.append("input:normal_hit_coeff_override")
    if enemy.get("immune_windows"):
        blockers.append("input:immune_windows")
    if enemy.get("element_windows"):
        blockers.append("input:element_windows")
    if enemy.get("has_parts"):
        blockers.append("input:has_parts")
    if enemy.get("optimal_range_weapons"):
        blockers.append("input:optimal_range_weapons")
    return tuple(blockers)


def _fast_enemy(enemy: dict[str, Any], *, duration: float) -> EnemyStaticProfile:
    core_px = float(enemy.get("core_px", DEFAULT_ENEMY["core_px"]) or 0.0)
    return EnemyStaticProfile(
        defense=float(enemy.get("def", DEFAULT_ENEMY["def"])),
        element=enemy.get("code", DEFAULT_ENEMY["code"]),
        core_uptime=1.0 if core_px > 0.0 else 0.0,
        core_px=core_px,
        duration=duration,
    )


def _groups(compiled) -> tuple[str, ...]:
    groups = {f"weapon:{member.weapon_type}" for member in compiled.members}
    if any(member.weapon_type in {"SR", "RL"} for member in compiled.members):
        groups.add("archetype:charge")
    if any(member.weapon_type == "SG" for member in compiled.members):
        groups.add("archetype:shotgun")
    if any(member.weapon_type == "MG" for member in compiled.members):
        groups.add("archetype:mg")
    for effect in compiled.effects:
        stat = effect.stat or ""
        keys = {rule.event_key for rule in effect.triggers}
        if "core_hit" in keys:
            groups.add("mechanic:core_hit_count")
        if "crit_hit" in keys:
            groups.add("mechanic:crit_hit_count")
        if stat in {"ammo_charge_flat", "ammo_charge_pct"}:
            groups.add("mechanic:ammo_refill")
        if effect.effect_type == "dot":
            groups.add("mechanic:dot")
    return tuple(sorted(groups))


def run_public_probe(*, top_n: int = 10, top_k: int = 20) -> dict[str, Any]:
    rows: list[ProbeRow] = []

    for name, case in snapshot.SQUADS.items():
        members = tuple(case["members"])
        chars = dict(case.get("chars") or {})
        config = dict(case.get("config") or {})
        config["rng_mode"] = "expected"
        enemy = dict(case.get("enemy") or {})
        seed = int(case.get("seed", 42))

        moris_squad = spec.build_squad(list(members), chars)
        moris_config = spec.build_config(moris_squad, config)
        t0 = perf_counter()
        moris = simulate(
            moris_squad,
            config=moris_config,
            enemy=enemy,
            seed=seed,
            verbose=False,
        )
        moris_seconds = perf_counter() - t0
        moris_score = float(moris.squad_total)

        input_blockers = _input_blockers(config, {**DEFAULT_ENEMY, **enemy})
        raw_fast_score: float | None = None
        certified_fast_score: float | None = None
        unsupported: tuple[str, ...] = ()
        blockers = list(input_blockers)
        fast_seconds = 0.0
        groups: tuple[str, ...] = ()

        try:
            compiled = compile_moris_squad(moris_squad)
            groups = _groups(compiled)
            policy = compile_burst_policy(moris_squad, compiled, config)
            fast_enemy = _fast_enemy({**DEFAULT_ENEMY, **enemy}, duration=policy.duration)
            blockers.extend(static_score_blockers(compiled))

            if not blockers:
                t1 = perf_counter()
                fast = score_static_squad(compiled, policy, fast_enemy)
                fast_seconds = perf_counter() - t1
                raw_fast_score = float(fast.squad_total)
                unsupported = tuple(fast.unsupported)
                if not unsupported:
                    certified_fast_score = raw_fast_score
        except NotImplementedError as exc:
            blockers.append("runtime:" + str(exc).split(":", 1)[0])
        except Exception as exc:  # Research probe: classify instead of aborting corpus.
            blockers.append(f"probe_error:{type(exc).__name__}")

        relative_error = None
        if certified_fast_score is not None and moris_score:
            relative_error = certified_fast_score / moris_score - 1.0

        rows.append(
            ProbeRow(
                name=name,
                members=members,
                moris_score=moris_score,
                raw_fast_score=raw_fast_score,
                certified_fast_score=certified_fast_score,
                relative_error=relative_error,
                blockers=tuple(dict.fromkeys(blockers)),
                unsupported=unsupported,
                groups=groups,
                moris_seconds=moris_seconds,
                fast_seconds=fast_seconds,
            )
        )

    observations = [
        RankingObservation(
            members=row.members,
            moris_score=row.moris_score,
            fast_score=row.certified_fast_score,
            blockers=row.blockers,
            unsupported=row.unsupported,
            groups=row.groups,
        )
        for row in rows
    ]
    coverage = analyze_fast_moris_ranking(observations, top_n=top_n, top_k=top_k)

    clean = [row for row in rows if row.certified_fast_score is not None]
    clean_metrics = None
    if clean:
        clean_top_n = min(5, len(clean))
        clean_top_k = min(max(clean_top_n, 10), len(clean))
        clean_metrics = analyze_fast_moris_ranking(
            [
                RankingObservation(
                    members=row.members,
                    moris_score=row.moris_score,
                    fast_score=row.certified_fast_score,
                    groups=row.groups,
                )
                for row in clean
            ],
            top_n=clean_top_n,
            top_k=clean_top_k,
        )

    rel = [row.relative_error for row in clean if row.relative_error is not None]
    blocker_families = Counter(
        blocker.split(":", 1)[0]
        for row in rows
        for blocker in row.blockers
    )
    unsupported_families = Counter(
        item.split(":", 1)[0]
        for row in rows
        for item in row.unsupported
    )

    return {
        "corpus": "context.snapshot.SQUADS",
        "candidate_source": "fixed-public-corpus; optimizer candidate generation bypassed",
        "rng_mode": "expected",
        "team_count": len(rows),
        "certified_team_count": len(clean),
        "coverage_gap_count": len(rows) - len(clean),
        "moris_sim_seconds": sum(row.moris_seconds for row in rows),
        "fast_score_seconds_certified_or_attempted": sum(row.fast_seconds for row in rows),
        "certified_top_n_in_top_k": asdict(coverage),
        "clean_ranking": asdict(clean_metrics) if clean_metrics is not None else None,
        "clean_relative_error": {
            "median": median(rel) if rel else None,
            "min": min(rel) if rel else None,
            "max": max(rel) if rel else None,
        },
        "blocker_family_counts": sorted(blocker_families.items(), key=lambda item: (-item[1], item[0])),
        "unsupported_family_counts": sorted(unsupported_families.items(), key=lambda item: (-item[1], item[0])),
        "rows": [asdict(row) for row in rows],
    }


def main() -> None:
    report = run_public_probe()
    print("=== Fast vs Moris public fixed-corpus ranking probe ===")
    print(f"teams={report['team_count']} certified={report['certified_team_count']} coverage_gaps={report['coverage_gap_count']}")
    print(f"moris_seconds={report['moris_sim_seconds']:.3f} fast_seconds={report['fast_score_seconds_certified_or_attempted']:.3f}")
    coverage = report["certified_top_n_in_top_k"]
    print(
        "coverage: "
        f"top{coverage['top_n']} recall in Fast top{coverage['top_k']}="
        f"{coverage['top_n_recall']:.3f}; blocked={coverage['top_n_blocked']}; "
        f"ranked_out={coverage['top_n_ranked_out']}"
    )
    clean = report["clean_ranking"]
    if clean is not None:
        print(
            "clean: "
            f"teams={clean['candidate_count']} pairwise={clean['pairwise_accuracy']} "
            f"top{clean['top_n']}_in_top{clean['top_k']}={clean['top_n_recall']:.3f}"
        )
    print("blocker_families=", report["blocker_family_counts"])
    print("unsupported_families=", report["unsupported_family_counts"])
    print("PUBLIC_RANKING_REPORT=" + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
