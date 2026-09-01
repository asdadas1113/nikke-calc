from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import TYPE_CHECKING, Iterable

from .scheduler import EventKind, EventScheduler, ScheduledEvent
from .shot_blocks import next_static_shot_after
from .state import StateDomain, StateStore

if TYPE_CHECKING:
    from .model import CompiledEffect, CompiledSquad

_EPS = 1e-9
ActiveKey = tuple[int, int, tuple[int, ...]]


@dataclass(slots=True)
class ActiveEffect:
    effect_id: int
    target: int
    source_actor: int
    cohort: tuple[int, ...]
    stacks: float
    expires_at: float
    generation: int

    def active(self, now: float) -> bool:
        return self.expires_at == inf or now < self.expires_at - _EPS


@dataclass(frozen=True, slots=True)
class EffectExpiryToken:
    effect_id: int
    target: int
    cohort: tuple[int, ...]
    generation: int
    post_shot: bool = False


class ActiveEffectStore:
    """Compact active-buff/state table preserving Moris target-cohort semantics.

    Moris can keep two activations of the same compiled effect alive at once when
    their resolved target cohorts differ. The active key therefore contains the
    whole activation cohort rather than only (effect_id, target). Damage effects
    that are observable as named DoT states reuse this table as well; ordinary
    score-only damage never enters it.
    """

    __slots__ = (
        "squad", "state", "_effects", "_active", "_by_target_stat",
        "_by_target_name", "_generation",
    )

    def __init__(self, squad: "CompiledSquad", state: StateStore) -> None:
        self.squad = squad
        self.state = state
        self._effects = tuple(squad.effects)
        self._active: dict[ActiveKey, ActiveEffect] = {}
        self._by_target_stat: dict[tuple[int, str], set[ActiveKey]] = {}
        self._by_target_name: dict[tuple[int, str], set[ActiveKey]] = {}
        self._generation = 0

    def _next_generation(self) -> int:
        self._generation += 1
        return self._generation

    @staticmethod
    def _cohort(targets: Iterable[int]) -> tuple[int, ...]:
        return tuple(sorted(set(int(target) for target in targets)))

    def _index_add(self, effect: "CompiledEffect", key: ActiveKey) -> None:
        target = key[1]
        if effect.stat:
            self._by_target_stat.setdefault((target, effect.stat), set()).add(key)
        if effect.name:
            self._by_target_name.setdefault((target, effect.name), set()).add(key)

    def _index_remove(self, effect: "CompiledEffect", key: ActiveKey) -> None:
        target = key[1]
        for table, index_key in (
            (self._by_target_stat, (target, effect.stat or "")),
            (self._by_target_name, (target, effect.name)),
        ):
            keys = table.get(index_key)
            if keys is None:
                continue
            keys.discard(key)
            if not keys:
                table.pop(index_key, None)

    def _activate_one(
        self,
        effect: "CompiledEffect",
        target: int,
        cohort: tuple[int, ...],
        now: float,
        scheduler: EventScheduler,
        *,
        initial_stacks: float | None = None,
        reset_scaled_stack: bool = False,
    ) -> ActiveEffect:
        key: ActiveKey = (effect.effect_id, target, cohort)
        old = self._active.get(key)
        max_stack = effect.max_stack if effect.max_stack is not None else 1.0

        if initial_stacks is None:
            if old is None or max_stack == 1:
                stacks = 1.0
            else:
                stacks = old.stacks + 1.0
            if max_stack is not None and max_stack >= 0:
                stacks = min(stacks, max_stack)
        else:
            initial = max(0.0, float(initial_stacks))
            if old is None:
                stacks = initial
            elif max_stack == 1:
                stacks = old.stacks
            elif reset_scaled_stack:
                stacks = initial
            else:
                stacks = old.stacks + 1.0
                if max_stack is not None and max_stack >= 0:
                    stacks = min(stacks, max_stack)

        duration = effect.duration
        expires = inf if duration is None or duration == -1 else now + max(0.0, duration)
        generation = self._next_generation()
        active = ActiveEffect(
            effect.effect_id,
            target,
            effect.actor,
            cohort,
            stacks,
            expires,
            generation,
        )
        self._active[key] = active
        if old is None:
            self._index_add(effect, key)
        self.state.touch(target, StateDomain.EFFECT)
        if expires != inf:
            scheduler.schedule(
                expires,
                EventKind.STATE_EXPIRE,
                actor=target,
                payload=EffectExpiryToken(effect.effect_id, target, cohort, generation),
            )

        duration_bullets = effect.parameters.get("duration_bullets")
        if duration_bullets is not None:
            bullets = float(duration_bullets)
            if bullets < 1.0 or not bullets.is_integer():
                raise NotImplementedError(
                    f"Fast duration_bullets={duration_bullets!r} not certified"
                )
            if target < 0:
                raise NotImplementedError(
                    "Fast duration_bullets enemy-target lifetime not certified"
                )
            # Moris decrements once per recipient shot and removes the state only
            # after the consuming shot has been damaged. Locate the Nth static
            # shot without scheduling per-shot events; one post-shot expiry is
            # enough. Reactivation gets a new generation, invalidating the old
            # expiry and thereby resetting the lifetime to N shots.
            consume_at = float(now)
            for _ in range(int(bullets)):
                consume_at = next_static_shot_after(self.squad, target, consume_at)
            scheduler.schedule(
                consume_at,
                EventKind.STATE_EXPIRE,
                actor=target,
                payload=EffectExpiryToken(
                    effect.effect_id,
                    target,
                    cohort,
                    generation,
                    post_shot=True,
                ),
            )
        return active

    def activate_group(
        self,
        effect: "CompiledEffect",
        targets: Iterable[int],
        now: float,
        scheduler: EventScheduler,
    ) -> tuple[ActiveEffect, ...]:
        cohort = self._cohort(targets)
        if not cohort:
            return ()
        return tuple(
            self._activate_one(effect, target, cohort, now, scheduler)
            for target in cohort
        )

    def activate_group_scaled(
        self,
        effect: "CompiledEffect",
        targets: Iterable[int],
        now: float,
        scheduler: EventScheduler,
        *,
        initial_stacks: float,
    ) -> tuple[ActiveEffect, ...]:
        """Register a Moris scaling_ref DoT as an observable named state."""
        cohort = self._cohort(targets)
        if not cohort:
            return ()
        return tuple(
            self._activate_one(
                effect,
                target,
                cohort,
                now,
                scheduler,
                initial_stacks=initial_stacks,
                reset_scaled_stack=True,
            )
            for target in cohort
        )

    def activate(
        self,
        effect: "CompiledEffect",
        target: int,
        now: float,
        scheduler: EventScheduler,
    ) -> ActiveEffect:
        return self._activate_one(effect, target, (target,), now, scheduler)

    def handle_expiry(self, event: ScheduledEvent) -> "CompiledEffect | None":
        token = event.payload
        if not isinstance(token, EffectExpiryToken):
            return None
        key: ActiveKey = (token.effect_id, token.target, token.cohort)
        active = self._active.get(key)
        if active is None or active.generation != token.generation:
            return None
        if not token.post_shot:
            if active.expires_at == inf or event.time < active.expires_at - _EPS:
                return None
        effect = self._effects[token.effect_id]
        del self._active[key]
        self._index_remove(effect, key)
        self.state.touch(token.target, StateDomain.EFFECT)
        return effect

    def _active_keys(
        self,
        table: dict[tuple[int, str], set[ActiveKey]],
        target: int,
        key: str,
        now: float,
    ) -> tuple[ActiveKey, ...]:
        out = []
        for active_key in tuple(table.get((target, key), ())):
            active = self._active.get(active_key)
            if active is not None and active.active(now):
                out.append(active_key)
        return tuple(out)

    def has_named_state(self, target: int, name: str, *, now: float) -> bool:
        return bool(self._active_keys(self._by_target_name, target, name, now))

    def named_stack(self, target: int, name: str, *, now: float) -> float:
        return max(
            (
                self._active[key].stacks
                for key in self._active_keys(self._by_target_name, target, name, now)
            ),
            default=0.0,
        )

    def adjust_named_stack(
        self,
        target: int,
        name: str,
        delta: float,
        *,
        now: float,
    ) -> tuple[int, ...]:
        changed: list[int] = []
        for key in self._active_keys(self._by_target_name, target, name, now):
            active = self._active[key]
            effect = self._effects[active.effect_id]
            max_stack = effect.max_stack if effect.max_stack is not None else 1.0
            cap = active.stacks + delta if max_stack == -1 else max_stack
            stacks = max(0.0, min(active.stacks + float(delta), cap))
            if abs(stacks - active.stacks) <= _EPS:
                continue
            active.stacks = stacks
            self.state.touch(target, StateDomain.EFFECT)
            changed.append(active.effect_id)
        return tuple(changed)

    def remove_named_state(
        self,
        target: int,
        name: str,
        *,
        now: float,
    ) -> tuple[int, ...]:
        removed: list[int] = []
        for key in self._active_keys(self._by_target_name, target, name, now):
            active = self._active.pop(key, None)
            if active is None:
                continue
            effect = self._effects[active.effect_id]
            self._index_remove(effect, key)
            removed.append(active.effect_id)
        if removed:
            self.state.touch(target, StateDomain.EFFECT)
        return tuple(removed)

    def has_stat(self, target: int, stat: str, *, now: float) -> bool:
        return bool(self._active_keys(self._by_target_stat, target, stat, now))

    def sum_stat(self, target: int, stat: str, *, now: float) -> float:
        total = 0.0
        for key in self._active_keys(self._by_target_stat, target, stat, now):
            active = self._active[key]
            effect = self._effects[active.effect_id]
            total += float(effect.value or 0.0) * active.stacks
        return total

    def effective_atk(self, actor: int, *, now: float) -> float:
        base = float(self.squad.members[actor].base_atk)
        atk_pct = self.sum_stat(actor, "atk_pct", now=now)
        atk_flat = self.sum_stat(actor, "atk_flat", now=now)
        for key in self._active_keys(
            self._by_target_stat, actor, "atk_caster_based_pct", now
        ):
            active = self._active[key]
            effect = self._effects[active.effect_id]
            caster_base = float(self.squad.members[active.source_actor].base_atk)
            atk_flat += caster_base * float(effect.value or 0.0) * active.stacks / 100.0
        return base * (1.0 + atk_pct / 100.0) + atk_flat

    def iter_stat_prefix(self, prefix: str, *, now: float):
        seen: set[ActiveKey] = set()
        for (target, stat), keys in tuple(self._by_target_stat.items()):
            if not stat.startswith(prefix):
                continue
            for key in tuple(keys):
                if key in seen:
                    continue
                active = self._active.get(key)
                if active is not None and active.active(now):
                    seen.add(key)
                    yield self._effects[active.effect_id], active

    def iter_stat(self, stat: str, *, now: float):
        seen: set[ActiveKey] = set()
        for (target, key_stat), keys in tuple(self._by_target_stat.items()):
            if key_stat != stat:
                continue
            for key in tuple(keys):
                if key in seen:
                    continue
                active = self._active.get(key)
                if active is not None and active.active(now):
                    seen.add(key)
                    yield self._effects[active.effect_id], active