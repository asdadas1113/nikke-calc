from __future__ import annotations

from typing import Any

from calculator.buff_manager import BuffManager, _get_skill_lv


def registered_effects(squad: list[dict]) -> tuple[tuple[dict[str, Any], str], ...]:
    """Return the exact effect sources Moris registers for this built squad.

    This is an intentionally narrow compile-time bridge to a private Moris list.
    It includes active skill variants plus equipment, overload/equip_skills,
    cube, collection and manual-stat effects.  Fast never calls BuffManager in
    its combat runtime.

    Keeping the private dependency in one adapter makes drift visible and easy
    to replace if Moris later exposes a public effect-expansion function.
    """

    manager = BuffManager(squad, state={})
    return tuple((effect, caster) for effect, caster in manager._effects)


def effect_skill_level(char: dict, effect: dict[str, Any]) -> str:
    return _get_skill_lv(char, effect)
