from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import TYPE_CHECKING

from .scheduler import EventKind, EventScheduler, ScheduledEvent
from .state import StateDomain, StateStore

if TYPE_CHECKING:
    from .model import CompiledEffect, CompiledSquad

_EPS = 1e-9


@dataclass(slots=True)
class ActiveEffect:
    effect_id: int
    target: int
    source_actor: int
    stacks: float
    expires_at: float
    generation: int

    def active(self, now: float) -> bool:
        return self.expires_at == inf or now < self.expires_at - _EPS


@dataclass(frozen=True, slots=True)
class EffectExpiryToken:
    effect_id: int
    target: int
    generation: int


class ActiveEffectStore:
    """Compact active-buff table indexed by effect id/target/stat/name."""

    __slots__ = ("squad", "state", "_effects", "_active", "_by_target_stat", "_by_target_name", "_generation")

    def __init__(self, squad: "CompiledSquad", state: StateStore) -> None:
        self.squad = squad
        self.state = state
        self._effects = tuple(squad.effects)
        self._active: dict[tuple[int, int], ActiveEffect] = {}
        self._by_target_stat: dict[tuple[int, str], set[int]] = {}
        self._by_target_name: dict[tuple[int, str], set[int]] = {}
        self._generation = 0

    def _next_generation(self) -> int:
        self._generation += 1
        return self._generation

    def _index_add(self, effect: "CompiledEffect", target: int) -> None:
        if effect.stat:
            self._by_target_stat.setdefault((target, effect.stat), set()).add(effect.effect_id)
        if effect.name:
            self._by_target_name.setdefault((target, effect.name), set()).add(effect.effect_id)

    def _index_remove(self, effect: "CompiledEffect", target: int) -> None:
        for table, key in (
            (self._by_target_stat, (target, effect.stat or "")),
            (self._by_target_name, (target, effect.name)),
        ):
            ids = table.get(key)
            if ids is None:
                continue
            ids.discard(effect.effect_id)
            if not ids:
                table.pop(key, None)

    def activate(self, effect: "CompiledEffect", target: int, now: float, scheduler: EventScheduler) -> ActiveEffect:
        key = (effect.effect_id, target)
        old = self._active.get(key)
        max_stack = effect.max_stack if effect.max_stack is not None else 1.0
        if old is None:
            stacks = 1.0
        elif max_stack == 1:
            stacks = 1.0
        else:
            stacks = old.stacks + 1.0
        if max_stack is not None and max_stack >= 0:
            stacks = min(stacks, max_stack)
        duration = effect.duration
        expires = inf if duration is None or duration == -1 else now + max(0.0, duration)
        generation = self._next_generation()
        active = ActiveEffect(effect.effect_id, target, effect.actor, stacks, expires, generation)
        self._active[key] = active
        if old is None:
            self._index_add(effect, target)
        self.state.touch(target, StateDomain.EFFECT)
        if expires != inf:
            scheduler.schedule(expires, EventKind.STATE_EXPIRE, actor=target,
                               payload=EffectExpiryToken(effect.effect_id, target, generation))
        return active

    def handle_expiry(self, event: ScheduledEvent) -> "CompiledEffect | None":
        token = event.payload
        if not isinstance(token, EffectExpiryToken):
            return None
        key = (token.effect_id, token.target)
        active = self._active.get(key)
        if active is None or active.generation != token.generation:
            return None
        if active.expires_at == inf or event.time < active.expires_at - _EPS:
            return None
        effect = self._effects[token.effect_id]
        del self._active[key]
        self._index_remove(effect, token.target)
        self.state.touch(token.target, StateDomain.EFFECT)
        return effect

    def _active_ids(self, table: dict[tuple[int, str], set[int]], target: int, key: str, now: float) -> tuple[int, ...]:
        out = []
        for eid in table.get((target, key), ()):
            active = self._active.get((eid, target))
            if active is not None and active.active(now):
                out.append(eid)
        return tuple(out)

    def has_named_state(self, target: int, name: str, *, now: float) -> bool:
        return bool(self._active_ids(self._by_target_name, target, name, now))

    def named_stack(self, target: int, name: str, *, now: float) -> float:
        vals = [self._active[(eid, target)].stacks for eid in self._active_ids(self._by_target_name, target, name, now)]
        return max(vals, default=0.0)

    def has_stat(self, target: int, stat: str, *, now: float) -> bool:
        return bool(self._active_ids(self._by_target_stat, target, stat, now))

    def sum_stat(self, target: int, stat: str, *, now: float) -> float:
        total = 0.0
        for eid in self._active_ids(self._by_target_stat, target, stat, now):
            effect = self._effects[eid]
            active = self._active[(eid, target)]
            total += float(effect.value or 0.0) * active.stacks
        return total

    def iter_stat_prefix(self, prefix: str, *, now: float):
        for (target, stat), ids in self._by_target_stat.items():
            if not stat.startswith(prefix):
                continue
            for eid in tuple(ids):
                active = self._active.get((eid, target))
                if active is not None and active.active(now):
                    yield self._effects[eid], active

    def iter_stat(self, stat: str, *, now: float):
        seen: set[tuple[int, int]] = set()
        for (target, key), ids in self._by_target_stat.items():
            if key != stat:
                continue
            for eid in ids:
                active = self._active.get((eid, target))
                if active is None or not active.active(now) or (eid, target) in seen:
                    continue
                seen.add((eid, target))
                yield self._effects[eid], active
