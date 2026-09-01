from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

from .state import ENEMY

if TYPE_CHECKING:
    from .burst import BurstMachine
    from .effects import ActiveEffectStore
    from .model import CompiledSquad
    from .state import StateStore


class TargetMode(str, Enum):
    SELF = "self"
    ALL_ALLIES = "all_allies"
    ALL_ALLIES_EXCL_SELF = "all_allies_excl_self"
    NAMED_ACTOR = "named_actor"
    ENEMY = "enemy"
    COMPOSITE = "composite"
    ADJACENT = "adjacent"
    WEAPON = "weapon"
    WEAPON_EXCL_SELF = "weapon_excl_self"
    CHARACTER_CLASS = "character_class"
    ELEMENT = "element"
    ELEMENT_WEAPON = "element_weapon"
    SAME_SQUAD = "same_squad"
    WITH_BUFF = "with_buff"
    WITHOUT_BUFF = "without_buff"
    BURST3 = "burst3"
    BURST_CASTED = "burst_casted"
    BURST_NOT_CASTED = "burst_not_casted"
    BURST_CASTED_B3 = "burst_casted_b3"
    BURST_CASTED_WEAPON = "burst_casted_weapon"
    TOP_ATK = "top_atk"
    TOP_ATK_EXCL_SELF = "top_atk_excl_self"
    LOWEST_ATK_BURST3 = "lowest_atk_burst3"
    LOWEST_HP = "lowest_hp"
    LOWEST_HP_EXCL_SELF = "lowest_hp_excl_self"
    TOP_DEF = "top_def"
    RANDOM = "random"
    MODEL_EXCLUDED = "model_excluded"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class TargetSpec:
    raw: Any
    mode: TargetMode
    arg: str | None = None
    count: int | None = None
    children: tuple["TargetSpec", ...] = ()

    @property
    def runtime_supported(self) -> bool:
        return self.mode not in {TargetMode.MODEL_EXCLUDED, TargetMode.UNSUPPORTED}


def _counted(raw: str, prefix: str) -> int:
    return int(raw[len(prefix):])


def compile_target(raw: Any, *, actor_by_name: dict[str, int]) -> TargetSpec:
    if isinstance(raw, list):
        return TargetSpec(
            raw,
            TargetMode.COMPOSITE,
            children=tuple(compile_target(x, actor_by_name=actor_by_name) for x in raw),
        )
    if raw is None:
        raw = "self"
    if not isinstance(raw, str):
        return TargetSpec(raw, TargetMode.UNSUPPORTED)
    if raw == "self":
        return TargetSpec(raw, TargetMode.SELF)
    if raw in {"all", "squad", "all_allies"}:
        return TargetSpec(raw, TargetMode.ALL_ALLIES)
    if raw == "all_allies_excl_self":
        return TargetSpec(raw, TargetMode.ALL_ALLIES_EXCL_SELF)
    if raw in actor_by_name:
        return TargetSpec(raw, TargetMode.NAMED_ACTOR, count=actor_by_name[raw])
    if raw in {"enemy", "target", "all_enemies", "target_body", "target_and_nearby"} or raw.startswith(
        ("enemy", "enemies", "same_target", "target")
    ):
        return TargetSpec(raw, TargetMode.ENEMY)
    if raw.startswith("allies_adjacent:"):
        return TargetSpec(raw, TargetMode.ADJACENT, count=_counted(raw, "allies_adjacent:"))
    if raw.startswith("allies_weapon_excl_self:"):
        return TargetSpec(raw, TargetMode.WEAPON_EXCL_SELF, arg=raw.split(":", 1)[1])
    if raw.startswith("allies_weapon:"):
        return TargetSpec(raw, TargetMode.WEAPON, arg=raw.split(":", 1)[1])
    if raw.startswith("allies_class:"):
        return TargetSpec(raw, TargetMode.CHARACTER_CLASS, arg=raw.split(":", 1)[1])
    if raw.startswith("allies_code_weapon:"):
        _, code, weapon = raw.split(":", 2)
        return TargetSpec(raw, TargetMode.ELEMENT_WEAPON, arg=f"{code}:{weapon}")
    if raw.startswith("allies_code:"):
        return TargetSpec(raw, TargetMode.ELEMENT, arg=raw.split(":", 1)[1])
    if raw == "allies_same_squad":
        return TargetSpec(raw, TargetMode.SAME_SQUAD)
    if raw.startswith("allies_with_buff:"):
        return TargetSpec(raw, TargetMode.WITH_BUFF, arg=raw.split(":", 1)[1])
    if raw.startswith("allies_without_buff:"):
        return TargetSpec(raw, TargetMode.WITHOUT_BUFF, arg=raw.split(":", 1)[1])

    # Burst-history selectors use the current cycle's BurstMachine.casted lane.
    # Do not collapse them to "all B3"; the target cohort is part of buff identity.
    if raw == "all_allies_burst_casted":
        return TargetSpec(raw, TargetMode.BURST_CASTED)
    if raw == "all_allies_burst_not_casted":
        return TargetSpec(raw, TargetMode.BURST_NOT_CASTED)
    if raw == "allies_burst_casted_burst3":
        return TargetSpec(raw, TargetMode.BURST_CASTED_B3)
    if raw.startswith("allies_burst_casted_weapon:"):
        return TargetSpec(raw, TargetMode.BURST_CASTED_WEAPON, arg=raw.split(":", 1)[1])
    if raw.startswith("allies_burst3"):
        return TargetSpec(raw, TargetMode.BURST3)

    if raw.startswith("allies_lowest_atk_burst3:"):
        return TargetSpec(
            raw,
            TargetMode.LOWEST_ATK_BURST3,
            count=_counted(raw, "allies_lowest_atk_burst3:"),
        )
    if raw.startswith("allies_top_atk_excl:"):
        return TargetSpec(
            raw, TargetMode.TOP_ATK_EXCL_SELF, count=_counted(raw, "allies_top_atk_excl:")
        )
    if raw.startswith("allies_top_atk:"):
        return TargetSpec(raw, TargetMode.TOP_ATK, count=_counted(raw, "allies_top_atk:"))
    if raw.startswith("allies_lowest_hp_excl:"):
        return TargetSpec(
            raw,
            TargetMode.LOWEST_HP_EXCL_SELF,
            count=_counted(raw, "allies_lowest_hp_excl:"),
        )
    if raw.startswith("allies_lowest_hp:"):
        return TargetSpec(raw, TargetMode.LOWEST_HP, count=_counted(raw, "allies_lowest_hp:"))
    if raw.startswith("allies_top_def:"):
        return TargetSpec(raw, TargetMode.TOP_DEF, count=_counted(raw, "allies_top_def:"))
    if raw.startswith("allies_random:"):
        return TargetSpec(raw, TargetMode.RANDOM, count=_counted(raw, "allies_random:"))
    if "cover" in raw or raw == "all_projectiles":
        return TargetSpec(raw, TargetMode.MODEL_EXCLUDED)
    return TargetSpec(raw, TargetMode.UNSUPPORTED)


