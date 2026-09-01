from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import inf
from typing import Any, Mapping

from context.spec import build_config

from .model import CompiledSquad
from .scheduler import EventKind, EventScheduler, ScheduledEvent

_EPS = 1e-9


class BurstPatternKind(str, Enum):
    EVERY = "every"
    CYCLES = "cycles"
    LAST = "last"


@dataclass(frozen=True, slots=True)
class BurstPattern:
    kind: BurstPatternKind
    every: int | None = None
    cycles: frozenset[int] = frozenset()
    last_seconds: float | None = None

    def rank(self, cycle: int, now: float, duration: float) -> int:
        # Mirrors Moris BurstController._pattern_rank.
        if self.kind is BurstPatternKind.LAST:
            assert self.last_seconds is not None
            return -1 if duration - now < self.last_seconds else 1
        if self.kind is BurstPatternKind.EVERY:
            assert self.every is not None
            due = self.every > 0 and cycle % self.every == 0
        else:
            due = cycle in self.cycles
        return 0 if due else 2


@dataclass(frozen=True, slots=True)
class BurstPolicy:
    duration: float = 180.0
    first_burst_time: float = 3.0
    reaction: float = 0.05
    switch_delay: float = 0.1
    reenter_delay: float = 0.5
    full_burst_entry_delay: float = 0.05
    full_burst_base_duration: float = 10.0
    max_burst_count: int | None = None
    no_burst_actors: frozenset[int] = frozenset()
    patterns: Mapping[int, BurstPattern] = field(default_factory=dict)
    sequence: tuple[Mapping[str, tuple[int, ...]], ...] | None = None

    def __post_init__(self) -> None:
        if self.duration <= 0:
            raise ValueError("duration must be > 0")
        if min(self.first_burst_time, self.reaction, self.switch_delay,
               self.reenter_delay, self.full_burst_entry_delay) < 0:
            raise ValueError("burst timings must be >= 0")
        if self.full_burst_base_duration <= 0:
            raise ValueError("full burst duration must be > 0")


@dataclass(frozen=True, slots=True)
class BurstSignal:
    """One Fast trigger notification caused by burst progression.

    `owner_actor` is the effect owner whose TriggerIndex bucket should receive
    the event. `source_actor` is the actual burst caster where meaningful.
    """

    time: float
    event_key: str
    owner_actor: int
    source_actor: int | None = None
    stage: str | None = None
    # Count-event fast-forward: weapon/runtime producers may collapse several
    # identical base events and deliver only the next meaningful boundary.
    # Burst signals keep the default one-event increment.
    count_increment: int = 1

    def __post_init__(self) -> None:
        if self.count_increment <= 0:
            raise ValueError("count_increment must be > 0")


@dataclass(frozen=True, slots=True)
class BurstActionToken:
    generation: int
    stage: str | None = None


def _compile_pattern(raw: Any) -> BurstPattern:
    if isinstance(raw, str) and raw.startswith("every:"):
        n = int(raw.split(":", 1)[1])
        if n <= 0:
            raise ValueError(f"invalid burst every pattern: {raw!r}")
        return BurstPattern(BurstPatternKind.EVERY, every=n)
    if isinstance(raw, str) and raw.startswith("last:"):
        seconds = float(raw.split(":", 1)[1])
        if seconds <= 0:
            raise ValueError(f"invalid burst last pattern: {raw!r}")
        return BurstPattern(BurstPatternKind.LAST, last_seconds=seconds)
    if isinstance(raw, (list, tuple, set)):
        return BurstPattern(BurstPatternKind.CYCLES, cycles=frozenset(int(v) for v in raw))
    raise ValueError(f"unsupported burst pattern: {raw!r}")


