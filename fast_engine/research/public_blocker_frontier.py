from __future__ import annotations

"""Summarize which fixed public squads are closest to Fast certification.

This is intentionally optimizer-independent. It consumes the standardized
public ranking probe and reports coverage pressure only; blocked squads are not
interpreted as ranking false negatives.
"""

from collections import Counter
import json

from .public_ranking_probe import run_public_probe


def summarize_frontier(report: dict, *, limit: int = 10) -> dict:
    rows = report["rows"]
    frontier = []
    for row in rows:
        blockers = tuple(row["blockers"])
        unsupported = tuple(row["unsupported"])
        unresolved = blockers + tuple(f"unsupported:{item}" for item in unsupported)
        frontier.append(
            {
                "source_name": row["source_name"],
                "members": row["members"],
                "moris_score": row["moris_score"],
                "blocker_count": len(blockers),
                "unsupported_count": len(unsupported),
                "unresolved_count": len(unresolved),
                "unresolved": unresolved,
            }
        )

    frontier.sort(
        key=lambda row: (
            row["unresolved_count"],
            row["blocker_count"],
            -row["moris_score"],
            row["source_name"],
        )
    )

    unresolved_histogram = Counter(row["unresolved_count"] for row in frontier)
    blocker_pressure = Counter(
        blocker
        for row in rows
        for blocker in row["blockers"]
    )

    minimum = frontier[0]["unresolved_count"] if frontier else 0
    nearest = [row for row in frontier if row["unresolved_count"] == minimum]

    return {
        "team_count": len(frontier),
        "certified_team_count": report["certified_team_count"],
        "coverage_gap_count": report["coverage_gap_count"],
        "minimum_unresolved_count": minimum,
        "nearest_team_count": len(nearest),
        "nearest_teams": nearest,
        "unresolved_count_histogram": sorted(unresolved_histogram.items()),
        "top_blocker_pressure": blocker_pressure.most_common(20),
        "frontier": frontier[:limit],
        "interpretation": (
            "candidate generation bypassed -> Fast coverage gap; ranking accuracy "
            "is measurable only after certified scores exist"
        ),
    }


def main() -> None:
    summary = summarize_frontier(run_public_probe())
    print(
        "frontier: "
        f"teams={summary['team_count']} certified={summary['certified_team_count']} "
        f"minimum_unresolved={summary['minimum_unresolved_count']} "
        f"nearest_teams={summary['nearest_team_count']}"
    )
    print("unresolved_histogram=", summary["unresolved_count_histogram"])
    for row in summary["frontier"]:
        print(
            f"FRONTIER {row['unresolved_count']:02d} {row['source_name']}: "
            + " | ".join(row["unresolved"])
        )
    print("top_blocker_pressure=", summary["top_blocker_pressure"])
    print("PUBLIC_BLOCKER_FRONTIER=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
