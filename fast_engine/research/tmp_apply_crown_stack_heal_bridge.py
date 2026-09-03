from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_dispatcher() -> None:
    path = Path("fast_engine/engine/dispatcher.py")
    text = path.read_text(encoding="utf-8")

    anchor = '''    _NAMED_EVENT_EXEMPT = frozenset({\n'''
    block = '''    @staticmethod
    def _parse_stack_reach_event_key(key: str) -> tuple[str, int] | None:
        prefix = "stack_reach:"
        if not key.startswith(prefix):
            return None
        body = key[len(prefix):]
        name, sep, raw = body.rpartition(":")
        if not sep or not name or not raw.isdigit():
            return None
        threshold = int(raw)
        return None if threshold <= 0 else (name, threshold)

    @classmethod
    def _self_stack_reach_marker_shape_supported(cls, effect: "CompiledEffect") -> bool:
        """Materialize only a sparse permanent self stack used as a state counter.

        The underlying stat may remain a Moris-NOP for damage purposes. Fast owns
        only the stack count and its hit-count boundaries, not the ignored stat.
        """
        if not (
            effect.capability.disposition is CapabilityDisposition.MIRROR_MORIS_NOP
            and effect.effect_type == "buff"
            and bool(effect.name)
            and effect.target_spec.mode is TargetMode.SELF
            and effect.duration in (None, -1, -1.0)
            and effect.max_stack is not None
            and float(effect.max_stack) > 1.0
            and float(effect.max_stack).is_integer()
            and not effect.parameters
            and not effect.condition_rules
            and len(effect.triggers) == 1
        ):
            return False
        rule = effect.triggers[0]
        return (
            rule.mode is TriggerMode.MODULO
            and rule.trigger_count_reducible
            and rule.event_key == "hit_count"
            and int(rule.threshold or 0) > 0
        )

    @classmethod
    def _stack_reach_source_shape_supported(
        cls, squad: "CompiledSquad", effect: "CompiledEffect"
    ) -> bool:
        parsed = tuple(
            cls._parse_stack_reach_event_key(rule.event_key or "")
            for rule in effect.triggers
        )
        if not parsed or any(item is None for item in parsed):
            return False
        for item in parsed:
            assert item is not None
            name, threshold = item
            providers = tuple(
                provider
                for provider in squad.members[effect.actor].effects
                if provider.effect_id != effect.effect_id
                and provider.name == name
                and cls._self_stack_reach_marker_shape_supported(provider)
            )
            if len(providers) != 1:
                return False
            marker = providers[0]
            if threshold > int(float(marker.max_stack or 0.0)):
                return False
            # A second stack-mutating path would make sparse hit-count ownership
            # insufficient to know the exact threshold phase.
            if any(
                other.effect_id != marker.effect_id
                and other.parameters.get("target_effect") == name
                and (other.stat or "") in {
                    "buff_stack_add", "buff_stack_remove", "buff_stack_init"
                }
                for other in squad.members[effect.actor].effects
            ):
                return False
        return True

    @classmethod
    def _self_stack_remove_shape_supported(cls, effect: "CompiledEffect") -> bool:
        name = effect.parameters.get("target_effect")
        if not (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and effect.effect_type == "instant"
            and (effect.stat or "") == "remove_named_buff"
            and effect.target_spec.mode is TargetMode.SELF
            and isinstance(name, str)
            and bool(name)
            and set(effect.parameters) == {"target_effect"}
            and not effect.condition_rules
            and bool(effect.triggers)
        ):
            return False
        for rule in effect.triggers:
            parsed = cls._parse_stack_reach_event_key(rule.event_key or "")
            if rule.mode is not TriggerMode.EVENT or parsed is None or parsed[0] != name:
                return False
        return True

    def _self_stack_remove_runtime_supported(self, effect: "CompiledEffect") -> bool:
        return (
            self._self_stack_remove_shape_supported(effect)
            and self._stack_reach_source_shape_supported(self.squad, effect)
        )

    @classmethod
    def _self_stack_heal_shape_supported(cls, effect: "CompiledEffect") -> bool:
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and effect.effect_type == "instant"
            and (effect.stat or "") == "heal_hp_pct"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and float(effect.value) > 0.0
            and not effect.parameters
            and not effect.condition_rules
            and bool(effect.triggers)
            and all(
                rule.mode is TriggerMode.EVENT
                and cls._parse_stack_reach_event_key(rule.event_key or "") is not None
                for rule in effect.triggers
            )
        )

    @classmethod
    def _self_stack_heal_chain_shape_supported(
        cls, squad: "CompiledSquad", effect: "CompiledEffect"
    ) -> bool:
        if not (
            cls._self_stack_heal_shape_supported(effect)
            and cls._stack_reach_source_shape_supported(squad, effect)
        ):
            return False
        # Reaching max stack without a same-edge reset would only fire once.
        # Require the reset as part of the certified recurring provider chain.
        for rule in effect.triggers:
            key = rule.event_key or ""
            parsed = cls._parse_stack_reach_event_key(key)
            if parsed is None:
                return False
            name, _threshold = parsed
            resetters = tuple(
                other
                for other in squad.members[effect.actor].effects
                if other.effect_id != effect.effect_id
                and cls._self_stack_remove_shape_supported(other)
                and other.parameters.get("target_effect") == name
                and any((r.event_key or "") == key for r in other.triggers)
            )
            if not resetters:
                return False
        return True

    def _self_stack_heal_runtime_supported(self, effect: "CompiledEffect") -> bool:
        return self._self_stack_heal_chain_shape_supported(self.squad, effect)

    @classmethod
    def heal_received_dependency_score_safe(
        cls, squad: "CompiledSquad", consumer: "CompiledEffect"
    ) -> bool:
        """Certify heal_received only when every possible provider is owned.

        The first slice intentionally supports only a recurring self stack-heal
        chain. External instant heals and lifesteal remain fail-closed so omitted
        refreshes cannot silently change a comparison-critical buff window.
        """
        owner = consumer.actor
        providers = tuple(
            provider
            for provider in squad.effects
            if provider.effect_id != consumer.effect_id
            and (provider.stat or "") in {"heal_hp_pct", "lifesteal_pct"}
            and owner in possible_ally_targets(squad, provider)
        )
        if not providers:
            return False
        return all(
            (provider.stat or "") == "heal_hp_pct"
            and provider.actor == owner
            and provider.target_spec.mode is TargetMode.SELF
            and cls._self_stack_heal_chain_shape_supported(squad, provider)
            for provider in providers
        )

'''
    text = replace_once(text, anchor, block + anchor, label="stack-heal helper block")

    old = '''        if (\n            TriggerDispatcher._timed_self_named_state_marker_shape_supported(effect)\n'''
    new = '''        if (\n            TriggerDispatcher._self_stack_reach_marker_shape_supported(effect)\n            or TriggerDispatcher._timed_self_named_state_marker_shape_supported(effect)\n'''
    text = replace_once(text, old, new, label="marker executable")

    old = '''        for key in keys:\n            name = key[len("event:"):]\n            providers = tuple(\n'''
    new = '''        for key in keys:\n            if key == "event:heal_received":\n                if not self.heal_received_dependency_score_safe(self.squad, effect):\n                    return False\n                continue\n            name = key[len("event:"):]\n            providers = tuple(\n'''
    text = replace_once(text, old, new, label="heal named-event source")

    old = '''        if self._timed_shield_shape_supported(effect):\n            return True\n        if self.is_executable_effect(effect):\n'''
    new = '''        if self._timed_shield_shape_supported(effect):\n            return True\n        if self._self_stack_remove_runtime_supported(effect):\n            return True\n        if self._self_stack_heal_runtime_supported(effect):\n            return True\n        if self.is_executable_effect(effect):\n'''
    text = replace_once(text, old, new, label="stack-heal runtime executable")

    old = '''            elif stat == "remove_named_buff" and self._enemy_remove_named_state_runtime_supported(effect):\n                name = str(effect.parameters.get("target_effect") or "")\n                if tuple(targets) != (ENEMY,):\n                    return False\n                self.effects.remove_named_state(ENEMY, name, now=now)\n'''
    new = '''            elif stat == "remove_named_buff" and self._self_stack_remove_runtime_supported(effect):\n                name = str(effect.parameters.get("target_effect") or "")\n                if tuple(targets) != (effect.actor,):\n                    return False\n                removed = self.effects.remove_named_state(effect.actor, name, now=now)\n                if removed and name in self._self_stack_dependency_names:\n                    self._sync_self_stack_conditional_passives(now=now)\n                if removed and name in self._self_state_dependency_names:\n                    self._sync_self_state_conditional_passives(now=now)\n            elif stat == "heal_hp_pct" and self._self_stack_heal_runtime_supported(effect):\n                if tuple(targets) != (effect.actor,):\n                    return False\n                # Patternless Fast does not mutate HP here. Moris still emits\n                # heal_received at full HP, so recipient-event delivery is exact.\n                from .burst import BurstSignal\n                self.dispatch(\n                    BurstSignal(now, "event:heal_received", effect.actor, effect.actor)\n                )\n            elif stat == "remove_named_buff" and self._enemy_remove_named_state_runtime_supported(effect):\n                name = str(effect.parameters.get("target_effect") or "")\n                if tuple(targets) != (ENEMY,):\n                    return False\n                self.effects.remove_named_state(ENEMY, name, now=now)\n'''
    text = replace_once(text, old, new, label="instant stack-heal execution")

    old = '''        elif effect.effect_type == "buff":\n            if stat in self._SHIELD_STATS and any(target == ENEMY for target in targets):\n                return False\n            was_active = self.effects.group_active(effect.effect_id, targets, now=now)\n            activated_group = self.effects.activate_group(effect, targets, now, self.scheduler)\n            if (\n                activated_group\n                and effect.name\n                and effect.name in self._self_stack_dependency_names\n            ):\n'''
    new = '''        elif effect.effect_type == "buff":\n            if stat in self._SHIELD_STATS and any(target == ENEMY for target in targets):\n                return False\n            marker_stack_before = (\n                self.effects.named_stack(effect.actor, effect.name or "", now=now)\n                if self._self_stack_reach_marker_shape_supported(effect)\n                else None\n            )\n            was_active = self.effects.group_active(effect.effect_id, targets, now=now)\n            activated_group = self.effects.activate_group(effect, targets, now, self.scheduler)\n            if activated_group and marker_stack_before is not None and effect.name:\n                marker_stack_after = self.effects.named_stack(\n                    effect.actor, effect.name, now=now\n                )\n                if marker_stack_after > marker_stack_before + 1e-9:\n                    stack_int = int(round(marker_stack_after))\n                    if abs(marker_stack_after - stack_int) <= 1e-9:\n                        from .burst import BurstSignal\n                        self.dispatch(\n                            BurstSignal(\n                                now,\n                                f"stack_reach:{effect.name}:{stack_int}",\n                                effect.actor,\n                                effect.actor,\n                            )\n                        )\n            if (\n                activated_group\n                and effect.name\n                and effect.name in self._self_stack_dependency_names\n            ):\n'''
    text = replace_once(text, old, new, label="stack reach dispatch")

    path.write_text(text, encoding="utf-8")


def patch_score() -> None:
    path = Path("fast_engine/engine/score.py")
    text = path.read_text(encoding="utf-8")
    old = '''    for key in keys:\n        name = key[len("event:"):]\n        providers = tuple(\n'''
    new = '''    for key in keys:\n        if key == "event:heal_received":\n            if not TriggerDispatcher.heal_received_dependency_score_safe(squad, effect):\n                return False\n            continue\n        name = key[len("event:"):]\n        providers = tuple(\n'''
    text = replace_once(text, old, new, label="score heal dependency")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_dispatcher()
    patch_score()
    print("applied temporary generic stack-reach/self-heal/heal-received bridge")


if __name__ == "__main__":
    main()
