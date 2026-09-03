from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import TYPE_CHECKING, Iterable

from .scheduler import EventKind, EventScheduler, ScheduledEvent
from .shot_blocks import next_static_shot_after
from .state import ENEMY, StateDomain, StateStore

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
        return self.expires_at == inf or now < self.expires_at


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

    ``duration_bullets`` normally uses one precomputed post-shot expiry at the
    recipient's Nth static shot. Selected dynamic rapid actors instead register
    themselves here and own a live remaining-bullet counter. That keeps the
    existing zero-overhead static path unchanged while letting cover/reload
    cadence move the actual consuming shot without stale expiry timestamps.
    """

    __slots__ = (
        "squad", "state", "_effects", "_active", "_by_target_stat",
        "_by_target_name", "_generation", "_dynamic_bullet_targets",
        "_bullet_remaining",
    )

    def __init__(self, squad: "CompiledSquad", state: StateStore) -> None:
        self.squad = squad
        self.state = state
        self._effects = tuple(squad.effects)
        self._active: dict[ActiveKey, ActiveEffect] = {}
        self._by_target_stat: dict[tuple[int, str], set[ActiveKey]] = {}
        self._by_target_name: dict[tuple[int, str], set[ActiveKey]] = {}
        self._generation = 0
        self._dynamic_bullet_targets: frozenset[int] = frozenset()
        self._bullet_remaining: dict[ActiveKey, int] = {}

    def enable_dynamic_bullet_lifetime_targets(self, actors: Iterable[int]) -> None:
        """Register actors whose physical shots consume bullet lifetimes live."""

        selected = frozenset(int(actor) for actor in actors)
        if any(actor < 0 or actor >= len(self.squad.members) for actor in selected):
            raise IndexError("dynamic bullet-lifetime actor out of range")
        # Registration is additive: charge and rapid score runtimes may
        # both own recipient-shot lifetimes in the same squad.
        self._dynamic_bullet_targets = self._dynamic_bullet_targets | selected

    def dynamic_bullet_lifetime_supported(self, target: int) -> bool:
        return int(target) in self._dynamic_bullet_targets

    def dynamic_bullet_signature(self, target: int, *, now: float) -> tuple[tuple[int, int, int], ...]:
        """Return a cheap generation/remaining signature for weapon replanning."""

        rows: list[tuple[int, int, int]] = []
        for key, remaining in self._bullet_remaining.items():
            if key[1] != target:
                continue
            active = self._active.get(key)
            if active is None or not active.active(now):
                continue
            rows.append((active.effect_id, active.generation, int(remaining)))
        return tuple(sorted(rows))

    def has_dynamic_bullet_lifetime(self, target: int, *, now: float) -> bool:
        return bool(self.dynamic_bullet_signature(target, now=now))

    def consume_dynamic_bullet(
        self,
        target: int,
        *,
        now: float,
        count: int = 1,
    ) -> tuple[int, ...]:
        """Consume recipient-shot lifetimes after the shot's post-hit signals.

        Moris decrements every active bullet-lifetime buff once per recipient
        shot. The consuming shot still sees the buff; removal happens only after
        damage and hit/on-attack notifications. BurstRuntime calls this at that
        exact post-shot point for dynamic rapid actors.
        """

        if count <= 0 or target not in self._dynamic_bullet_targets:
            return ()
        removed: list[int] = []
        changed = False
        for key in tuple(self._bullet_remaining):
            if key[1] != target:
                continue
            active = self._active.get(key)
            if active is None or not active.active(now):
                self._bullet_remaining.pop(key, None)
                continue
            remaining = self._bullet_remaining[key] - int(count)
            changed = True
            if remaining > 0:
                self._bullet_remaining[key] = remaining
                continue
            self._bullet_remaining.pop(key, None)
            effect = self._effects[active.effect_id]
            self._active.pop(key, None)
            self._index_remove(effect, key)
            removed.append(active.effect_id)
        if changed:
            self.state.touch(target, StateDomain.EFFECT)
        return tuple(removed)

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
            if target in self._dynamic_bullet_targets:
                # Reactivation gets a new generation and resets the remaining
                # lifetime just like Moris' bullet-duration refresh semantics.
                self._bullet_remaining[key] = int(bullets)
            else:
                # Moris decrements once per recipient shot and removes the state
                # only after the consuming shot has been damaged. Locate the Nth
                # static shot without scheduling per-shot events; one post-shot
                # expiry is enough. Reactivation gets a new generation,
                # invalidating the old expiry and resetting the lifetime.
                self._bullet_remaining.pop(key, None)
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
        else:
            self._bullet_remaining.pop(key, None)
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
        self._bullet_remaining.pop(key, None)
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

    def active_effect_of_type(self, target: int, effect_type: str, *, now: float):
        """Return the newest live effect of ``effect_type`` on one target."""
        rows = []
        for active in self._active.values():
            if active.target != int(target) or not active.active(now):
                continue
            effect = self._effects[active.effect_id]
            if effect.effect_type == effect_type:
                rows.append((effect, active))
        if not rows:
            return None
        return max(rows, key=lambda row: row[1].generation)

    def named_stack(self, target: int, name: str, *, now: float) -> float:
        return max(
            (
                self._active[key].stacks
                for key in self._active_keys(self._by_target_name, target, name, now)
            ),
            default=0.0,
        )

    def source_named_stack(self, source_actor: int, name: str, *, now: float) -> float:
        """Moris self_stack_above: same-caster named state on self or enemy."""
        values = []
        for active in self._active.values():
            if (
                active.source_actor != int(source_actor)
                or active.target not in {int(source_actor), ENEMY}
                or not active.active(now)
            ):
                continue
            effect = self._effects[active.effect_id]
            if effect.name == name:
                values.append(active.stacks)
        return max(values, default=0.0)

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
            self._bullet_remaining.pop(key, None)
            effect = self._effects[active.effect_id]
            self._index_remove(effect, key)
            removed.append(active.effect_id)
        if removed:
            self.state.touch(target, StateDomain.EFFECT)
        return tuple(removed)

    def group_active(
        self,
        effect_id: int,
        targets: Iterable[int],
        *,
        now: float,
    ) -> bool:
        """Return whether this exact Moris target cohort is already active."""

        cohort = self._cohort(targets)
        if not cohort:
            return False
        return any(
            (active := self._active.get((int(effect_id), target, cohort))) is not None
            and active.active(now)
            for target in cohort
        )


    def deactivate_group(
        self,
        effect_id: int,
        targets: Iterable[int],
        *,
        now: float,
    ) -> tuple[int, ...]:
        """Remove one exact activation cohort without synthesizing expiry events."""

        cohort = self._cohort(targets)
        if not cohort:
            return ()
        removed: list[int] = []
        for target in cohort:
            key: ActiveKey = (int(effect_id), target, cohort)
            active = self._active.pop(key, None)
            if active is None:
                continue
            self._bullet_remaining.pop(key, None)
            effect = self._effects[active.effect_id]
            self._index_remove(effect, key)
            self.state.touch(target, StateDomain.EFFECT)
            removed.append(target)
        return tuple(removed)

    def extend_named_states(
        self,
        targets: Iterable[int],
        name: str,
        delta: float,
        *,
        now: float,
        scheduler: EventScheduler,
    ) -> tuple[int, ...]:
        """Extend finite active ``name``/``name N`` states by one sparse boundary."""

        selected = frozenset(int(target) for target in targets)
        amount = float(delta)
        if not selected or not name or amount <= 0.0:
            return ()
        prefix = name + " "
        changed: list[int] = []
        touched: set[int] = set()
        for active in tuple(self._active.values()):
            if active.target not in selected or not active.active(now):
                continue
            effect = self._effects[active.effect_id]
            effect_name = effect.name or ""
            if effect_name != name and not effect_name.startswith(prefix):
                continue
            if active.expires_at == inf:
                continue
            if effect.parameters.get("duration_bullets") is not None:
                raise NotImplementedError(
                    "Fast named duration extension over bullet lifetime not certified"
                )
            active.expires_at += amount
            active.generation = self._next_generation()
            scheduler.schedule(
                active.expires_at,
                EventKind.STATE_EXPIRE,
                actor=active.target,
                payload=EffectExpiryToken(
                    active.effect_id,
                    active.target,
                    active.cohort,
                    active.generation,
                ),
            )
            changed.append(active.effect_id)
            touched.add(active.target)
        for target in touched:
            self.state.touch(target, StateDomain.EFFECT)
        return tuple(changed)

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
