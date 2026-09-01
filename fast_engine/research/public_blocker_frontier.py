from __future__ import annotations

"""Summarize which fixed public squads are closest to Fast certification.

Unlike the ranking probe, this coverage scan deliberately does not run Moris.
Blocker discovery depends only on the compiled Fast capability surface, so a
full reference simulation would add ~minute-scale cost without changing the
frontier. If a squad has no static blockers, Fast scoring is attempted to expose
runtime/unsupported gaps before calling it certified.
"""

from collections import Counter
import json

from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import score_static_squad, static_score_blockers

from .public_ranking_probe import COMMON_CONFIG, _fast_enemy, _source_corpus


def _conceptual_key(item: str) -> str:
    """Collapse duplicate normal/skill delivery reports into one mechanism."""

    for prefix in ("normal_delivery:", "skill_state_delivery:"):
        if item.startswith(prefix):
            return "damage_delivery:" + item[len(prefix):]
    return item


def scan_public_blockers() -> dict:
    rows = []
    certified = 0

    for members, source_name in _source_corpus():
        moris_squad = spec.build_squad(list(members))
        compiled = compile_moris_squad(moris_squad)
        blockers = list(static_score_blockers(compiled))
        unsupported: tuple[str, ...] = ()

        if not blockers:
            policy = compile_burst_policy(
                moris_squad,
                compiled,
                dict(COMMON_CONFIG),
            )
            try:
                fast = score_static_squad(
                    compiled,
                    policy,
                    _fast_enemy(duration=policy.duration),
                )
                unsupported = tuple(fast.unsupported)
            except NotImplementedError as exc:
                blockers.append("runtime:" + str(exc).split(":", 1)[0])
            except Exception as exc:
                blockers.append(f"probe_error:{type(exc).__name__}")

        if not blockers and not unsupported:
            certified += 1

        rows.append(
            {
                "source_name": source_name,
                "members": members,
                "blockers": tuple(dict.fromkeys(blockers)),
                "unsupported": unsupported,
            }
        )

    return {
        "team_count": len(rows),
        "certified_team_count": certified,
        "coverage_gap_count": len(rows) - certified,
        "rows": rows,
    }


def summarize_frontier(report: dict, *, limit: int = 10) -> dict:
    rows = report["rows"]
    frontier = []
    for row in rows:
        blockers = tuple(row["blockers"])
        unsupported = tuple(row["unsupported"])
        unresolved = blockers + tuple(f"unsupported:{item}" for item in unsupported)
        conceptual = tuple(dict.fromkeys(_conceptual_key(item) for item in unresolved))
        frontier.append(
            {
                "source_name": row["source_name"],
                "members": row["members"],
                "blocker_count": len(blockers),
                "unsupported_count": len(unsupported),
                "unresolved_count": len(unresolved),
                "conceptual_count": len(conceptual),
                "unresolved": unresolved,
                "conceptual": conceptual,
            }
        )

    frontier.sort(
        key=lambda row: (
            row["conceptual_count"],
            row["unresolved_count"],
            row["source_name"],
        )
    )

    unresolved_histogram = Counter(row["unresolved_count"] for row in frontier)
    conceptual_histogram = Counter(row["conceptual_count"] for row in frontier)
    blocker_pressure = Counter(
        blocker
        for row in rows
        for blocker in row["blockers"]
    )
    conceptual_pressure = Counter(
        _conceptual_key(blocker)
        for row in rows
        for blocker in row["blockers"]
    )

    minimum_unresolved = min(
        (row["unresolved_count"] for row in frontier),
        default=0,
    )
    minimum_conceptual = min(
        (row["conceptual_count"] for row in frontier),
        default=0,
    )
    nearest = [
        row for row in frontier if row["conceptual_count"] == minimum_conceptual
    ]

    return {
        "team_count": len(frontier),
        "certified_team_count": report["certified_team_count"],
        "coverage_gap_count": report["coverage_gap_count"],
        "minimum_unresolved_count": minimum_unresolved,
        "minimum_conceptual_count": minimum_conceptual,
        "nearest_team_count": len(nearest),
        "nearest_teams": nearest,
        "unresolved_count_histogram": sorted(unresolved_histogram.items()),
        "conceptual_count_histogram": sorted(conceptual_histogram.items()),
        "top_blocker_pressure": blocker_pressure.most_common(20),
        "top_conceptual_pressure": conceptual_pressure.most_common(20),
        "frontier": frontier[:limit],
        "interpretation": (
            "candidate generation bypassed -> Fast coverage gap; ranking accuracy "
            "is measurable only after certified scores exist"
        ),
    }


def main() -> None:
    summary = summarize_frontier(scan_public_blockers())
    print(
        "frontier: "
        f"teams={summary['team_count']} certified={summary['certified_team_count']} "
        f"minimum_unresolved={summary['minimum_unresolved_count']} "
        f"minimum_conceptual={summary['minimum_conceptual_count']} "
        f"nearest_teams={summary['nearest_team_count']}"
    )
    print("unresolved_histogram=", summary["unresolved_count_histogram"])
    print("conceptual_histogram=", summary["conceptual_count_histogram"])
    for row in summary["frontier"]:
        print(
            f"FRONTIER raw={row['unresolved_count']:02d} "
            f"conceptual={row['conceptual_count']:02d} {row['source_name']}: "
            + " | ".join(row["conceptual"])
        )
    print("top_blocker_pressure=", summary["top_blocker_pressure"])
    print("top_conceptual_pressure=", summary["top_conceptual_pressure"])
    print("PUBLIC_BLOCKER_FRONTIER=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