def compile_burst_policy(
    moris_squad: list[dict],
    compiled: CompiledSquad,
    config: dict | None = None,
) -> BurstPolicy:
    """Lower Moris runner burst configuration from names to actor indexes."""

    cfg = build_config(moris_squad, config)
    actor_by_name = {name: i for i, name in enumerate(compiled.names)}

    no_burst_names = set(cfg.get("no_burst_chars") or ())
    if cfg.get("no_burst_char"):
        no_burst_names.add(str(cfg["no_burst_char"]))
    no_burst = frozenset(actor_by_name[name] for name in no_burst_names if name in actor_by_name)

    patterns: dict[int, BurstPattern] = {}
    for name, raw in (cfg.get("burst_pattern") or {}).items():
        if name in actor_by_name:
            patterns[actor_by_name[name]] = _compile_pattern(raw)

    raw_sequence = cfg.get("burst_sequence")
    sequence = None
    if raw_sequence is not None:
        out = []
        for cycle in raw_sequence:
            stages: dict[str, tuple[int, ...]] = {}
            for stage in ("1", "2", "3"):
                stages[stage] = tuple(
                    actor_by_name[name]
                    for name in cycle.get(stage, ())
                    if name in actor_by_name
                )
            out.append(stages)
        sequence = tuple(out)

    return BurstPolicy(
        duration=float(cfg.get("duration", 180.0)),
        first_burst_time=float(cfg.get("first_burst_time", 3.0)),
        reaction=float(cfg.get("burst_reaction", 0.05)),
        switch_delay=float(cfg.get("burst_switch_delay", 0.1)),
        reenter_delay=float(cfg.get("burst_reenter_delay", 0.5)),
        max_burst_count=cfg.get("max_burst_count"),
        no_burst_actors=no_burst,
        patterns=patterns,
        sequence=sequence,
    )


