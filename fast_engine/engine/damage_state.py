from __future__ import annotations

from .conditions import ConditionMode
from .damage import DamageTerms
from .damage_policy import is_static_element_override_score_supported
from .effects import ActiveEffectStore
from .model import CompiledSquad, EnemyStaticProfile
from .state import ENEMY, StateDomain, StateStore

_CODE_ADVANTAGE = {
    "전격": "수냉",
    "수냉": "작열",
    "작열": "풍압",
    "풍압": "철갑",
    "철갑": "전격",
}


class DamageTermResolver:
    """Resolve active Fast effects into one cacheable numeric damage snapshot.

    The hot path depends only on the scored actor's EFFECT lane and the enemy's
    EFFECT lane. Unrelated ally mutations therefore do not invalidate this
    actor's snapshot. Health/resource-derived stats are intentionally not folded
    in yet; adding one requires explicitly widening this dependency token.
    """

    __slots__ = (
        "squad",
        "effects",
        "state",
        "enemy",
        "_cache",
        "_static_element_override_codes",
    )

    def __init__(
        self,
        squad: CompiledSquad,
        effects: ActiveEffectStore,
        state: StateStore,
        enemy: EnemyStaticProfile,
    ) -> None:
        self.squad = squad
        self.effects = effects
        self.state = state
        self.enemy = enemy
        self._cache: dict[int, tuple[tuple[int, ...], DamageTerms]] = {}

        # Moris keeps element_code_override separate from the roster code and
        # simply ORs it into the element-advantage predicate while active. Only
        # immutable battle-start/self/irremovable variants are folded here, so
        # this table never needs a runtime dependency token.
        override_codes: list[set[str]] = [set() for _ in squad.members]
        for effect in squad.effects:
            if is_static_element_override_score_supported(effect):
                override_codes[effect.actor].add(
                    str(effect.parameters["target_code"])
                )
        self._static_element_override_codes = tuple(
            frozenset(codes) for codes in override_codes
        )

    def _token(self, actor: int) -> tuple[int, ...]:
        effect_token = self.state.dependency_token(
            entities=(actor, ENEMY),
            domains=(StateDomain.EFFECT,),
        )
        # A shield-conditioned buff may be sourced by another ally, so
        # HEALTH invalidation is squad-global for this sparse state change.
        return effect_token + (self.state.domain_version(StateDomain.HEALTH),)

    def _runtime_condition_ok(self, effect) -> bool:
        for rule in effect.condition_rules:
            if (
                rule.mode is ConditionMode.DURING_SHIELD
                and self.state.actors[effect.actor].shield <= 0.0
            ):
                return False
        return True

    def _sum(self, actor: int, stat: str, now: float) -> float:
        total = 0.0
        for effect, active in self.effects.iter_stat(stat, now=now):
            if active.target != actor or not self._runtime_condition_ok(effect):
                continue
            total += float(effect.value or 0.0) * active.stacks
        return total

    def _has(self, actor: int, stat: str, now: float) -> bool:
        return any(
            active.target == actor and self._runtime_condition_ok(effect)
            for effect, active in self.effects.iter_stat(stat, now=now)
        )

    def _sum_aliases(self, actor: int, stats: tuple[str, ...], now: float) -> float:
        return sum(self._sum(actor, stat, now) for stat in stats)

    def _caster_based_atk_flat(self, actor: int, now: float) -> float:
        total = 0.0
        for effect, active in self.effects.iter_stat("atk_caster_based_pct", now=now):
            if active.target != actor or not self._runtime_condition_ok(effect):
                continue
            caster_base = self.squad.members[active.source_actor].base_atk
            total += caster_base * float(effect.value or 0.0) * active.stacks / 100.0
        return total

    def resolve(self, actor: int, *, now: float) -> DamageTerms:
        token = self._token(actor)
        cached = self._cache.get(actor)
        if cached is not None and cached[0] == token:
            return cached[1]

        general_crit_rate_pct = self._sum(actor, "crit_rate", now)
        normal_crit_rate_pct = self._sum(actor, "normal_atk_crit_rate", now)
        general_crit_dmg = self._sum(actor, "crit_dmg", now)
        normal_crit_dmg = self._sum(actor, "normal_atk_crit_dmg", now)

        # Moris routing rules:
        # - enemy-target def_pct becomes enemy_def_down_pct in the DealForm.
        # - personal_* manual/character effects stay on the scored actor itself.
        enemy_def_down = self._sum_aliases(
            ENEMY, ("def_pct", "enemy_def_down_pct"), now
        ) + self._sum(actor, "personal_enemy_def_down_pct", now)
        received = self._sum(ENEMY, "received_dmg_pct", now) + self._sum(
            actor, "personal_received_dmg_pct", now
        )

        element = self.squad.members[actor].element
        base_element_match = (
            bool(element)
            and bool(self.enemy.element)
            and _CODE_ADVANTAGE.get(str(element)) == self.enemy.element
        )
        override_element_match = (
            bool(self.enemy.element)
            and str(self.enemy.element) in self._static_element_override_codes[actor]
        )
        terms = DamageTerms(
            atk_pct=self._sum(actor, "atk_pct", now),
            atk_flat=(
                self._sum(actor, "atk_flat", now)
                + self._caster_based_atk_flat(actor, now)
            ),
            enemy_def_down_pct=enemy_def_down,
            def_ignore_pct=self._sum(actor, "def_ignore_pct", now),
            crit_rate=min(
                1.0,
                0.15 + (general_crit_rate_pct + normal_crit_rate_pct) / 100.0,
            ),
            crit_dmg=general_crit_dmg + normal_crit_dmg,
            crit_rate_skill=min(1.0, 0.15 + general_crit_rate_pct / 100.0),
            crit_dmg_skill=general_crit_dmg,
            core_dmg_pct=self._sum(actor, "core_dmg_pct", now),
            accuracy_pct=self._sum(actor, "accuracy_pct", now),
            normal_atk_dmg_pct=self._sum(actor, "normal_atk_dmg_pct", now),
            atk_dmg_pct=self._sum(actor, "atk_dmg_pct", now),
            burst_dmg_pct=self._sum(actor, "burst_dmg_pct", now),
            burst_dmg_aoe_pct=self._sum(actor, "burst_dmg_aoe_pct", now),
            pierce_dmg_pct=self._sum(actor, "pierce_dmg_pct", now),
            armor_break_dmg_pct=self._sum(actor, "armor_break_dmg_pct", now),
            pierce_enabled=self._has(actor, "pierce_enabled", now),
            armor_break_enabled=self._has(actor, "armor_break_enabled", now),
            dot_dmg_pct=self._sum(actor, "dot_dmg_pct", now),
            projectile_explosion_dmg_pct=self._sum_aliases(
                actor,
                ("projectile_explosion_dmg", "projectile_explosion_dmg_pct"),
                now,
            ),
            projectile_attachment_dmg_pct=self._sum_aliases(
                actor,
                ("projectile_attachment_dmg", "projectile_attachment_dmg_pct"),
                now,
            ),
            sequential_dmg_pct=self._sum(actor, "sequential_dmg_pct", now),
            part_dmg_pct=self._sum_aliases(
                actor, ("part_dmg", "part_dmg_pct"), now
            ),
            charge_dmg_pct=self._sum(actor, "charge_dmg_pct", now),
            charge_dmg_mag_pct=self._sum(actor, "charge_dmg_mag_pct", now),
            received_dmg_pct=received,
            split_dmg_pct=self._sum(actor, "split_dmg_pct", now),
            element_bonus_pct=self._sum_aliases(
                actor, ("element_bonus", "element_bonus_pct"), now
            ),
            element_match=base_element_match or override_element_match,
        )
        self._cache[actor] = (token, terms)
        return terms
