from pathlib import Path


def patch_dispatcher() -> None:
    path = Path("fast_engine/engine/dispatcher.py")
    text = path.read_text()
    old = '''    @staticmethod
    def _lazy_rank_target_shape_supported(effect: "CompiledEffect") -> bool:
        """Own simple Moris lazy ATK-rank direct buffs without bullet lifetimes."""

        max_stack = effect.max_stack if effect.max_stack is not None else 1.0
        return (
            effect.effect_type == "buff"
            and effect.target_spec.mode in TriggerDispatcher._LAZY_ATK_RANK_MODES
            and is_direct_damage_buff_runtime_supported(effect)
            and float(max_stack) == 1.0
            and effect.max_trigger is None
            and effect.tick_interval is None
            and effect.parameters.get("duration_bullets") is None
            and effect.parameters.get("event_scope") != "recipients"
            and not effect.condition_rules
        )
'''
    new = '''    @staticmethod
    def _lazy_rank_target_shape_supported(effect: "CompiledEffect") -> bool:
        """Own simple Moris lazy ATK-rank states without bullet lifetimes.

        Direct-damage buffs retain the existing generic slice. Cadence is much
        narrower: one finite positive caster-based charge-speed buff delivered
        to the lowest-ATK base B3 at full-burst start. Recipient weapon safety
        is a squad-level score proof, not a runtime-shape assumption.
        """

        max_stack = effect.max_stack if effect.max_stack is not None else 1.0
        common = (
            effect.effect_type == "buff"
            and effect.target_spec.mode in TriggerDispatcher._LAZY_ATK_RANK_MODES
            and float(max_stack) == 1.0
            and effect.max_trigger is None
            and effect.tick_interval is None
            and effect.parameters.get("duration_bullets") is None
            and effect.parameters.get("event_scope") != "recipients"
            and not effect.condition_rules
        )
        if not common:
            return False
        if is_direct_damage_buff_runtime_supported(effect):
            return True
        return (
            effect.target_spec.mode is TargetMode.LOWEST_ATK_BURST3
            and int(effect.target_spec.count or 0) == 1
            and (effect.stat or "") == "charge_speed_caster_based_pct"
            and effect.value is not None
            and float(effect.value) >= 0.0
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and not effect.parameters
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.EVENT
            and effect.triggers[0].event_key == "full_burst_start"
        )
'''
    if old not in text:
        raise SystemExit("dispatcher patch anchor not found")
    path.write_text(text.replace(old, new))


