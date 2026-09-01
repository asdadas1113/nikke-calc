from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import CompiledEffect, CompiledSquad


def possible_ally_targets(
    squad: "CompiledSquad",
    effect: "CompiledEffect",
) -> tuple[int, ...]:
    """Return a conservative set of allies that an effect may target.

    Selectors determined only by immutable squad metadata are narrowed exactly.
    Rank/history/state selectors can change during combat, so they widen to all
    allies. Callers may therefore use this set for fail-closed certification
    without assuming a dynamic selector stays on its initial recipient.
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
