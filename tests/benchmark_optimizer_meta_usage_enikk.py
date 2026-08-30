"""Public Enikk Solo Raid usage-distribution study.

This is a network benchmark/data-inspection script, not a unit test. It fetches
public Enikk GraphQL rankings and prints threshold-free evidence for completed
seasons. No account/profile data is read or uploaded.

The script deliberately does not declare ``low_usage``. For historical zeroes
it uses only a conservative established cohort: a character must have appeared
at least once on or before the start season of the inspected window. Positive
appearance proves the character existed by then; absence before first appearance
is not interpreted as zero/release evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from optimizer.meta_usage import (
    aggregate_character_window,
    build_external_name_mapping,
    summarize_enikk_rankings,
)

ENDPOINT = "https://enikk.app/api/graphql"
PEAK_BINS = (0.0035, 0.01, 0.02, 0.05, 0.10)


def graphql(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "nikke-calc optimizer public benchmark",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"Enikk GraphQL errors: {payload['errors'][:1]}")
    if not isinstance(payload.get("data"), dict):
        raise RuntimeError("Enikk GraphQL returned no data")
    return payload["data"]


def local_resource_map() -> dict[int, str]:
    raw = json.loads((ROOT / "scraper" / "nikke_scraped.json").read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for name, row in raw.items():
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        try:
            out[int(row["id"])] = str(name)
        except (TypeError, ValueError):
            continue
    return out


def fetch_name_map():
    data = graphql("{ characters { resource_id name_localkey } }")
    rows = data.get("characters") or []
    return build_external_name_mapping(
        (row for row in rows if isinstance(row, dict)),
        local_resource_map(),
    )


def fetch_summaries() -> dict[int, str]:
    data = graphql("{ soloRaidSummaries { raid_number wave_name weakness } }")
    return {
        int(row["raid_number"]): str(row.get("wave_name") or "")
        for row in data.get("soloRaidSummaries") or []
        if isinstance(row, dict) and row.get("raid_number") is not None
    }


def fetch_rankings(raid: int) -> list[dict]:
    data = graphql(
        "query($raid: Float!) { SRRankings(raid: $raid) { rank playerid server damage cp teams } }",
        {"raid": raid},
    )
    rows = data.get("SRRankings") or []
    return [row for row in rows if isinstance(row, dict)]


def parse_raids(value: str) -> tuple[int, ...]:
    value = value.strip()
    if "-" in value and "," not in value:
        start_text, end_text = value.split("-", 1)
        start, end = int(start_text), int(end_text)
        if start <= 0 or end < start:
            raise argparse.ArgumentTypeError("raid range must be positive start-end")
        return tuple(range(start, end + 1))
    raids = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not raids or any(raid <= 0 for raid in raids) or len(set(raids)) != len(raids):
        raise argparse.ArgumentTypeError("raids must be unique positive integers")
    return raids


def pct(value: float | None) -> str:
    return "NA" if value is None else f"{value * 100:.3f}%"


def window_rows(snapshots, raids: tuple[int, ...], first_seen: dict[str, int]):
    start = raids[0]
    established = sorted(name for name, first in first_seen.items() if first <= start)
    rows = []
    for name in established:
        stats = aggregate_character_window(name, snapshots, eligible_raids=raids)
        if stats.complete_for_requested_window:
            rows.append(stats)
    return established, rows


def peak_bin_counts(rows) -> tuple[int, ...]:
    return tuple(sum((row.peak_usage or 0.0) <= bound for row in rows) for bound in PEAK_BINS)


def descriptive_window(snapshots, raids: tuple[int, ...], first_seen: dict[str, int]) -> None:
    established, rows = window_rows(snapshots, raids, first_seen)
    print(f"\nWINDOW {len(raids)} seasons: S{raids[0]}-S{raids[-1]}")
    print(f"  conservative established cohort: {len(established)}")
    print(f"  complete mapped/coverage cohort: {len(rows)}")
    if not rows:
        return

    for bound, count in zip(PEAK_BINS, peak_bin_counts(rows)):
        print(f"  peak <= {bound * 100:.2f}%: {count}")

    by_positive_seasons: dict[int, int] = {}
    for row in rows:
        n = len(row.positive_raids)
        by_positive_seasons[n] = by_positive_seasons.get(n, 0) + 1
    print("  positive-season-count distribution:", dict(sorted(by_positive_seasons.items())))

    bottom = sorted(
        rows,
        key=lambda row: (
            row.peak_usage if row.peak_usage is not None else 1.0,
            len(row.positive_raids),
            row.median_usage if row.median_usage is not None else 1.0,
            row.character,
        ),
    )[:30]
    print("  bottom by peak usage (descriptive, not classified):")
    for row in bottom:
        vector = ",".join(f"S{raid}:{fraction*100:.1f}%" for raid, fraction in row.usage_fractions)
        print(
            f"    {row.character}: peak={pct(row.peak_usage)} median={pct(row.median_usage)} "
            f"positive={len(row.positive_raids)}/{len(raids)} [{vector}]"
        )


def rolling_summary(snapshots, raids: tuple[int, ...], first_seen: dict[str, int], size: int) -> None:
    print(f"\nROLLING SUMMARY {size}-season windows")
    print("  columns: window cohort complete zero_all peak<=0.35/1/2/5/10%")
    for offset in range(0, len(raids) - size + 1):
        window = tuple(raids[offset : offset + size])
        established, rows = window_rows(snapshots, window, first_seen)
        zero_all = sum(len(row.positive_raids) == 0 for row in rows)
        counts = "/".join(str(count) for count in peak_bin_counts(rows))
        print(
            f"  S{window[0]}-S{window[-1]} cohort={len(established)} complete={len(rows)} "
            f"zero_all={zero_all} peak_bins={counts}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raids",
        type=parse_raids,
        default=parse_raids("31-40"),
        help="inclusive range like 31-40 or comma list; default 31-40",
    )
    parser.add_argument(
        "--windows",
        default="6,8,10",
        help="suffix window lengths to inspect; default 6,8,10",
    )
    parser.add_argument(
        "--rolling-summary",
        action="store_true",
        help="also print compact rolling-window lower-tail counts",
    )
    args = parser.parse_args()
    raids: tuple[int, ...] = args.raids
    windows = tuple(int(part.strip()) for part in args.windows.split(",") if part.strip())
    if not windows or any(size <= 0 or size > len(raids) for size in windows):
        parser.error("window lengths must be positive and <= number of fetched raids")

    summaries = fetch_summaries()
    missing_summaries = [raid for raid in raids if raid not in summaries]
    if missing_summaries:
        raise RuntimeError(f"requested raids absent from Enikk summaries: {missing_summaries}")

    external_map = fetch_name_map()
    print(
        f"Enikk character catalog: {external_map.source_row_count}; "
        f"unambiguous local mappings: {len(external_map.mapping)}; "
        f"resource-unmapped rows: {external_map.unmapped_source_rows}; "
        f"ambiguous external labels: {len(external_map.ambiguous_labels)}"
    )
    if external_map.ambiguous_labels:
        for external, names in external_map.ambiguous_labels.items():
            print(f"  ambiguous label {external!r}: {names}")

    snapshots = []
    for raid in raids:
        rankings = fetch_rankings(raid)
        snapshot = summarize_enikk_rankings(
            raid,
            rankings,
            external_map.mapping,
            boss=summaries.get(raid),
        )
        snapshots.append(snapshot)
        usages = [
            count / snapshot.player_count
            for count in snapshot.player_appearances.values()
            if snapshot.player_count > 0
        ]
        positive_min = min(usages) if usages else None
        print(
            f"S{raid} {snapshot.boss}: players={snapshot.player_count} "
            f"players_with_teams={snapshot.players_with_teams} "
            f"incomplete={snapshot.incomplete_player_rows} "
            f"used_chars={len(snapshot.player_appearances)} "
            f"min_positive={pct(positive_min)} unknown_external={len(snapshot.unknown_external_names)}"
        )
        if snapshot.unknown_external_names:
            print("  unknown external names:", snapshot.unknown_external_names[:20])

    # First positive observation is a conservative proof that the character was
    # available by that season. It is NOT the actual release season.
    first_seen: dict[str, int] = {}
    for snapshot in snapshots:
        for name, count in snapshot.player_appearances.items():
            if count > 0:
                first_seen.setdefault(name, snapshot.raid)

    for size in windows:
        window_raids = tuple(raids[-size:])
        descriptive_window(snapshots, window_raids, first_seen)
        if args.rolling_summary:
            rolling_summary(snapshots, raids, first_seen, size)


if __name__ == "__main__":
    main()
