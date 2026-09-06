from pathlib import Path

# 1) Scope live effective-weapon lookup to rapid actors that can actually receive
# an executable weapon-change. Ordinary rapid actors in the same squad stay on
# the zero-allocation base-weapon path.
p = Path("fast_engine/engine/dynamic_reload.py")
text = p.read_text(encoding="utf-8")
old = '''        "_score_sink",\n        "_effective_weapon",\n    )\n'''
new = '''        "_score_sink",\n        "_effective_weapon",\n        "_effective_weapon_actors",\n    )\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("dynamic reload slots anchor missing")
    text = text.replace(old, new, 1)

old = '''        self._score_sink: Callable[[int, int, float], None] | None = None\n        self._effective_weapon: Callable[[int, float], dict] | None = None\n\n        hit_thresholds: dict[int, tuple[int, ...]] = {}\n'''
new = '''        self._score_sink: Callable[[int, int, float], None] | None = None\n        self._effective_weapon: Callable[[int, float], dict] | None = None\n        self._effective_weapon_actors: frozenset[int] = frozenset()\n\n        hit_thresholds: dict[int, tuple[int, ...]] = {}\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("dynamic reload init anchor missing")
    text = text.replace(old, new, 1)

old = '''    def attach_effective_weapon(\n        self, callback: Callable[[int, float], dict]\n    ) -> None:\n        if self._states:\n            raise RuntimeError("Fast effective weapon callback must be attached before weapon start")\n        self._effective_weapon = callback\n\n    def _weapon(self, actor: int, now: float) -> dict:\n        if self._effective_weapon is None:\n            return self.squad.members[actor].weapon\n        return self._effective_weapon(actor, float(now))\n'''
new = '''    def attach_effective_weapon(\n        self,\n        callback: Callable[[int, float], dict],\n        actors: tuple[int, ...] | frozenset[int] | None = None,\n    ) -> None:\n        if self._states:\n            raise RuntimeError("Fast effective weapon callback must be attached before weapon start")\n        selected = (\n            frozenset(range(len(self.squad.members)))\n            if actors is None\n            else frozenset(int(actor) for actor in actors)\n        )\n        if any(actor < 0 or actor >= len(self.squad.members) for actor in selected):\n            raise IndexError("Fast effective weapon actor out of range")\n        self._effective_weapon = callback\n        self._effective_weapon_actors = selected\n\n    def _weapon(self, actor: int, now: float) -> dict:\n        if self._effective_weapon is None or actor not in self._effective_weapon_actors:\n            return self.squad.members[actor].weapon\n        return self._effective_weapon(actor, float(now))\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("dynamic reload effective weapon anchor missing")
    text = text.replace(old, new, 1)

# 2) A dynamic rapid score actor with no local observable shot boundary does not
# need a future scheduler token. Its ordinary shots are still compressed forward
# by advance_to() at the next global event or score horizon. Avoid scanning every
# remaining physical shot merely to prove that no boundary exists.
old = '''    @staticmethod\n    def _crosses(before: int, after: int, thresholds: tuple[int, ...]) -> bool:\n        return any(before // threshold != after // threshold for threshold in thresholds)\n\n    def _shot_is_boundary(self, st: _RapidActorState) -> bool:\n'''
new = '''    @staticmethod\n    def _crosses(before: int, after: int, thresholds: tuple[int, ...]) -> bool:\n        return any(before // threshold != after // threshold for threshold in thresholds)\n\n    def _has_local_boundary_interest(self, actor: int, now: float) -> bool:\n        return (\n            actor in self._last_bullet_actors\n            or bool(self._hit_thresholds.get(actor))\n            or bool(self._pellet_thresholds.get(actor))\n        )\n\n    def _shot_is_boundary(self, st: _RapidActorState) -> bool:\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("dynamic reload boundary-interest anchor missing")
    text = text.replace(old, new, 1)

old = '''    def _predict_next_boundary(self, actor: int) -> tuple[float, int] | None:\n        st = replace(self._states[actor])\n        while st.phase_end <= self.duration + _EPS:\n'''
new = '''    def _predict_next_boundary(self, actor: int) -> tuple[float, int] | None:\n        source = self._states[actor]\n        if not self._has_local_boundary_interest(actor, source.phase_end):\n            return None\n        st = replace(source)\n        while st.phase_end <= self.duration + _EPS:\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("dynamic reload predict anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

p = Path("fast_engine/engine/dynamic_rapid.py")
text = p.read_text(encoding="utf-8")
old = '''    def _shot_is_boundary(self, st: _RapidActorState) -> bool:\n        if self.effects.has_dynamic_bullet_lifetime(st.actor, now=st.phase_end):\n            return True\n        return super()._shot_is_boundary(st)\n'''
new = '''    def _has_local_boundary_interest(self, actor: int, now: float) -> bool:\n        return (\n            super()._has_local_boundary_interest(actor, now)\n            or self.effects.has_dynamic_bullet_lifetime(actor, now=now)\n        )\n\n    def _shot_is_boundary(self, st: _RapidActorState) -> bool:\n        if self.effects.has_dynamic_bullet_lifetime(st.actor, now=st.phase_end):\n            return True\n        return super()._shot_is_boundary(st)\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("dynamic rapid boundary-interest anchor missing")
    text = text.replace(old, new, 1)

old = '''    def _predict_next_boundary(self, actor: int) -> tuple[float, int] | None:\n        st = self._states[actor]\n        # Keep the base runtime's cheap copy-only prediction contract.\n        from dataclasses import replace\n\n        probe = replace(st)\n'''
new = '''    def _predict_next_boundary(self, actor: int) -> tuple[float, int] | None:\n        st = self._states[actor]\n        if not self._has_local_boundary_interest(actor, st.phase_end):\n            return None\n        # Keep the base runtime's cheap copy-only prediction contract.\n        from dataclasses import replace\n\n        probe = replace(st)\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("dynamic rapid predict anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

p = Path("fast_engine/engine/dynamic_weapon.py")
text = p.read_text(encoding="utf-8")
old = '''        if any(\n            effect.effect_type == "weapon_change"\n            and effect_filter(effect)\n            and str(squad.members[effect.actor].weapon.get("fire_mode") or "")\n            in {"auto", "auto_warmup"}\n            for effect in squad.effects\n        ):\n            self._rapid_reload.attach_effective_weapon(self.effective_weapon)\n\n        actors = set(self.actors)\n'''
new = '''        rapid_weapon_change_actors = frozenset(\n            effect.actor\n            for effect in squad.effects\n            if effect.effect_type == "weapon_change"\n            and effect_filter(effect)\n            and str(squad.members[effect.actor].weapon.get("fire_mode") or "")\n            in {"auto", "auto_warmup"}\n        )\n        if rapid_weapon_change_actors:\n            self._rapid_reload.attach_effective_weapon(\n                self.effective_weapon, rapid_weapon_change_actors\n            )\n\n        actors = set(self.actors)\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("dynamic weapon rapid callback anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

p = Path("fast_engine/tests/test_damage_moran_weapon_change_lifecycle.py")
text = p.read_text(encoding="utf-8")
anchor = '''    def test_shape_rejects_wider_weapon_modes(self):\n'''
insert = '''    def test_live_weapon_view_is_scoped_to_actual_weapon_change_actor(self):\n        compiled = self._compiled()\n        effect = self._producer(compiled)\n        actor = effect.actor\n        enemy = EnemyStaticProfile(defense=31784.0, duration=20.0, core_px=0.0)\n        runtime = BurstRuntime(\n            compiled,\n            BurstPolicy(duration=20.0, first_burst_time=3.0),\n            enemy,\n            damage_sink=SimpleDamageScoreSink(compiled, enemy),\n        )\n        rapid = runtime.weapons._rapid_reload\n        self.assertEqual(rapid._effective_weapon_actors, frozenset({actor}))\n\n        mast = next(\n            i for i, member in enumerate(compiled.members)\n            if member.name == "마스트 : 로망틱 메이드"\n        )\n        self.assertNotIn(mast, rapid._effective_weapon_actors)\n        self.assertIs(rapid._weapon(mast, 0.0), compiled.members[mast].weapon)\n\n'''
if insert not in text:
    if anchor not in text:
        raise RuntimeError("Moran actor-scope test anchor missing")
    text = text.replace(anchor, insert + anchor, 1)
p.write_text(text, encoding="utf-8")

p = Path("fast_engine/tests/test_damage_dynamic_reload_scoring.py")
text = p.read_text(encoding="utf-8")
if "from unittest.mock import patch\n" not in text:
    text = text.replace("import unittest\n", "import unittest\nfrom unittest.mock import patch\n", 1)
if "from fast_engine.engine.dynamic_rapid import DynamicRapidCadenceRuntime\n" not in text:
    text = text.replace(
        "from fast_engine.engine.capabilities import (\n",
        "from fast_engine.engine.dynamic_rapid import DynamicRapidCadenceRuntime\nfrom fast_engine.engine.capabilities import (\n",
        1,
    )
anchor = '''    def test_auto_reload_duration_is_fixed_at_reload_start(self):\n'''
insert = '''    def test_boundaryless_dynamic_actor_does_not_scan_to_horizon_for_plan(self):\n        effect = _reload_effect(duration=180.0)\n        squad = _squad(effect)\n        enemy = EnemyStaticProfile(\n            defense=0.0, core_uptime=0.0, core_px=0.0, duration=180.0\n        )\n        runtime = BurstRuntime(\n            squad, BurstPolicy(duration=180.0, first_burst_time=200.0), enemy\n        )\n        runtime.dispatcher.effects.activate(effect, 0, 0.0, runtime.scheduler)\n        StaticNormalAttackObserver(runtime, duration=180.0)\n        rapid = runtime.weapons._rapid_reload\n        with patch.object(\n            DynamicRapidCadenceRuntime,\n            "_after_shot",\n            side_effect=AssertionError("boundaryless plan simulated physical shots"),\n        ):\n            runtime.weapons.start(0.0)\n        self.assertIsNone(rapid._states[0].scheduled_time)\n        self.assertFalse(rapid._has_local_boundary_interest(0, 0.0))\n\n'''
if insert not in text:
    if anchor not in text:
        raise RuntimeError("dynamic reload boundaryless test anchor missing")
    text = text.replace(anchor, insert + anchor, 1)
p.write_text(text, encoding="utf-8")

print("Moran actor-scoped weapon view and sparse boundaryless planner staged")
