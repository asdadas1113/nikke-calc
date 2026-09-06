from pathlib import Path

# Scope live effective-weapon lookup to the rapid actors that can actually
# receive an executable weapon-change. Ordinary rapid actors in the same squad
# must stay on the zero-allocation base-weapon path.
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

print("Moran actor-scoped effective weapon patch staged")