def patch_score() -> None:
    path = Path("fast_engine/engine/score.py")
    text = path.read_text()
    old = '''def _ammo_charge_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
    if _actor_has_live_max_ammo_mutation(squad, actor):
        return False
    mode = str(squad.members[actor].weapon.get("fire_mode") or "")
    if mode in {"auto", "auto_warmup"}:
        return _rapid_actor_score_safe(squad, actor)
    if mode == "charge":
        return _charge_actor_score_safe(squad, actor)
    return False
'''
    new = '''def _same_event_self_max_ammo_before_refill_score_safe(
    squad: CompiledSquad, effect, actor: int
) -> bool:
    """Own one live self max-ammo -> 100% refill transaction in actor order.

    Moris computes ``ammo_charge_pct`` from effective max ammo at the instant of
    activation. The first owned live-max slice therefore requires one positive
    finite self ``max_ammo_pct`` source on the same ``full_burst_start`` and
    requires that source to precede the refill in the actor's compiled order.
    Any competing max-ammo producer or wider refill shape remains fail-closed.
    """

    if not (
        effect.actor == actor
        and effect.effect_type == "instant"
        and (effect.stat or "") == "ammo_charge_pct"
        and effect.target_spec.mode is TargetMode.SELF
        and effect.value is not None
        and abs(float(effect.value) - 100.0) <= 1e-9
        and not effect.parameters
        and not effect.condition_rules
        and len(effect.triggers) == 1
        and effect.triggers[0].mode is TriggerMode.EVENT
        and effect.triggers[0].event_key == "full_burst_start"
    ):
        return False

    live = tuple(
        other
        for other in squad.effects
        if (other.stat or "") in {"max_ammo_pct", "max_ammo_flat", "max_ammo_infinite"}
        and not _is_folded_static_self_modifier(other)
        and actor in _possible_ally_targets(squad, other)
    )
    if len(live) != 1:
        return False
    source = live[0]
    if not (
        source.actor == actor
        and (source.stat or "") == "max_ammo_pct"
        and source.effect_type == "buff"
        and source.target_spec.mode is TargetMode.SELF
        and source.value is not None
        and float(source.value) > 0.0
        and source.duration is not None
        and float(source.duration) > 0.0
        and source.max_stack in (None, 1, 1.0)
        and source.max_trigger is None
        and source.tick_interval is None
        and not source.parameters
        and not source.condition_rules
        and len(source.triggers) == 1
        and source.triggers[0].mode is TriggerMode.EVENT
        and source.triggers[0].event_key == "full_burst_start"
        and _is_dynamic_max_ammo_score_supported(squad, source)
    ):
        return False

    ordered = tuple(row.effect_id for row in squad.members[actor].effects)
    return ordered.index(source.effect_id) < ordered.index(effect.effect_id)


def _ammo_charge_recipient_score_safe(
    squad: CompiledSquad, actor: int, effect=None
) -> bool:
    if _actor_has_live_max_ammo_mutation(squad, actor):
        if effect is None or not _same_event_self_max_ammo_before_refill_score_safe(
            squad, effect, actor
        ):
            return False
    mode = str(squad.members[actor].weapon.get("fire_mode") or "")
    if mode in {"auto", "auto_warmup"}:
        return _rapid_actor_score_safe(squad, actor)
    if mode == "charge":
        return _charge_actor_score_safe(squad, actor)
    return False
'''
    if old not in text:
        raise SystemExit("ammo proof patch anchor not found")
    text = text.replace(old, new)

    old = '''    return bool(targets) and all(
        _ammo_charge_recipient_score_safe(squad, actor) for actor in targets
    )
'''
    new = '''    return bool(targets) and all(
        _ammo_charge_recipient_score_safe(squad, actor, effect) for actor in targets
    )
'''
    if old not in text:
        raise SystemExit("ammo recipient call anchor not found")
    text = text.replace(old, new, 1)

    old = '''def _lazy_rank_target_score_safe(squad: CompiledSquad, effect) -> bool:
    if not TriggerDispatcher._lazy_rank_target_shape_supported(effect):
        return False
    if not effect.name:
        return True
    named_event_key = f"event:{effect.name}"
    if any(
        any((rule.event_key or "") == named_event_key for rule in other.triggers)
        for other in squad.effects
        if other.effect_id != effect.effect_id
    ):
        return False
    return not any(
        rule.key == effect.name
        for other in squad.effects
        if other.effect_id != effect.effect_id
        for rule in other.condition_rules
    )
'''
    new = '''def _lazy_rank_target_score_safe(squad: CompiledSquad, effect) -> bool:
    if not TriggerDispatcher._lazy_rank_target_shape_supported(effect):
        return False
    if (effect.stat or "") == "charge_speed_caster_based_pct":
        if effect.target_spec.mode is not TargetMode.LOWEST_ATK_BURST3:
            return False
        # Moris LOWEST_ATK_BURST3 uses parsed/base burst stage, not live stage
        # overrides. Restrict cadence ownership to those immutable B3 candidates
        # and require every possible recipient to have certified charge cadence.
        candidates = tuple(
            actor
            for actor, member in enumerate(squad.members)
            if member.burst_stage == "3"
        )
        if not candidates or not all(
            _charge_actor_score_safe(squad, actor) for actor in candidates
        ):
            return False
        if not _charge_actor_score_safe(squad, effect.actor):
            return False
    if not effect.name:
        return True
    named_event_key = f"event:{effect.name}"
    if any(
        any((rule.event_key or "") == named_event_key for rule in other.triggers)
        for other in squad.effects
        if other.effect_id != effect.effect_id
    ):
        return False
    return not any(
        rule.key == effect.name
        for other in squad.effects
        if other.effect_id != effect.effect_id
        for rule in other.condition_rules
    )
'''
    if old not in text:
        raise SystemExit("lazy score patch anchor not found")
    path.write_text(text.replace(old, new))


patch_dispatcher()
patch_score()