# Moris resolves these stat/rank targets lazily, then shares one cohort between
# effects from the same caster at the same activation time with the same raw
# target. Fast does not yet defer resolution to end-of-frame, but it must at
# least preserve that cohort identity once the first selection is made.
_SHARED_SELECTION_MODES = frozenset({
    TargetMode.TOP_ATK,
    TargetMode.TOP_ATK_EXCL_SELF,
    TargetMode.LOWEST_ATK_BURST3,
    TargetMode.LOWEST_HP,
    TargetMode.LOWEST_HP_EXCL_SELF,
    TargetMode.TOP_DEF,
})


class TargetResolver:
    __slots__ = ("squad", "state", "effects", "burst", "_selection_cache")

    def __init__(
        self,
        squad: "CompiledSquad",
        state: "StateStore",
        effects: "ActiveEffectStore",
        burst: "BurstMachine",
    ) -> None:
        self.squad = squad
        self.state = state
        self.effects = effects
        self.burst = burst
        self._selection_cache: dict[tuple[int, float, str], tuple[int, ...]] = {}

    def _cache_key(
        self, spec: TargetSpec, *, owner_actor: int, now: float
    ) -> tuple[int, float, str] | None:
        if spec.mode not in _SHARED_SELECTION_MODES or not isinstance(spec.raw, str):
            return None
        return owner_actor, float(now), spec.raw

    def _remember(
        self,
        spec: TargetSpec,
        *,
        owner_actor: int,
        now: float,
        targets: tuple[int, ...],
    ) -> tuple[int, ...]:
        key = self._cache_key(spec, owner_actor=owner_actor, now=now)
        if key is not None:
            self._selection_cache.setdefault(key, targets)
            return self._selection_cache[key]
        return targets

    def resolve(self, spec: TargetSpec, *, owner_actor: int, now: float) -> tuple[int, ...]:
        key = self._cache_key(spec, owner_actor=owner_actor, now=now)
        if key is not None and key in self._selection_cache:
            return self._selection_cache[key]

        n = len(self.squad.members)
        mode = spec.mode
        if mode is TargetMode.SELF:
            return (owner_actor,)
        if mode is TargetMode.ALL_ALLIES:
            return tuple(range(n))
        if mode is TargetMode.ALL_ALLIES_EXCL_SELF:
            return tuple(i for i in range(n) if i != owner_actor)
        if mode is TargetMode.NAMED_ACTOR:
            return () if spec.count is None else (spec.count,)
        if mode is TargetMode.ENEMY:
            return (ENEMY,)
        if mode is TargetMode.COMPOSITE:
            out: list[int] = []
            for child in spec.children:
                for actor in self.resolve(child, owner_actor=owner_actor, now=now):
                    if actor not in out:
                        out.append(actor)
            return tuple(out)
        if mode is TargetMode.ADJACENT:
            k = max(0, spec.count or 0)
            cand = [i for i in range(n) if i != owner_actor]
            cand.sort(key=lambda i: (abs(i - owner_actor), i))
            return tuple(cand[:k])
        if mode in {TargetMode.WEAPON, TargetMode.WEAPON_EXCL_SELF}:
            return tuple(
                i
                for i, member in enumerate(self.squad.members)
                if member.weapon_type == spec.arg
                and (mode is TargetMode.WEAPON or i != owner_actor)
            )
        if mode is TargetMode.CHARACTER_CLASS:
            aliases = {"공격": "화력형", "방어": "방어형", "지원": "지원형"}
            cls = aliases.get(spec.arg or "", spec.arg)
            return tuple(
                i for i, member in enumerate(self.squad.members)
                if member.character_class == cls
            )
        if mode is TargetMode.ELEMENT:
            return tuple(
                i for i, member in enumerate(self.squad.members)
                if member.element == spec.arg
            )
        if mode is TargetMode.ELEMENT_WEAPON:
            code, weapon = (spec.arg or ":").split(":", 1)
            return tuple(
                i for i, member in enumerate(self.squad.members)
                if member.element == code and member.weapon_type == weapon
            )
        if mode is TargetMode.SAME_SQUAD:
            group = self.squad.members[owner_actor].squad_group
            return tuple(
                i for i, member in enumerate(self.squad.members)
                if group and member.squad_group == group
            )
        if mode is TargetMode.WITH_BUFF:
            return tuple(
                i for i in range(n)
                if self.effects.has_named_state(i, spec.arg or "", now=now)
            )
        if mode is TargetMode.WITHOUT_BUFF:
            return tuple(
                i for i in range(n)
                if not self.effects.has_named_state(i, spec.arg or "", now=now)
            )
        if mode is TargetMode.BURST3:
            return tuple(i for i in range(n) if self.burst.stage_for(i) == "3")
        if mode is TargetMode.BURST_CASTED:
            return tuple(i for i in range(n) if self.burst.casted[i])
        if mode is TargetMode.BURST_NOT_CASTED:
            return tuple(i for i in range(n) if not self.burst.casted[i])
        if mode is TargetMode.BURST_CASTED_B3:
            caster = self.burst.full_burst_caster
            return () if caster is None else (caster,)
        if mode is TargetMode.BURST_CASTED_WEAPON:
            return tuple(
                i for i in range(n)
                if self.burst.casted[i] and self.squad.members[i].weapon_type == spec.arg
            )
        if mode in {TargetMode.TOP_ATK, TargetMode.TOP_ATK_EXCL_SELF}:
            cand = [
                i for i in range(n)
                if mode is TargetMode.TOP_ATK or i != owner_actor
            ]
            cand.sort(key=lambda i: (-self.effects.effective_atk(i, now=now), i))
            return self._remember(
                spec,
                owner_actor=owner_actor,
                now=now,
                targets=tuple(cand[: max(0, spec.count or 0)]),
            )
        if mode is TargetMode.LOWEST_ATK_BURST3:
            # Moris uses parsed_nikke's base B3 stage here, not live stage
            # overrides, then ranks by current effective ATK ascending.
            cand = [
                i for i, member in enumerate(self.squad.members)
                if member.burst_stage == "3"
            ]
            cand.sort(key=lambda i: (self.effects.effective_atk(i, now=now), i))
            return self._remember(
                spec,
                owner_actor=owner_actor,
                now=now,
                targets=tuple(cand[: max(0, spec.count or 0)]),
            )
        if mode in {TargetMode.LOWEST_HP, TargetMode.LOWEST_HP_EXCL_SELF}:
            cand = [
                i for i in range(n)
                if mode is TargetMode.LOWEST_HP or i != owner_actor
            ]
            cand.sort(
                key=lambda i: (
                    self.state.actors[i].hp / max(self.squad.members[i].base_hp, 1.0),
                    i,
                )
            )
            return self._remember(
                spec,
                owner_actor=owner_actor,
                now=now,
                targets=tuple(cand[: max(0, spec.count or 0)]),
            )
        if mode is TargetMode.TOP_DEF:
            cand = sorted(
                range(n), key=lambda i: (-self.squad.members[i].base_def, i)
            )
            return self._remember(
                spec,
                owner_actor=owner_actor,
                now=now,
                targets=tuple(cand[: max(0, spec.count or 0)]),
            )
        if mode is TargetMode.RANDOM:
            raise NotImplementedError(
                f"expected random target not certified: {spec.raw!r}"
            )
        raise NotImplementedError(f"Fast target not supported: {spec.raw!r}")
