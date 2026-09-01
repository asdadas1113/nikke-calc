from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "fast_engine/engine/effects.py",
    "        self._dynamic_bullet_targets = selected\n",
    "        # Registration is additive: charge and rapid score runtimes may\n"
    "        # both own recipient-shot lifetimes in the same squad.\n"
    "        self._dynamic_bullet_targets = self._dynamic_bullet_targets | selected\n",
)

replace_once(
    "fast_engine/engine/dynamic_weapon.py",
    "        self._score_actors = selected\n        self._score_shot_sink = sink\n",
    "        # Charge duration_bullets must be registered before battle-start\n"
    "        # activation so ActiveEffectStore does not schedule a stale static\n"
    "        # Nth-shot expiry. Rapid registration is additive in the store.\n"
    "        self.effects.enable_dynamic_bullet_lifetime_targets(selected)\n"
    "        self._score_actors = selected\n        self._score_shot_sink = sink\n",
)

replace_once(
    "fast_engine/engine/dynamic_weapon.py",
    "        if actor in self._hit_thresholds:\n"
    "            signals.append(DynamicCountSignal(\"hit_count\", count_increment))\n"
    "        return DynamicChargeBoundary(\n",
    "        if actor in self._hit_thresholds:\n"
    "            signals.append(DynamicCountSignal(\"hit_count\", count_increment))\n"
    "        if self.effects.has_dynamic_bullet_lifetime(actor, now=float(event.time)):\n"
    "            # The consuming charge shot is scored above and its hit/full-charge\n"
    "            # signals are delivered first. Remove bullet-duration state only at\n"
    "            # the same post-shot point used by the rapid runtime.\n"
    "            signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))\n"
    "        return DynamicChargeBoundary(\n",
)

core_block = '''def _actor_has_executable_core_count(squad: CompiledSquad, actor: int) -> bool:
    return any(
        TriggerDispatcher.is_executable_effect(effect)
        and any(is_static_expected_core_count_rule(rule) for rule in effect.triggers)
        for effect in squad.members[actor].effects
    )


'''
helpers = core_block + '''def _reload_speed_positive_upper_bound(squad: CompiledSquad, actor: int) -> float:
    """Conservative upper bound for beneficial reload speed on one actor.

    ``cover_during_delay`` only changes Moris behavior once reload speed reaches
    100%. Counting every possibly-targeting positive buff at maximum stack is an
    intentionally loose bound: if even this stays below 100, the special branch
    is provably unreachable for the squad.
    """

    total = 0.0
    for effect in squad.effects:
        if effect.effect_type != "buff" or (effect.stat or "") != "reload_speed_pct":
            continue
        if actor not in _possible_ally_targets(squad, effect):
            continue
        value = max(0.0, float(effect.value or 0.0))
        if value <= 0.0:
            continue
        max_stack = effect.max_stack
        if max_stack is not None and float(max_stack) < 0.0:
            return inf
        stacks = 1.0 if max_stack is None else max(1.0, float(max_stack))
        total += value * stacks
    return total


def _charge_actor_score_safe(squad: CompiledSquad, actor: int) -> bool:
    """Safety contract for per-shot dynamic SR/RL score ownership."""

    member = squad.members[actor]
    if str(member.weapon.get("fire_mode") or "") != "charge":
        return False
    if member.weapon.get("control") or member.weapon.get("is_clip"):
        return False
    if (
        member.weapon.get("cover_during_delay")
        and _reload_speed_positive_upper_bound(squad, actor) >= 100.0 - 1e-9
    ):
        return False

    for effect in squad.effects:
        if effect.effect_type == "weapon_change" and actor in _possible_ally_targets(squad, effect):
            return False

    if _actor_has_executable_core_count(squad, actor):
        return False
    if _actor_has_executable_event(
        squad,
        actor,
        frozenset({"last_bullet_fire", "on_attack", "event:full_reload", "full_reload"}),
    ):
        return False
    if _actor_has_executable_event(squad, actor, frozenset({"pellet_hit"})):
        return False
    return not _actor_has_unhandled_count_event(
        squad, actor, frozenset({"hit_count"})
    )


'''
replace_once("fast_engine/engine/score.py", core_block, helpers)

