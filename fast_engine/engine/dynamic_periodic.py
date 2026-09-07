from __future__ import annotations

from dataclasses import dataclass

from .frame_lattice import moris_next_tick, moris_observed_tick
from .scheduler import EventKind, EventScheduler
from .triggers import TriggerMode

_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class DynamicPeriodicTickToken:
    effect_id: int
    rule_index: int
    generation: int


@dataclass(frozen=True, slots=True)
class DynamicPeriodicSyncToken:
    time: float


@dataclass(slots=True)
class _DynamicPeriodicState:
    effect_id: int
    rule_index: int
    actor: int
    effect_name: str
    base_interval: float
    interval: float
    next_nominal: float
    generation: int = 0


class DynamicPeriodicCadenceRuntime:
    """Sparse Moris-style every:Ns cadence with targeted interval modifiers.

    Moris rescales the *remaining* cooldown whenever the effective interval
    changes. Fast keeps one raw next-fire timestamp per affected periodic and
    only maps that boundary onto the repeated-add 60 Hz lattice. Old scheduled
    reservations are invalidated by generation rather than cancelled, so no
    global frame stream is introduced.
    """

    __slots__ = (
        'squad', 'effects', 'scheduler', 'horizon', '_states', '_owned', '_pending_sync',
        '_modifier_actors',
    )

    def __init__(
        self,
        squad,
        effects,
        scheduler: EventScheduler,
        *,
        horizon: float,
        modifier_filter,
        effect_filter,
    ) -> None:
        self.squad = squad
        self.effects = effects
        self.scheduler = scheduler
        self.horizon = float(horizon)
        self._states: dict[tuple[int, int], _DynamicPeriodicState] = {}

        target_keys: set[tuple[int, str]] = set()
        for modifier in squad.effects:
            if not modifier_filter(modifier):
                continue
            if (modifier.stat or '') != 'effect_interval':
                continue
            target_name = modifier.parameters.get('target_effect')
            if not isinstance(target_name, str) or not target_name:
                continue
            target_keys.add((modifier.actor, target_name))

        for actor, target_name in target_keys:
            candidates = [
                effect for effect in squad.effects
                if effect.actor == actor
                and effect.name == target_name
                and effect_filter(effect)
            ]
            if len(candidates) != 1:
                continue
            effect = candidates[0]
            periodic_rules = [
                (index, rule)
                for index, rule in enumerate(effect.triggers)
                if rule.mode is TriggerMode.PERIODIC
                and rule.interval is not None
                and float(rule.interval) > 0.0
            ]
            if len(periodic_rules) != 1:
                continue
            rule_index, rule = periodic_rules[0]
            base = float(rule.interval)
            key = (effect.effect_id, rule_index)
            self._states[key] = _DynamicPeriodicState(
                effect.effect_id,
                rule_index,
                actor,
                effect.name,
                base,
                base,
                base,
            )

        self._owned = frozenset(self._states)
        self._modifier_actors = frozenset(
            state.actor for state in self._states.values()
        )
        self._pending_sync: set[float] = set()

    @property
    def owned(self) -> frozenset[tuple[int, int]]:
        return self._owned

    def owns(self, effect_id: int, rule_index: int) -> bool:
        return (int(effect_id), int(rule_index)) in self._owned

    def _effective_interval(self, state: _DynamicPeriodicState, now: float) -> float:
        flat = self.effects.sum_targeted_stat(
            state.actor,
            'effect_interval',
            state.effect_name,
            now=now,
        )
        interval = max(0.0, state.base_interval + flat)
        return max(interval, state.base_interval * 0.05)

    def _reserve(self, state: _DynamicPeriodicState) -> None:
        if state.next_nominal >= self.horizon:
            return
        observed = moris_observed_tick(state.next_nominal, horizon=self.horizon)
        # If a phase-later event changed cadence after BuffManager's periodic
        # phase at the same Moris frame, the newly-due periodic cannot run
        # retroactively. Moris sees it on the next outer-loop tick.
        if observed <= self.scheduler.now + _EPS:
            observed = moris_next_tick(self.scheduler.now, horizon=self.horizon)
        if observed >= self.horizon:
            return
        self.scheduler.schedule(
            observed,
            EventKind.PERIODIC_TICK,
            actor=state.actor,
            payload=DynamicPeriodicTickToken(
                state.effect_id,
                state.rule_index,
                state.generation,
            ),
        )

    def start(self) -> None:
        for state in self._states.values():
            state.interval = self._effective_interval(state, 0.0)
            state.next_nominal = state.interval
            self._reserve(state)

    def defer_burst_cast_sync(self, actor: int | None, now: float) -> None:
        """Observe an owned actor's burst-cast modifier on the next Moris frame."""
        if actor is None or int(actor) not in self._modifier_actors:
            return
        when = moris_next_tick(float(now), horizon=self.horizon)
        if when >= self.horizon or when in self._pending_sync:
            return
        self._pending_sync.add(when)
        self.scheduler.schedule(
            when, EventKind.PERIODIC_SYNC, payload=DynamicPeriodicSyncToken(when)
        )

    def handle_sync(self, token: DynamicPeriodicSyncToken, now: float) -> None:
        self._pending_sync.discard(token.time)
        self.sync(now)

    def sync(self, now: float) -> None:
        """Rescale remaining cooldown after an interval state transition."""
        now = float(now)
        for state in self._states.values():
            new_interval = self._effective_interval(state, now)
            old_interval = state.interval
            if abs(new_interval - old_interval) <= _EPS:
                continue
            remaining = max(0.0, state.next_nominal - now)
            state.next_nominal = now + remaining * (new_interval / old_interval)
            state.interval = new_interval
            state.generation += 1
            self._reserve(state)

    def accepts(self, token: DynamicPeriodicTickToken) -> bool:
        state = self._states.get((token.effect_id, token.rule_index))
        return state is not None and state.generation == token.generation

    def after_tick(self, token: DynamicPeriodicTickToken) -> None:
        state = self._states[(token.effect_id, token.rule_index)]
        state.next_nominal += state.interval
        state.generation += 1
        self._reserve(state)
