"""Public Enikk S33-S40 usage-bound study under a certified cohort contract.

Network benchmark only.  It uses no private account data.  The cohort contract is
explicitly the shape verified by the separate public completeness probe:
6 server ladders x ranks 1..50, with exactly five five-character teams per
returned player row.

Missing/malformed/truly-unmapped player slots are not zero-filled.  Known
ambiguous external labels are localized to their possible canonical characters
rather than spreading uncertainty across the whole roster.  For every
source-known canonical character the script reports conservative lower/upper
usage bounds and summarizes how many eight-season windows are safely <=1%,
definitely >1%, or straddle the boundary.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from optimizer.meta_usage import build_external_name_mapping
from optimizer.meta_usage_bounds import (
    RankingCoverageContract,
    aggregate_bounded_character_window,
    certify_enikk_rankings,
)

ENDPOINT = "https://enikk.app/api/graphql"
RAIDS = tuple(range(33, 41))
CONTRACT = RankingCoverageContract(
    servers=("GLOBAL", "JP", "KR", "NA", "SEA", "TW-HK"),
    rank_start=1,
    rank_end=50,
    team_count=5,
    team_size=5,
    source="enikk-public-probe:S33-S40:6servers-rank1-50:5x5",
)
BOUNDARY = 0.01


def graphql(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "nikke-calc optimizer bounded usage benchmark",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"Enikk GraphQL errors: {payload['errors'][:1]}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Enikk GraphQL returned no data")
    return data


def local_resource_map() -> dict[int, str]:
    raw = json.loads((ROOT / "scraper" / "nikke_scraped.json").read_text(encoding="utf-8"))
    result = {}
    for name, row in raw.items():
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        try:
            result[int(row["id"])] = str(name)
        except (TypeError, ValueError):
            continue
    return result


def fetch_name_map():
    data = graphql("{ characters { resource_id name_localkey } }")
    rows = data.get("characters") or []
    return build_external_name_mapping(
        (row for row in rows if isinstance(row, dict)),
        local_resource_map(),
    )


def fetch_rankings(raid: int) -> list[dict]:
    data = graphql(
        "query($raid: Float!) { SRRankings(raid: $raid) { rank playerid server damage cp teams } }",
        {"raid": raid},
    )
    return [
        row for row in (data.get("SRRankings") or [])
        if isinstance(row, dict)
    ]


def pct(value: float | None) -> str:
    return "NA" if value is None else f"{value * 100:.3f}%"


def main() -> None:
    external_map = fetch_name_map()
    snapshots = []
    for raid in RAIDS:
        snapshot = certify_enikk_rankings(
            raid,
            fetch_rankings(raid),
            external_map.mapping,
            contract=CONTRACT,
            ambiguous_name_map=external_map.ambiguous_labels,
        )
        snapshots.append(snapshot)
        print(json.dumps({
            "raid": raid,
            "expected_slots": snapshot.expected_player_slots,
            "complete_rows": snapshot.observed_complete_player_slots,
            "missing_rows": snapshot.missing_player_slots,
            "malformed_rows": snapshot.malformed_player_slots,
            "mapping_uncertain_rows": snapshot.mapping_uncertain_player_slots,
            "ambiguous_candidate_rows": sum(snapshot.ambiguous_player_slots.values()),
            "max_character_uncertain_rows": snapshot.uncertain_player_slots,
            "unknown_or_ambiguous_external_names": len(snapshot.unknown_external_names),
        }, sort_keys=True))

    source_known_names = set(external_map.mapping.values())
    for candidates in external_map.ambiguous_labels.values():
        source_known_names.update(candidates)

    rows = []
    for name in sorted(source_known_names):
        window = aggregate_bounded_character_window(
            name,
            snapshots,
            eligible_raids=RAIDS,
        )
        if not window.complete_for_requested_window:
            continue
        lower = window.peak_lower_usage
        upper = window.peak_upper_usage
        if lower is None or upper is None:
            continue
        if upper <= BOUNDARY:
            verdict = "safe<=1%"
        elif lower > BOUNDARY:
            verdict = "definitely>1%"
        else:
            verdict = "crosses-boundary"
        rows.append((name, lower, upper, verdict, window))

    counts = {}
    for _name, _lower, _upper, verdict, _window in rows:
        counts[verdict] = counts.get(verdict, 0) + 1
    print(json.dumps({
        "source_known_characters": len(source_known_names),
        "complete_bound_windows": len(rows),
        "boundary": BOUNDARY,
        "verdict_counts": dict(sorted(counts.items())),
        "ambiguous_external_labels": len(external_map.ambiguous_labels),
        "ambiguous_label_candidates": {
            label: list(candidates)
            for label, candidates in sorted(external_map.ambiguous_labels.items())
        },
        "resource_unmapped_rows": external_map.unmapped_source_rows,
    }, sort_keys=True, ensure_ascii=False))

    safe = sorted(
        (row for row in rows if row[3] == "safe<=1%"),
        key=lambda row: (row[2], row[1], row[0]),
    )
    crossing = sorted(
        (row for row in rows if row[3] == "crosses-boundary"),
        key=lambda row: (row[2], row[1], row[0]),
    )

    print(f"SAFE <=1% ({len(safe)}):")
    for name, lower, upper, _verdict, window in safe:
        vector = ",".join(
            f"S{raid}:{lo*100:.2f}-{hi*100:.2f}%"
            for raid, lo, hi in window.bounds
        )
        print(f"  {name}: peak={pct(lower)}..{pct(upper)} [{vector}]")

    print(f"CROSSES 1% ({len(crossing)}):")
    for name, lower, upper, _verdict, window in crossing[:40]:
        vector = ",".join(
            f"S{raid}:{lo*100:.2f}-{hi*100:.2f}%"
            for raid, lo, hi in window.bounds
        )
        print(f"  {name}: peak={pct(lower)}..{pct(upper)} [{vector}]")


if __name__ == "__main__":
    main()
