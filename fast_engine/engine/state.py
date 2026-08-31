from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from math import inf
from typing import Iterable

from .model import ActorRuntimeState, CompiledSquad

ENEMY = -1
_EPS = 1e-12


class StateDomain(IntEnum):
    """Independent invalidation lanes for hot-path caches."""

    EFFECT = 0          # named states, stacks, gauges, counters
    HEALTH = 1          # HP / shield dependent conditions and derived values
    RESOURCE = 2        # ammo / weapon mode / cadence-facing resources
    DAMAGE_MEMORY = 3   # last dealt damage / delayed-damage accumulators
    BURST = 4           # reserved for burst-stage/full-burst state


@dataclass(slots=True)
class ActiveState:
    """Compact runtime record for a named buff/debuff/marker state.

    `effect_id` points back to compiled IR; the hot runtime does not duplicate
    the full parsed effect dict in every active state instance.
    """

    effect_id: int
    source_actor: int
    stacks: float = 1.0
    max_stacks: float | None = None
    expires_at: float | None = None
    generation: int = 1

    def is_active(self, now: float) -> bool:
        return self.expires_at is None or now < self.expires_at - _EPS


class StateStore:
    """Mutable score-oriented runtime state with domain-scoped versions.

    A mutation increments only the domain it can invalidate. For example,
    recording `last_dealt_damage` must not invalidate a cached buff snapshot
    that depends only on named effects and HP.
    """

    __slots__ = (
        "actors", "enemy_states", "_version", "_domain_versions",
        "_actor_versions", "_enemy_versions", "_generation",
    )

    def __init__(
        self,
        actor_count: int,
        *,
        initial_hp: Iterable[float] | None = None,
        initial_ammo: Iterable[float] | None = None,
    ) -> None:
        if actor_count <= 0:
            raise ValueError("actor_count must be > 0")
        hp = list(initial_hp) if initial_hp is not None else [0.0] * actor_count
        ammo = list(initial_ammo) if initial_ammo is not None else [0.0] * actor_count
        if len(hp) != actor_count or len(ammo) != actor_count:
            raise ValueError("initial_hp/initial_ammo must match actor_count")
        self.actors = [
            ActorRuntimeState(hp=float(hp[i]), ammo=float(ammo[i]))
            for i in range(actor_count)
        ]
        self.enemy_states: dict[str, ActiveState] = {}
        self._version = 0
        self._domain_versions = [0] * len(StateDomain)
        self._actor_versions = [[0] * len(StateDomain) for _ in range(actor_count)]
        self._enemy_versions = [0] * len(StateDomain)
        self._generation = 0

    @classmethod
    def from_compiled_squad(cls, squad: CompiledSquad) -> "StateStore":
        return cls(
            len(squad.members),
            initial_hp=(m.base_hp for m in squad.members),
            initial_ammo=(float(m.weapon.get("max_ammo", 0.0) or 0.0) for m in squad.members),
        )

    @property
    def version(self) -> int:
        return self._version

    def domain_version(self, domain: StateDomain) -> int:
        return self._domain_versions[int(domain)]

    def entity_version(self, entity: int, domain: StateDomain) -> int:
        if entity == ENEMY:
            return self._enemy_versions[int(domain)]
        self._check_actor(entity)
        return self._actor_versions[entity][int(domain)]

    def dependency_token(
        self,
        *,
        entities: Iterable[int] | None = None,
        domains: Iterable[StateDomain] = (StateDomain.EFFECT,),
    ) -> tuple[int, ...]:
        """Return a stable cache key for exactly the declared dependencies."""

        doms = tuple(domains)
        if entities is None:
            return tuple(self._domain_versions[int(d)] for d in doms)
        ents = tuple(entities)
        return tuple(self.entity_version(e, d) for e in ents for d in doms)

    def _check_actor(self, actor: int) -> None:
        if not 0 <= actor < len(self.actors):
            raise IndexError(f"actor out of range: {actor}")

    def touch(self, entity: int, domain: StateDomain) -> None:
        """Public invalidation hook for compact runtime subsystems."""
        self._touch(entity, domain)

    def _touch(self, entity: int, domain: StateDomain) -> None:
        self._version += 1
        idx = int(domain)
        self._domain_versions[idx] += 1
        if entity == ENEMY:
            self._enemy_versions[idx] += 1
        else:
            self._check_actor(entity)
            self._actor_versions[entity][idx] += 1

    def _next_generation(self) -> int:
        self._generation += 1
        return self._generation

    def _states(self, entity: int) -> dict[str, ActiveState]:
        if entity == ENEMY:
            return self.enemy_states
        self._check_actor(entity)
        return self.actors[entity].states

    # ── named states / stacks ──────────────────────────────────────────────
    def get_state(self, entity: int, name: str, *, now: float | None = None) -> ActiveState | None:
        state = self._states(entity).get(name)
        if state is None:
            return None
        if now is not None and not state.is_active(now):
            return None
        return state

    def has_state(self, entity: int, name: str, *, now: float | None = None) -> bool:
        return self.get_state(entity, name, now=now) is not None

    def set_state(
        self,
        entity: int,
        name: str,
        *,
        effect_id: int,
        source_actor: int,
        stacks: float = 1.0,
        max_stacks: float | None = None,
        expires_at: float | None = None,
    ) -> int:
        if not name:
            raise ValueError("state name must not be empty")
        if stacks < 0:
            raise ValueError("state stacks must be >= 0")
        if max_stacks is not None:
            if max_stacks < 0:
                raise ValueError("max_stacks must be >= 0")
            stacks = min(stacks, max_stacks)
        if expires_at is not None and expires_at < 0:
            raise ValueError("expires_at must be >= 0")
        bucket = self._states(entity)
        old = bucket.get(name)
        desired = (effect_id, source_actor, float(stacks), max_stacks, expires_at)
        if old is not None and (
            old.effect_id, old.source_actor, old.stacks, old.max_stacks, old.expires_at
        ) == desired:
            return old.generation
        generation = self._next_generation()
        bucket[name] = ActiveState(
            effect_id=effect_id,
            source_actor=source_actor,
            stacks=float(stacks),
            max_stacks=max_stacks,
            expires_at=expires_at,
            generation=generation,
        )
        self._touch(entity, StateDomain.EFFECT)
        return generation

    def remove_state(self, entity: int, name: str) -> bool:
        bucket = self._states(entity)
        if name not in bucket:
            return False
        del bucket[name]
        self._touch(entity, StateDomain.EFFECT)
        return True

    def expire_state(self, entity: int, name: str, generation: int, *, now: float) -> bool:
        """Expire only the exact generation scheduled earlier.

        Refreshing a state produces a new generation, making its old scheduled
        expiry event harmless without needing heap deletion.
        """

        state = self._states(entity).get(name)
        if state is None or state.generation != generation:
            return False
        if state.expires_at is None or now < state.expires_at - _EPS:
            return False
        return self.remove_state(entity, name)

    def set_stack(self, entity: int, name: str, stacks: float) -> float:
        state = self._states(entity).get(name)
        if state is None:
            raise KeyError(f"state not active: {name}")
        if stacks < 0:
            stacks = 0.0
        if state.max_stacks is not None:
            stacks = min(stacks, state.max_stacks)
        stacks = float(stacks)
        if abs(state.stacks - stacks) <= _EPS:
            return state.stacks
        state.stacks = stacks
        state.generation = self._next_generation()
        self._touch(entity, StateDomain.EFFECT)
        return state.stacks

    def add_stack(self, entity: int, name: str, delta: float) -> float:
        state = self._states(entity).get(name)
        if state is None:
            raise KeyError(f"state not active: {name}")
        return self.set_stack(entity, name, state.stacks + delta)

    # ── numeric effect state ───────────────────────────────────────────────
    def _set_mapping_value(self, actor: int, mapping: dict[str, float], key: str, value: float) -> float:
        self._check_actor(actor)
        value = float(value)
        old = float(mapping.get(key, 0.0))
        if abs(old - value) <= _EPS:
            return old
        mapping[key] = value
        self._touch(actor, StateDomain.EFFECT)
        return value

    def set_gauge(self, actor: int, key: str, value: float, *, minimum: float = 0.0, maximum: float = inf) -> float:
        value = min(max(float(value), minimum), maximum)
        return self._set_mapping_value(actor, self.actors[actor].gauges, key, value)

    def add_gauge(self, actor: int, key: str, delta: float, *, minimum: float = 0.0, maximum: float = inf) -> float:
        self._check_actor(actor)
        return self.set_gauge(actor, key, self.actors[actor].gauges.get(key, 0.0) + delta, minimum=minimum, maximum=maximum)

    def set_counter(self, actor: int, key: str, value: float) -> float:
        return self._set_mapping_value(actor, self.actors[actor].counters, key, value)

    def add_counter(self, actor: int, key: str, delta: float) -> float:
        self._check_actor(actor)
        return self.set_counter(actor, key, self.actors[actor].counters.get(key, 0.0) + delta)

    # ── HP / shield ────────────────────────────────────────────────────────
    def set_hp(self, actor: int, value: float, *, max_hp: float | None = None) -> float:
        self._check_actor(actor)
        value = max(float(value), 0.0)
        if max_hp is not None:
            value = min(value, max_hp)
        state = self.actors[actor]
        if abs(state.hp - value) <= _EPS:
            return state.hp
        state.hp = value
        self._touch(actor, StateDomain.HEALTH)
        return value

    def add_hp(self, actor: int, delta: float, *, max_hp: float | None = None) -> float:
        self._check_actor(actor)
        return self.set_hp(actor, self.actors[actor].hp + delta, max_hp=max_hp)

    def set_shield(self, actor: int, value: float) -> float:
        self._check_actor(actor)
        value = max(float(value), 0.0)
        state = self.actors[actor]
        if abs(state.shield - value) <= _EPS:
            return state.shield
        state.shield = value
        self._touch(actor, StateDomain.HEALTH)
        return value

    # ── ammo / weapon mode ─────────────────────────────────────────────────
    def set_ammo(self, actor: int, value: float) -> float:
        self._check_actor(actor)
        value = max(float(value), 0.0)
        state = self.actors[actor]
        if abs(state.ammo - value) <= _EPS:
            return state.ammo
        state.ammo = value
        self._touch(actor, StateDomain.RESOURCE)
        return value

    def add_ammo(self, actor: int, delta: float, *, maximum: float = inf) -> float:
        self._check_actor(actor)
        return self.set_ammo(actor, min(self.actors[actor].ammo + delta, maximum))

    def set_weapon_mode(self, actor: int, mode: str | None) -> str | None:
        self._check_actor(actor)
        state = self.actors[actor]
        if state.weapon_mode == mode:
            return mode
        state.weapon_mode = mode
        self._touch(actor, StateDomain.RESOURCE)
        return mode

    # ── damage memory ──────────────────────────────────────────────────────
    def record_damage(self, actor: int, damage: float) -> float:
        self._check_actor(actor)
        damage = float(damage)
        state = self.actors[actor]
        if abs(state.last_dealt_damage - damage) <= _EPS:
            return state.last_dealt_damage
        state.last_dealt_damage = damage
        self._touch(actor, StateDomain.DAMAGE_MEMORY)
        return damage

    def set_damage_accumulator(self, actor: int, key: str, value: float) -> float:
        self._check_actor(actor)
        value = float(value)
        mapping = self.actors[actor].damage_accumulators
        old = float(mapping.get(key, 0.0))
        if abs(old - value) <= _EPS:
            return old
        mapping[key] = value
        self._touch(actor, StateDomain.DAMAGE_MEMORY)
        return value

    def add_damage_accumulator(self, actor: int, key: str, delta: float) -> float:
        self._check_actor(actor)
        return self.set_damage_accumulator(
            actor, key, self.actors[actor].damage_accumulators.get(key, 0.0) + delta
        )