class BurstMachine:
    """Character-name-blind continuous-time burst state machine.

    This is infrastructure, not yet a claim of full Moris burst parity. Dynamic
    burst-cooldown buffs, full-burst-duration buffs and reenter/stage-override
    skill dispatch will connect through the generic effect runtime later. The
    state machine already exposes mutation APIs and uses generation tokens so
    stale scheduled waits can be ignored cheaply.
    """

    __slots__ = (
        "squad", "policy", "phase", "cycle_count", "ready_at", "gauge_ready_at",
        "stage_override", "reenter_stage", "casted", "full_burst_end_at",
        "full_burst_caster", "cd_applied_at_cast", "_generation", "_waiting_candidates", "_waiting_stage",
    )

    def __init__(self, squad: CompiledSquad, policy: BurstPolicy) -> None:
        self.squad = squad
        self.policy = policy
        self.phase = "idle"
        self.cycle_count = 0
        self.ready_at = [0.0] * len(squad.members)
        self.gauge_ready_at = [policy.first_burst_time] * len(squad.members)
        self.stage_override: dict[int, str] = {}
        self.reenter_stage: dict[int, str] = {}
        self.casted = [False] * len(squad.members)
        self.full_burst_end_at = -1.0
        self.full_burst_caster: int | None = None
        self.cd_applied_at_cast = [0.0] * len(squad.members)
        self._generation = 0
        self._waiting_candidates: tuple[int, ...] = ()
        self._waiting_stage: str | None = None

    def start(self, scheduler: EventScheduler) -> None:
        self._schedule(scheduler, max(self.gauge_ready_at), EventKind.BURST_READY)

    def _schedule(
        self,
        scheduler: EventScheduler,
        time: float,
        kind: EventKind,
        *,
        stage: str | None = None,
    ) -> None:
        self._generation += 1
        scheduler.schedule(time, kind, payload=BurstActionToken(self._generation, stage))

    def _is_current(self, event: ScheduledEvent) -> bool:
        token = event.payload
        return isinstance(token, BurstActionToken) and token.generation == self._generation

    def stage_for(self, actor: int) -> str:
        if not 0 <= actor < len(self.squad.members):
            raise IndexError(f"actor out of range: {actor}")
        return self.stage_override.get(actor, self.squad.members[actor].burst_stage)

    def set_stage_override(self, actor: int, stage: str | None) -> None:
        if stage is None:
            self.stage_override.pop(actor, None)
            return
        if stage not in {"1", "2", "3", "A"}:
            raise ValueError(f"invalid burst stage override: {stage!r}")
        self.stage_override[actor] = stage

    def set_reenter_stage(self, actor: int, stage: str | None) -> None:
        if stage is None:
            self.reenter_stage.pop(actor, None)
            return
        if stage not in {"1", "2", "3"}:
            raise ValueError(f"invalid reenter stage: {stage!r}")
        self.reenter_stage[actor] = stage

    def adjust_cooldown(self, actor: int, reduction: float, now: float, scheduler: EventScheduler) -> None:
        """Apply an instant cooldown reduction in seconds; negative values extend CD."""
        if abs(reduction) <= _EPS:
            return
        self.ready_at[actor] = max(now, self.ready_at[actor] - float(reduction))
        if actor in self._waiting_candidates and self._waiting_stage is not None:
            earliest = min(self.ready_at[a] for a in self._waiting_candidates)
            self._schedule(scheduler, max(now, earliest), EventKind.BURST_ACTIVATE,
                           stage=self._waiting_stage)

    def reduce_cooldown(self, actor: int, seconds: float, now: float, scheduler: EventScheduler) -> None:
        if seconds > 0:
            self.adjust_cooldown(actor, seconds, now, scheduler)

    def reconcile_persistent_cooldown(
        self, actor: int, current_reduction: float, now: float, scheduler: EventScheduler
    ) -> None:
        """Mirror Moris full-burst-start catch-up for persistent burst CD buffs."""
        if self.ready_at[actor] <= now + _EPS:
            self.cd_applied_at_cast[actor] = 0.0
            return
        extra = max(0.0, float(current_reduction) - self.cd_applied_at_cast[actor])
        if extra > 0.0:
            self.reduce_cooldown(actor, extra, now, scheduler)
        self.cd_applied_at_cast[actor] = 0.0

    def _stage_candidates(self, stage: str, now: float) -> tuple[int, ...]:
        if self.policy.sequence is not None and self.cycle_count < len(self.policy.sequence):
            return tuple(self.policy.sequence[self.cycle_count].get(stage, ()))

        candidates = []
        for actor, member in enumerate(self.squad.members):
            if actor in self.policy.no_burst_actors:
                continue
            current = self.stage_override.get(actor, member.burst_stage)
            if current == "A" or current == stage:
                candidates.append(actor)
        if self.policy.patterns:
            cycle = self.cycle_count + 1
            candidates.sort(key=lambda actor: self.policy.patterns.get(actor).rank(cycle, now, self.policy.duration)
                            if actor in self.policy.patterns else 1)
        return tuple(candidates)

    def _broadcast(self, now: float, event_key: str, source: int | None = None,
                   stage: str | None = None) -> list[BurstSignal]:
        return [BurstSignal(now, event_key, owner, source, stage)
                for owner in range(len(self.squad.members))]

    def _cast_signals(self, actor: int, stage: str, now: float) -> list[BurstSignal]:
        signals = [
            BurstSignal(now, "burst_cast", actor, actor, stage),
            BurstSignal(now, f"squad_burst_cast:{stage}", actor, actor, stage),
        ]
        signals.extend(self._broadcast(now, "event:ally_burst_cast", actor, stage))
        return signals

    def _attempt_stage(
        self,
        stage: str,
        now: float,
        scheduler: EventScheduler,
        *,
        reenter: bool = False,
        cooldown_buff_provider=None,
    ) -> list[BurstSignal]:
        candidates = self._stage_candidates(stage, now)
        self._waiting_candidates = ()
        self._waiting_stage = None
        if not candidates:
            self.phase = f"stage:{stage}"
            return []

        actor = next((a for a in candidates if now >= self.ready_at[a] - _EPS), None)
        if actor is None:
            earliest = min(self.ready_at[a] for a in candidates)
            self._waiting_candidates = candidates
            self._waiting_stage = stage
            self.phase = f"reenter:{stage}" if reenter else f"stage:{stage}"
            self._schedule(
                scheduler, max(now, earliest),
                EventKind.BURST_REENTER if reenter else EventKind.BURST_ACTIVATE,
                stage=stage,
            )
            return []

        self.casted[actor] = True
        cd_buff = max(0.0, float(cooldown_buff_provider(actor, now))) if cooldown_buff_provider else 0.0
        self.cd_applied_at_cast[actor] = cd_buff
        self.ready_at[actor] = now + max(0.0, self.squad.members[actor].burst_cooldown - cd_buff)
        if stage == "3":
            self.full_burst_caster = actor
        signals = self._cast_signals(actor, stage, now)

        r_stage = self.reenter_stage.get(actor)
        if r_stage is not None:
            self.phase = f"reenter:{r_stage}"
            self._schedule(scheduler, now + self.policy.reenter_delay, EventKind.BURST_REENTER,
                           stage=r_stage)
            return signals

        if stage == "3":
            self.phase = "switching"
            self._schedule(scheduler, now + self.policy.full_burst_entry_delay,
                           EventKind.FULL_BURST_START)
        else:
            next_stage = str(int(stage) + 1)
            self.phase = f"stage:{next_stage}"
            signals.extend(self._broadcast(now, f"burst_enter:{next_stage}", actor, next_stage))
            self._schedule(
                scheduler,
                now + self.policy.switch_delay + self.policy.reaction,
                EventKind.BURST_ACTIVATE,
                stage=next_stage,
            )
        return signals

    def handle(
        self,
        event: ScheduledEvent,
        scheduler: EventScheduler,
        *,
        full_burst_extension: float = 0.0,
        cooldown_buff_provider=None,
    ) -> tuple[BurstSignal, ...]:
        # Full-burst-end effects must see the cast flags from the cycle that just
        # ended. Reset them on a same-time follow-up boundary after those signals
        # have been dispatched, but before later weapon-phase events at that time.
        if event.kind is EventKind.BURST_END_FINALIZE:
            self.casted = [False] * len(self.casted)
            return ()

        if not self._is_current(event):
            return ()
        now = event.time

        if event.kind is EventKind.BURST_READY:
            if self.policy.max_burst_count is not None and self.cycle_count >= self.policy.max_burst_count:
                return ()
            self.phase = "stage:1"
            signals = self._broadcast(now, "burst_enter:1", None, "1")
            self._schedule(scheduler, now + self.policy.reaction, EventKind.BURST_ACTIVATE, stage="1")
            return tuple(signals)

        token = event.payload
        stage = token.stage if isinstance(token, BurstActionToken) else None
        if event.kind is EventKind.BURST_ACTIVATE:
            if stage not in {"1", "2", "3"}:
                raise ValueError(f"missing burst stage in activation: {stage!r}")
            return tuple(self._attempt_stage(stage, now, scheduler, reenter=False, cooldown_buff_provider=cooldown_buff_provider))

        if event.kind is EventKind.BURST_REENTER:
            if stage not in {"1", "2", "3"}:
                raise ValueError(f"missing burst stage in reenter: {stage!r}")
            signals = self._broadcast(now, f"burst_enter:{stage}", None, stage)
            signals.extend(self._attempt_stage(stage, now, scheduler, reenter=True, cooldown_buff_provider=cooldown_buff_provider))
            return tuple(signals)

        if event.kind is EventKind.FULL_BURST_START:
            self.phase = "full_burst"
            duration = max(1.0, self.policy.full_burst_base_duration + full_burst_extension)
            self.full_burst_end_at = now + duration
            signals = self._broadcast(now, "full_burst_start", self.full_burst_caster, "3")
            self._schedule(scheduler, self.full_burst_end_at, EventKind.FULL_BURST_END)
            return tuple(signals)

        if event.kind is EventKind.FULL_BURST_END:
            self.phase = "idle"
            signals = self._broadcast(now, "full_burst_end", self.full_burst_caster, "3")
            scheduler.schedule(now, EventKind.BURST_END_FINALIZE)
            self.cycle_count += 1
            self.full_burst_caster = None
            self.gauge_ready_at = [
                now + max(0.0, member.burst_regen_time) for member in self.squad.members
            ]
            if self.policy.max_burst_count is None or self.cycle_count < self.policy.max_burst_count:
                self._schedule(scheduler, max(self.gauge_ready_at), EventKind.BURST_READY)
            return tuple(signals)

        raise ValueError(f"BurstMachine cannot handle event kind {event.kind}")