old_reload = '''def _reload_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
    member = squad.members[actor]
    mode = str(member.weapon.get("fire_mode") or "")
    if mode in {"auto", "auto_warmup"}:
        return _rapid_actor_score_safe(squad, actor)
    if mode != "charge":
        return False
    if member.weapon.get("control") or member.weapon.get("is_clip"):
        return False
    if member.weapon.get("cover_during_delay"):
        return False

    for effect in squad.effects:
        if effect.effect_type != "weapon_change":
            continue
        if actor in _possible_ally_targets(squad, effect):
            return False

    if _actor_has_executable_core_count(squad, actor):
        return False
    if _actor_has_executable_event(
        squad,
        actor,
        frozenset({"last_bullet_fire", "on_attack", "event:full_reload", "full_reload"}),
    ):
        return False
    if _actor_has_executable_event(squad, actor, frozenset({"pellet_hit"})):
        return False
    return not _actor_has_unhandled_count_event(
        squad, actor, frozenset({"hit_count"})
    )


'''
new_reload = '''def _reload_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
    member = squad.members[actor]
    mode = str(member.weapon.get("fire_mode") or "")
    if mode in {"auto", "auto_warmup"}:
        return _rapid_actor_score_safe(squad, actor)
    if mode == "charge":
        return _charge_actor_score_safe(squad, actor)
    return False


'''
replace_once("fast_engine/engine/score.py", old_reload, new_reload)

marker = "def _dynamic_charge_score_actors(squad: CompiledSquad) -> tuple[int, ...]:\n"
helper = '''def _dynamic_charge_bullet_lifetime_score_actors(
    squad: CompiledSquad,
) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if effect.parameters.get("duration_bullets") is None:
            continue
        if not is_direct_damage_buff_runtime_supported(effect):
            continue
        if not TriggerDispatcher.is_executable_effect(effect):
            continue
        for actor in _possible_ally_targets(squad, effect):
            if _charge_actor_score_safe(squad, actor):
                actors.add(actor)
    return tuple(sorted(actors))


''' + marker
replace_once("fast_engine/engine/score.py", marker, helper)

replace_once(
    "fast_engine/engine/score.py",
    "    actors.update(charge & set(_dynamic_reload_score_actors(squad)))\n"
    "    return tuple(sorted(actors))\n",
    "    actors.update(charge & set(_dynamic_reload_score_actors(squad)))\n"
    "    actors.update(_dynamic_charge_bullet_lifetime_score_actors(squad))\n"
    "    return tuple(sorted(actors))\n",
)

replace_once(
    "fast_engine/engine/score.py",
    "    return bool(targets) and all(\n"
    "        static_bullet_lifetime_cadence_safe(squad, actor)\n"
    "        for actor in targets\n"
    "    )\n",
    "    return bool(targets) and all(\n"
    "        static_bullet_lifetime_cadence_safe(squad, actor)\n"
    "        or _charge_actor_score_safe(squad, actor)\n"
    "        for actor in targets\n"
    "    )\n",
)

replace_once(
    "fast_engine/tests/test_damage_helm_bullet_lifetime.py",
    "from fast_engine.engine.burst import BurstMachine, compile_burst_policy\n",
    "from fast_engine.engine.burst import BurstMachine, BurstPolicy, compile_burst_policy\n"
    "from fast_engine.engine.burst_runtime import BurstRuntime\n",
)
replace_once(
    "fast_engine/tests/test_damage_helm_bullet_lifetime.py",
    "from fast_engine.engine.score import static_score_blockers\n",
    "from fast_engine.engine.score import StaticNormalAttackObserver, static_score_blockers\n",
)

test_marker = "    def test_reactivation_resets_ten_shot_generation(self):\n"
tests = '''    def test_dynamic_charge_owner_consumes_ten_shot_lifetime(self):
        compiled, _policy, helm = self._fixture()
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=20.0, first_burst_time=30.0),
            EnemyStaticProfile(defense=31784.0, duration=20.0),
        )
        observer = StaticNormalAttackObserver(runtime, duration=20.0)
        self.assertIn(2, observer.dynamic_charge_actors)
        self.assertTrue(runtime.dispatcher.effects.dynamic_bullet_lifetime_supported(2))

        runtime.dispatcher.effects.activate(helm, 2, 0.0, runtime.scheduler)
        self.assertGreater(
            runtime.dispatcher.effects.sum_stat(2, "charge_dmg_mag_pct", now=0.0),
            0.0,
        )
        runtime.run(duration=20.0, score_observer=observer)
        self.assertEqual(
            runtime.dispatcher.effects.sum_stat(2, "charge_dmg_mag_pct", now=19.9),
            0.0,
        )

    def test_squad1_helm_charge_lifetime_and_crown_reload_are_certified(self):
        names = ["리틀 머메이드", "크라운", "라피 : 레드 후드", "미하라 : 본딩 체인", "헬름"]
        compiled = compile_moris_squad(build_squad(names))
        blockers = static_score_blockers(compiled)
        self.assertNotIn("cadence:크라운:원 포 올 2:reload_speed_pct", blockers)
        self.assertNotIn("normal_delivery:헬름:이지스 캐논 3:charge_dmg_mag_pct", blockers)
        self.assertNotIn("skill_state_delivery:헬름:이지스 캐논 3:charge_dmg_mag_pct", blockers)
        self.assertIn("cadence:리틀 머메이드:세이렌 송 2:ammo_charge_pct", blockers)
        self.assertIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)

''' + test_marker
replace_once("fast_engine/tests/test_damage_helm_bullet_lifetime.py", test_marker, tests)
