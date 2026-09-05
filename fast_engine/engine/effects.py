from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Callable, TYPE_CHECKING, Iterable

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
    scaling_stack: float | None = None

    def active(self, now: float) -> bool:
        return self.expires_at == inf or now < self.expires_at


@dataclass(frozen=True, slots=True)
class EffectExpiryToken:
    effect_id: int
    target: int
    cohort: tuple[int, ...]
    generation: int
    post_shot: bool = False


@dataclass(slots=True)
class PendingTargetEffect:
    """One Moris-style lazy target buff waiting for its first stat read."""

    effect_id: int
    source_actor: int
    activated_at: float
    expires_at: float
    stacks: float
    scheduler: EventScheduler


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
        "_bullet_remaining", "_pending_target", "_lazy_target_resolver",
        "_resolving_lazy_target", "_finite_reference_stack_effect_ids",
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
        self._pending_target: dict[int, PendingTargetEffect] = {}
        self._lazy_target_resolver: Callable[["CompiledEffect", float, float], tuple[int, ...]] | None = None
        self._resolving_lazy_target = False
        self._finite_reference_stack_effect_ids: frozenset[int] = frozenset()

    def enable_finite_reference_stack_capture(self, effect_ids: Iterable[int]) -> None:
        """Enable only squad-proven finite named-stack reference consumers."""

        self._finite_reference_stack_effect_ids = frozenset(int(eid) for eid in effect_ids)

    def _reference_named_stack_optional(
        self, source_actor: int, name: str, *, now: float
    ) -> float | None:
        if not self.has_named_state(int(source_actor), name, now=now):
            return None
        return self.named_stack(int(source_actor), name, now=now)

    def _capture_reference_stack(self, effect: "CompiledEffect", now: float) -> float | None:
        if effect.effect_id not in self._finite_reference_stack_effect_ids:
            return None
        ref = effect.parameters.get("scaling_ref")
        if not isinstance(ref, str) or not ref:
            return None
        return self._reference_named_stack_optional(effect.actor, ref, now=now)

    def effect_value_scale(
        self, effect: "CompiledEffect", active: ActiveEffect, *, now: float
    ) -> float:
        """Return Moris' own-stack or captured reference-stack multiplier."""

        if effect.effect_id not in self._finite_reference_stack_effect_ids:
            return active.stacks
        if active.scaling_stack is not None:
            return active.scaling_stack
        # Moris leaves scaling_stack=None when the reference is absent at the
        # activation boundary, then falls back to a live ref_count lookup.
        ref = effect.parameters.get("scaling_ref")
        if not isinstance(ref, str) or not ref:
            return 0.0
        live = self._reference_named_stack_optional(active.source_actor, ref, now=now)
        return 0.0 if live is None else live

    def _touch_live_reference_consumers(
        self, source_actor: int, name: str, *, now: float
    ) -> None:
        """Invalidate only finite refs whose activation captured no provider."""

        if not name:
            return
        for active in tuple(self._active.values()):
            if (
                active.effect_id not in self._finite_reference_stack_effect_ids
                or active.source_actor != int(source_actor)
                or active.scaling_stack is not None
                or not active.active(now)
            ):
                continue
            effect = self._effects[active.effect_id]
            if effect.parameters.get("scaling_ref") == name:
                self.state.touch(active.target, StateDomain.EFFECT)

    def attach_lazy_target_resolver(
        self,
        resolver: Callable[["CompiledEffect", float, float], tuple[int, ...]],
    ) -> None:
        """Attach the rank resolver after TargetResolver is constructed."""

        self._lazy_target_resolver = resolver

    def defer_target_group(
        self,
        effect: "CompiledEffect",
        now: float,
        scheduler: EventScheduler,
    ) -> None:
        """Register one unresolved target cohort without guessing its recipient.

        Moris keeps lazy rank buffs active with target_chars=None.  A refresh of
        an already-resolved buff keeps that cohort; a refresh before first read
        merely moves the unresolved activation timestamp.  Pending activation
        invalidates ally EFFECT caches conservatively because the future cohort
        is not known yet.
        """

        max_stack = effect.max_stack if effect.max_stack is not None else 1.0
        if float(max_stack) != 1.0:
            raise NotImplementedError(
                "Fast lazy rank target currently requires max_stack=1"
            )

        live = tuple(
            active
            for active in self._active.values()
            if active.effect_id == effect.effect_id and active.active(now)
        )
        if live:
            cohort = max(live, key=lambda active: active.generation).cohort
            for target in cohort:
                self._activate_one(effect, target, cohort, now, scheduler)
            return

        duration = effect.duration
        expires = inf if duration is None or duration == -1 else now + max(0.0, duration)
        self._pending_target[effect.effect_id] = PendingTargetEffect(
            effect.effect_id,
            effect.actor,
            float(now),
            float(expires),
            1.0,
            scheduler,
        )
        # DamageTermResolver caches by concrete actor EFFECT versions.  Until the
        # lazy cohort is known every ally is a possible recipient, so invalidate
        # those snapshots without materializing a target.
        for actor in range(len(self.squad.members)):
            self.state.touch(actor, StateDomain.EFFECT)

    def _materialize_pending_stat(self, stat: str, now: float) -> None:
        """Resolve pending buffs of ``stat`` on their first observable read."""

        if self._resolving_lazy_target or self._lazy_target_resolver is None:
            return
        for effect_id, pending in tuple(self._pending_target.items()):
            effect = self._effects[effect_id]
            if (effect.stat or "") != stat:
                continue
            if pending.expires_at != inf and now >= pending.expires_at:
                self._pending_target.pop(effect_id, None)
                continue

            self._resolving_lazy_target = True
            try:
                targets = self._lazy_target_resolver(
                    effect, pending.activated_at, float(now)
                )
            finally:
                self._resolving_lazy_target = False

            self._pending_target.pop(effect_id, None)
            cohort = self._cohort(targets)
            if not cohort:
                continue
            # Lifetimes start at activation, not at first read.  This slice does
            # not defer duration_bullets, so scheduling from activated_at cannot
            # create a missed post-shot expiry.
            for target in cohort:
                self._activate_one(
                    effect,
                    target,
                    cohort,
                    pending.activated_at,
                    pending.scheduler,
                )

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
            self._capture_reference_stack(effect, now),
        )
        self._active[key] = active
        if old is None:
            self._index_add(effect, key)
        self.state.touch(target, StateDomain.EFFECT)
        if effect.name:
            self._touch_live_reference_consumers(effect.actor, effect.name, now=now)
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
        if effect.name:
            self._touch_live_reference_consumers(active.source_actor, effect.name, now=event.time)
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
            self._touch_live_reference_consumers(active.source_actor, name, now=now)
            changed.append(active.effect_id)
        return tuple(changed)

    def decrement_harmful_stackable(
        self,
        targets: Iterable[int],
        amount: float,
        *,
        now: float,
    ) -> tuple[int, ...]:
        """Mirror Moris' generic debuff_stack_remove over active ally states.

        The generic path only touches harmful buffs whose declared max_stack is
        greater than one, and unlike a named removal it cannot reduce a live
        stack below one. Runtime certification in TriggerDispatcher keeps this
        primitive inside a squad-proven single-provider slice.
        """

        selected = frozenset(int(target) for target in targets)
        delta = max(0.0, float(amount))
        if not selected or delta <= 0.0:
            return ()
        changed: list[int] = []
        touched: set[int] = set()
        for active in tuple(self._active.values()):
            if active.target not in selected or not active.active(now):
                continue
            effect = self._effects[active.effect_id]
            max_stack = effect.max_stack
            if (
                not str(effect.polarity or "").startswith("harmful")
                or max_stack is None
                or float(max_stack) <= 1.0
                or active.stacks <= 1.0 + _EPS
            ):
                continue
            stacks = max(1.0, active.stacks - delta)
            if abs(stacks - active.stacks) <= _EPS:
                continue
            active.stacks = stacks
            touched.add(active.target)
            if effect.name:
                self._touch_live_reference_consumers(
                    active.source_actor, effect.name, now=now
                )
            changed.append(active.effect_id)
        for target in touched:
            self.state.touch(target, StateDomain.EFFECT)
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
            self._touch_live_reference_consumers(active.source_actor, name, now=now)
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
            if effect.name:
                self._touch_live_reference_consumers(active.source_actor, effect.name, now=now)
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
        self._materialize_pending_stat(stat, now)
        return bool(self._active_keys(self._by_target_stat, target, stat, now))

    def sum_stat(self, target: int, stat: str, *, now: float) -> float:
        self._materialize_pending_stat(stat, now)
        total = 0.0
        for key in self._active_keys(self._by_target_stat, target, stat, now):
            active = self._active[key]
            effect = self._effects[active.effect_id]
            total += float(effect.value or 0.0) * self.effect_value_scale(effect, active, now=now)
        return total

    def effective_atk(self, actor: int, *, now: float) -> float:
        """Return current ATK without forcing unresolved rank buffs to resolve.

        Moris _effective_atk sees lazy ActiveBuff rows with target_chars=None and
        therefore excludes them while choosing that very cohort.
        """

        previous = self._resolving_lazy_target
        self._resolving_lazy_target = True
        try:
            base = float(self.squad.members[actor].base_atk)
            atk_pct = self.sum_stat(actor, "atk_pct", now=now)
            atk_flat = self.sum_stat(actor, "atk_flat", now=now)
            for key in self._active_keys(
                self._by_target_stat, actor, "atk_caster_based_pct", now
            ):
                active = self._active[key]
                effect = self._effects[active.effect_id]
                caster_base = float(self.squad.members[active.source_actor].base_atk)
                scale = self.effect_value_scale(effect, active, now=now)
                atk_flat += caster_base * float(effect.value or 0.0) * scale / 100.0
            return base * (1.0 + atk_pct / 100.0) + atk_flat
        finally:
            self._resolving_lazy_target = previous

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
        self._materialize_pending_stat(stat, now)
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
