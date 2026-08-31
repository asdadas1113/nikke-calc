"""Measure MorisEvaluator cache retention without changing combat semantics.

This benchmark uses the real ``SimResult`` and ``HitEvent`` payload classes but an
injected simulator so the measurement isolates optimizer-cache retention rather
than combat CPU.  ``hits-per-result=19195`` matches the previously observed
180-second benchmark payload size in docs/BENCHMARK.md.

Each CLI invocation must run in a fresh process.  ``score-only`` still constructs
one full SimResult per evaluation, then immediately replaces only the cached entry
with an equivalent Evaluation whose ``raw`` field is None.  Its peak/current RSS
therefore includes normal one-result transient cost but not N-result retention.
"""

from __future__ import annotations

import argparse
import gc
import json
import resource
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from calculator.sim_result import HitEvent, SimResult
from optimizer.evaluator import CacheIdentity, MorisEvaluator


def _rss_kib() -> int:
    with open("/proc/self/status", encoding="utf-8") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    raise RuntimeError("VmRSS not found")


def _payload(index: int, hit_count: int) -> SimResult:
    caster = f"C{index % 7}"
    hits = [
        HitEvent(
            t=float(i) / 60.0,
            caster=caster,
            damage=i + index,
            is_crit=False,
            hit_tag="normal",
            skill_name="기본 공격",
        )
        for i in range(hit_count)
    ]
    total = sum(hit.damage for hit in hits)
    return SimResult(
        hits=hits,
        char_total={caster: total},
        squad_total=total,
        duration=180.0,
        log=None,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("raw", "score-only"), required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--hits-per-result", type=int, default=19195)
    args = ap.parse_args()
    if args.count <= 0 or args.hits_per_result < 0:
        raise ValueError("count must be positive and hits-per-result non-negative")

    call_index = 0

    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, *, config, enemy, seed, verbose):
        nonlocal call_index
        result = _payload(call_index, args.hits_per_result)
        call_index += 1
        return result

    evaluator = MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("cache-memory-benchmark", "synthetic-account"),
        use_cache=True,
    )

    gc.collect()
    rss_start = _rss_kib()
    for i in range(args.count):
        result = evaluator.evaluate(("A", f"B{i}"))
        if args.mode == "score-only":
            # Deliberately benchmark the storage policy without changing
            # MorisEvaluator yet. Dict insertion order makes this the entry just
            # created by the evaluate() call above.
            key = next(reversed(evaluator._cache))
            cached = evaluator._cache[key]
            evaluator._cache[key] = replace(cached, raw=None)
        result = None
    gc.collect()

    rss_end = _rss_kib()
    peak_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    print(json.dumps({
        "mode": args.mode,
        "count": args.count,
        "hits_per_result": args.hits_per_result,
        "cache_size": evaluator.cache_size,
        "simulate_calls": evaluator.stats.simulate_calls,
        "rss_start_kib": rss_start,
        "rss_end_kib": rss_end,
        "rss_growth_kib": rss_end - rss_start,
        "peak_rss_kib": peak_kib,
        "growth_per_cached_eval_kib": (rss_end - rss_start) / args.count,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
