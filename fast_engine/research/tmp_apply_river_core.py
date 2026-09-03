from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one patch anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    policy = ROOT / "fast_engine" / "engine" / "damage_policy.py"
    _replace_once(
        policy,
        '''    if any(rule.mode not in _SAFE_CONDITIONS for rule in effect.condition_rules):\n        return False\n''',
        '''    unsupported_conditions = tuple(\n        rule for rule in effect.condition_rules if rule.mode not in _SAFE_CONDITIONS\n    )\n    if unsupported_conditions:\n        # First fail-closed core-presence slice: Moris' `core_hit` condition on\n        # a raw post-shot full_charge_hit checks whether the target has an active\n        # core (enemy.core_px >= 1), not whether this projectile sampled a core\n        # hit. Keep every other CORE_HIT shape closed.\n        if not (\n            len(unsupported_conditions) == 1\n            and unsupported_conditions[0].mode is ConditionMode.CORE_HIT\n            and len(effect.condition_rules) == 1\n            and effect.target_spec.mode is TargetMode.SELF\n            and not effect.parameters\n            and len(effect.triggers) == 1\n            and effect.triggers[0].mode is TriggerMode.EVENT\n            and effect.triggers[0].event_key == "full_charge_hit"\n        ):\n            return False\n''',
    )

    runtime = ROOT / "fast_engine" / "engine" / "burst_runtime.py"
    _replace_once(
        runtime,
        '''from .conditions import SignalContext\n''',
        '''from .conditions import ConditionMode, SignalContext\n''',
    )
    _replace_once(
        runtime,
        '''from .damage_state import DamageTermResolver\nfrom .dispatcher import TriggerDispatcher\n''',
        '''from .damage_policy import is_direct_damage_buff_runtime_supported\nfrom .damage_state import DamageTermResolver\nfrom .dispatcher import TriggerDispatcher\n''',
    )
    _replace_once(
        runtime,
        '''        self.squad = squad\n        self.enemy = enemy or EnemyStaticProfile(duration=policy.duration)\n        self.policy = policy\n''',
        '''        self.squad = squad\n        self.enemy = enemy or EnemyStaticProfile(duration=policy.duration)\n        # `core_hit` as a condition on raw full_charge_hit is a target-core\n        # presence predicate in Moris. The historical aggregate Fast enemy\n        # profile (core_uptime/rate without core_px) cannot reconstruct that\n        # per-shot boolean, so do not silently guess.\n        if self.enemy.core_px is None and any(\n            is_direct_damage_buff_runtime_supported(effect)\n            and any(rule.mode is ConditionMode.CORE_HIT for rule in effect.condition_rules)\n            for effect in squad.effects\n        ):\n            raise NotImplementedError(\n                "Fast full_charge_hit core-presence condition requires explicit enemy.core_px"\n            )\n        self.policy = policy\n''',
    )
    _replace_once(
        runtime,
        '''                    for count_signal in boundary.signals:\n                        self.dispatcher.dispatch(\n                            BurstSignal(\n                                event.time,\n                                count_signal.event_key,\n                                boundary.actor,\n                                boundary.actor,\n                                count_increment=count_signal.count_increment,\n                            ),\n                            context=SignalContext(),\n                        )\n''',
        '''                    for count_signal in boundary.signals:\n                        # Moris evaluates the `core_hit` condition attached to a\n                        # raw full_charge_hit from target core presence, while\n                        # ordinary normal-hit core damage still uses the expected\n                        # weapon spread probability. Only this post-shot signal\n                        # carries the presence bit.\n                        context = SignalContext(\n                            core_hit=(\n                                count_signal.event_key == "full_charge_hit"\n                                and self.enemy.core_px is not None\n                                and float(self.enemy.core_px) >= 1.0\n                            )\n                        )\n                        self.dispatcher.dispatch(\n                            BurstSignal(\n                                event.time,\n                                count_signal.event_key,\n                                boundary.actor,\n                                boundary.actor,\n                                count_increment=count_signal.count_increment,\n                            ),\n                            context=context,\n                        )\n''',
    )
    print("applied temporary Riverellio generic core-presence/full-charge patch")


if __name__ == "__main__":
    main()
