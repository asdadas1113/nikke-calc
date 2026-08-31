from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .ir import CharacterIR, EffectIR


@dataclass(frozen=True)
class FastSupportProfile:
    """Capabilities currently implemented by the Fast runtime.

    A/B are intended to be generic baseline operations. C effects are accepted
    only when their subsystem has been implemented and tested. D is never
    silently approximated: any D effect routes the whole team to Moris.
    N matches a Moris-side NOP/unimplemented effect and therefore never blocks.
    """

    support_a: bool = True
    support_b: bool = True
    c_subsystems: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def structural_full_generic(cls, catalog: Iterable[CharacterIR]) -> 'FastSupportProfile':
        subsystems = {
            effect.subsystem
            for char in catalog
            for effect in char.effects
            if effect.readiness == 'C'
        }
        return cls(c_subsystems=frozenset(subsystems))


@dataclass(frozen=True)
class EffectBlocker:
    character: str
    effect_name: str
    stat: str | None
    readiness: str
    subsystem: str
    reason: str


@dataclass(frozen=True)
class RouteDecision:
    engine: str  # "fast" | "moris"
    blockers: tuple[EffectBlocker, ...] = ()

    @property
    def fast_exact(self) -> bool:
        return self.engine == 'fast'


def _blocker_for(effect: EffectIR, reason: str) -> EffectBlocker:
    return EffectBlocker(
        character=effect.character,
        effect_name=effect.name,
        stat=effect.stat,
        readiness=effect.readiness,
        subsystem=effect.subsystem,
        reason=reason,
    )


def route_team(
    team: Iterable[str],
    catalog_by_name: Mapping[str, CharacterIR],
    profile: FastSupportProfile,
) -> RouteDecision:
    blockers: list[EffectBlocker] = []
    for name in team:
        char = catalog_by_name.get(name)
        if char is None:
            blockers.append(EffectBlocker(name, '<catalog>', None, 'D', 'catalog', 'unknown_character'))
            continue
        for effect in char.effects:
            if effect.readiness == 'N':
                continue
            if effect.readiness == 'D':
                blockers.append(_blocker_for(effect, 'special_fallback'))
            elif effect.readiness == 'C' and effect.subsystem not in profile.c_subsystems:
                blockers.append(_blocker_for(effect, f'unimplemented_subsystem:{effect.subsystem}'))
            elif effect.readiness == 'B' and not profile.support_b:
                blockers.append(_blocker_for(effect, 'generic_B_not_implemented'))
            elif effect.readiness == 'A' and not profile.support_a:
                blockers.append(_blocker_for(effect, 'core_A_not_implemented'))
    return RouteDecision('fast' if not blockers else 'moris', tuple(blockers))
