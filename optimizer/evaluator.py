"""Thin adapter around Moris' build_squad -> build_config -> simulate path.

The optimizer must not know calculator internals. This module is the only place
that depends on Moris evaluator call signatures, and the callables are injectable
so search code can be tested without running the expensive simulator.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

BuildSquad = Callable[[Sequence[str], Mapping[str, Any]], Any]
BuildConfig = Callable[[Any, Mapping[str, Any]], Any]
Simulate = Callable[..., Any]


@dataclass(frozen=True)
class CacheIdentity:
    """External identities that must partition evaluator cache entries."""

    engine_commit: str
    account_snapshot: str

    def __post_init__(self) -> None:
        if not self.engine_commit.strip():
            raise ValueError("engine_commit must not be empty")
        if not self.account_snapshot.strip():
            raise ValueError("account_snapshot must not be empty")


@dataclass(frozen=True)
class EvaluationTimings:
    build_squad_s: float
    build_config_s: float
    simulate_s: float

    @property
    def total_s(self) -> float:
        return self.build_squad_s + self.build_config_s + self.simulate_s


@dataclass(frozen=True)
class Evaluation:
    members: tuple[str, ...]
    score: float
    timings: EvaluationTimings
    cache_hit: bool
    raw: Any


@dataclass
class EvaluatorStats:
    requests: int = 0
    cache_hits: int = 0
    simulate_calls: int = 0
    build_squad_s: float = 0.0
    build_config_s: float = 0.0
    simulate_s: float = 0.0


class MorisEvaluator:
    """Evaluate an ordered squad using Moris while counting expensive calls.

    ``rng_mode="expected"`` and ``verbose=False`` are optimizer defaults. Squad
    order is deliberately part of the cache key because Moris can use order for
    burst priority/operation.

    Cached evaluators require an explicit engine commit and account/build snapshot
    identity. This prevents persistent or reused evaluator instances from silently
    mixing results across engine/profile revisions.
    """

    def __init__(
        self,
        build_squad: BuildSquad,
        build_config: BuildConfig,
        simulate: Simulate,
        *,
        cache_identity: CacheIdentity | None = None,
        use_cache: bool = True,
    ) -> None:
        if use_cache and cache_identity is None:
            raise ValueError("cache_identity is required when evaluator cache is enabled")
        self._build_squad = build_squad
        self._build_config = build_config
        self._simulate = simulate
        self._use_cache = use_cache
        self._cache_identity = cache_identity
        self._cache: dict[str, Evaluation] = {}
        self.stats = EvaluatorStats()

    @classmethod
    def from_moris(
        cls,
        *,
        engine_commit: str,
        account_snapshot: str,
        use_cache: bool = True,
    ) -> "MorisEvaluator":
        """Bind to the same engine entry points used by site/pybridge/bridge.py."""
        from calculator.timeline import simulate
        from context import spec as char_spec

        identity = CacheIdentity(engine_commit, account_snapshot) if use_cache else None
        return cls(
            char_spec.build_squad,
            char_spec.build_config,
            simulate,
            cache_identity=identity,
            use_cache=use_cache,
        )

    def clear_cache(self) -> None:
        self._cache.clear()

    def evaluate(
        self,
        members: Sequence[str],
        *,
        characters: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        enemy: Mapping[str, Any] | None = None,
        seed: int = 42,
        verbose: bool = False,
    ) -> Evaluation:
        ordered = tuple(members)
        if not ordered:
            raise ValueError("members must not be empty")

        char_input = copy.deepcopy(dict(characters or {}))
        config_input = copy.deepcopy(dict(config or {}))
        config_input.setdefault("rng_mode", "expected")
        config_input.setdefault("immune_blocks_burst", True)
        enemy_input = copy.deepcopy(dict(enemy or {}))

        key = self._cache_key(
            ordered,
            char_input,
            config_input,
            enemy_input,
            seed=seed,
            verbose=verbose,
            cache_identity=self._cache_identity,
        )
        self.stats.requests += 1
        cached = self._cache.get(key) if self._use_cache else None
        if cached is not None:
            self.stats.cache_hits += 1
            return Evaluation(
                members=cached.members,
                score=cached.score,
                timings=EvaluationTimings(0.0, 0.0, 0.0),
                cache_hit=True,
                raw=cached.raw,
            )

        t0 = perf_counter()
        squad = self._build_squad(list(ordered), char_input)
        t1 = perf_counter()
        built_config = self._build_config(squad, config_input)
        t2 = perf_counter()
        result = self._simulate(
            squad,
            config=built_config,
            enemy=enemy_input,
            seed=seed,
            verbose=verbose,
        )
        t3 = perf_counter()

        timings = EvaluationTimings(t1 - t0, t2 - t1, t3 - t2)
        score = float(result.squad_total)
        evaluation = Evaluation(ordered, score, timings, False, result)

        self.stats.simulate_calls += 1
        self.stats.build_squad_s += timings.build_squad_s
        self.stats.build_config_s += timings.build_config_s
        self.stats.simulate_s += timings.simulate_s
        if self._use_cache:
            self._cache[key] = evaluation
        return evaluation

    @staticmethod
    def _cache_key(
        members: tuple[str, ...],
        characters: Mapping[str, Any],
        config: Mapping[str, Any],
        enemy: Mapping[str, Any],
        *,
        seed: int,
        verbose: bool,
        cache_identity: CacheIdentity | None,
    ) -> str:
        payload = {
            "engine_commit": cache_identity.engine_commit if cache_identity else None,
            "account_snapshot": cache_identity.account_snapshot if cache_identity else None,
            "members": members,
            "characters": characters,
            "config": config,
            "enemy": enemy,
            "seed": seed,
            "verbose": verbose,
        }
        try:
            return json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except TypeError as exc:
            raise TypeError("evaluator inputs must be JSON-serializable for stable caching") from exc
