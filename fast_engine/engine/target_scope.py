from __future__ import annotations

from typing import TYPE_CHECKING

from .targets import TargetMode, TargetSpec, adjacent_ally_targets

if TYPE_CHECKING:
    from .model import CompiledEffect, CompiledSquad


_STATIC_ALLY_TARGET_MODES = frozenset({
    TargetMode.SELF,
    TargetMode.ALL_ALLIES,
    TargetMode.ALL_ALLIES_EXCL_SELF,
    TargetMode.NAMED_ACTOR,
    TargetMode.ENEMY,
    TargetMode.ADJACENT,
    TargetMode.WEAPON,
    TargetMode.WEAPON_EXCL_SELF,
    TargetMode.CHARACTER_CLASS,
    TargetMode.ELEMENT,
    TargetMode.ELEMENT_WEAPON,
    TargetMode.SAME_SQUAD,
})


def target_scope_is_static(spec: TargetSpec) -> bool:
    """Whether a target cohort is fixed by immutable squad metadata.

    Buff/state/rank/burst-history selectors are deliberately dynamic. Composite
    selectors are static only when every child is static.
    """

    if spec.mode is TargetMode.COMPOSITE:
        return all(target_scope_is_static(child) for child in spec.children)
    return spec.mode in _STATIC_ALLY_TARGET_MODES


def possible_ally_targets(
    squad: "CompiledSquad",
    effect: "CompiledEffect",
) -> tuple[int, ...]:
    """Return a conservative set of allies that an effect may target.

    Selectors determined only by immutable squad metadata are narrowed exactly.
    Dynamic rank/history/state selectors widen to all allies so callers can use
    this set for compile-time fail-closed checks without assuming a selector
    stays on its initial recipient.
    """

    mode = effect.target_spec.mode.value
    n = len(squad.members)
    if mode == "self":
        return (effect.actor,)
    if mode == "named_actor":
        return () if effect.target_spec.count is None else (effect.target_spec.count,)
    if mode == "enemy":
        return ()
    if mode == "all_allies":
        return tuple(range(n))
    if mode == "all_allies_excl_self":
        return tuple(i for i in range(n) if i != effect.actor)
    if mode == "adjacent":
        return adjacent_ally_targets(n, effect.actor, effect.target_spec.count)
    if mode in {"weapon", "weapon_excl_self"}:
        return tuple(
            i
            for i, member in enumerate(squad.members)
            if member.weapon_type == effect.target_spec.arg
            and (mode == "weapon" or i != effect.actor)
        )
    if mode == "character_class":
        aliases = {"공격": "화력형", "방어": "방어형", "지원": "지원형"}
        cls = aliases.get(effect.target_spec.arg or "", effect.target_spec.arg)
        return tuple(
            i for i, member in enumerate(squad.members) if member.character_class == cls
        )
    if mode == "element":
        return tuple(
            i for i, member in enumerate(squad.members) if member.element == effect.target_spec.arg
        )
    if mode == "element_weapon":
        code, weapon = (effect.target_spec.arg or ":").split(":", 1)
        return tuple(
            i
            for i, member in enumerate(squad.members)
            if member.element == code and member.weapon_type == weapon
        )
    if mode == "same_squad":
        group = squad.members[effect.actor].squad_group
        return tuple(
            i
            for i, member in enumerate(squad.members)
            if group and member.squad_group == group
        )
    if mode in {"model_excluded", "unsupported"}:
        return tuple(range(n))
    return tuple(range(n))
