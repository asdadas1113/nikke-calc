from __future__ import annotations

from . import public_ranking_probe as probe


_original_analyze = probe.analyze_fast_moris_ranking


def _dedupe_analyze(observations, *, top_n: int, top_k: int):
    """Rank unique memberships while leaving 24 source-case coverage untouched.

    The standardized corpus intentionally retains duplicate source cases because
    each source case is a coverage observation. The ranking validator, correctly,
    rejects duplicate optimizer candidates. Deduplicate only at the metric call
    boundary so source-case coverage counts and blocker frequencies keep their
    historical meaning.
    """
    unique = []
    seen = set()
    for row in observations:
        members = tuple(row.members)
        if members in seen:
            continue
        seen.add(members)
        unique.append(row)
    if not unique:
        return _original_analyze(unique, top_n=0, top_k=0)
    return _original_analyze(
        unique,
        top_n=min(int(top_n), len(unique)),
        top_k=min(int(top_k), len(unique)),
    )


def main() -> None:
    probe.analyze_fast_moris_ranking = _dedupe_analyze
    probe.main()


if __name__ == "__main__":
    main()
