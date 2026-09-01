from __future__ import annotations

"""Optimizer-independent Fast-vs-Moris ranking probe on one common scenario.

The source of squad memberships is ``context.snapshot.SQUADS`` because it is a
public, mechanic-rich collection that predates the Fast ranking experiment. Its
per-case config/enemy/build overrides are deliberately NOT reused here: mixing
scores from different scenarios would make the ranking itself invalid.

The probe therefore keeps only real five-character ordered squads, deduplicates
identical ordered squads, rebuilds all squads with the same public defaults, and
evaluates every squad under one common config/enemy. Fast blockers or unsupported
damage remain coverage gaps rather than artificial low scores.

This is a first engine-ranking diagnosis, not a production optimizer benchmark.
The corpus is curated and small, so its recall numbers are not production
shortlist guarantees.
"""

from collections import Counter
from dataclasses import asdict, dataclass
import json
from statistics import median
from time import perf_counter

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers
from optimizer.validation import RankingObservation, analyze_fast_moris_ranking


COMMON_CONFIG = {
    "duration": 180.0,
    "first_burst_time": 3.0,
    "rng_mode": "expected",
}
COMMON_ENEMY = dict(DEFAULT_ENEMY)


@dataclass(frozen=True)
class ProbeRow:
    source_name: str
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


def _source_corpus() -> tuple[tuple[tuple[str, ...], str], ...]:
    seen: set[tuple[str, ...]] = set()
    rows: list[tuple[tuple[str, ...], str]] = []
    for name, case in snapshot.SQUADS.items():
        members = tuple(str(member) for member in case["members"])
        if len(members) != 5:
            continue
        if any(member.startswith("test_") for member in members):
            continue
        if members in seen:
            continue
        seen.add(members)
        rows.append((members, str(name)))
    return tuple(rows)


def _fast_enemy(*, duration: float) -> EnemyStaticProfile:
    core_px = float(COMMON_ENEMY.get("core_px", 0.0) or 0.0)
    return EnemyStaticProfile(
        defense=float(COMMON_ENEMY.get("def", 31784.0)),
        element=COMMON_ENEMY.get("code"),
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


def run_public_probe(*, top_n: int = 10, top_k: int = 20) -> dict:
    corpus = _source_corpus()
    rows: list[ProbeRow] = []

    for members, source_name in corpus:
        # Snapshot case-specific chars/config/enemy overrides are deliberately ignored.
        moris_squad = spec.build_squad(list(members))
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
        moris_score = float(moris.squad_total)

        raw_fast_score: float | None = None
        certified_fast_score: float | None = None
        unsupported: tuple[str, ...] = ()
        blockers: list[str] = []
        fast_seconds = 0.0

        compiled = compile_moris_squad(moris_squad)
        groups = _groups(compiled)
        policy = compile_burst_policy(moris_squad, compiled, dict(COMMON_CONFIG))
        blockers.extend(static_score_blockers(compiled))

        if not blockers:
            try:
                t1 = perf_counter()
                fast = score_static_squad(compiled, policy, _fast_enemy(duration=policy.duration))
                fast_seconds = perf_counter() - t1
                raw_fast_score = float(fast.squad_total)
                unsupported = tuple(fast.unsupported)
                if not unsupported:
                    certified_fast_score = raw_fast_score
            except NotImplementedError as exc:
                blockers.append("runtime:" + str(exc).split(":", 1)[0])
            except Exception as exc:
                blockers.append(f"probe_error:{type(exc).__name__}")

        relative_error = None
        if certified_fast_score is not None and moris_score:
            relative_error = certified_fast_score / moris_score - 1.0

        rows.append(
            ProbeRow(
                source_name=source_name,
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
    coverage = analyze_fast_moris_ranking(
        observations,
        top_n=min(top_n, len(observations)),
        top_k=min(top_k, len(observations)),
    )

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
        "corpus": "unique real five-person memberships from context.snapshot.SQUADS",
        "candidate_source": "fixed public memberships; optimizer candidate generation bypassed",
        "scenario_contract": {
            "build": "context.spec public defaults; snapshot chars overrides ignored",
            "config": dict(COMMON_CONFIG),
            "enemy": dict(COMMON_ENEMY),
            "snapshot_case_config_used": False,
            "snapshot_case_enemy_used": False,
            "snapshot_case_chars_used": False,
        },
        "snapshot_source_case_count": len(snapshot.SQUADS),
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
    print("=== Fast vs Moris standardized public-membership ranking probe ===")
    print(
        f"teams={report['team_count']} certified={report['certified_team_count']} "
        f"coverage_gaps={report['coverage_gap_count']}"
    )
    print(
        f"moris_seconds={report['moris_sim_seconds']:.3f} "
        f"fast_seconds={report['fast_score_seconds_certified_or_attempted']:.3f}"
    )
    coverage = report["certified_top_n_in_top_k"]
    print(
        "coverage: "
        f"top{coverage['top_n']} certified survival in Fast top{coverage['top_k']}="
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
    print("clean_relative_error=", report["clean_relative_error"])
    print("blocker_families=", report["blocker_family_counts"])
    print("unsupported_families=", report["unsupported_family_counts"])
    print("PUBLIC_RANKING_REPORT=" + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
