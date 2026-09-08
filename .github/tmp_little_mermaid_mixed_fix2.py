from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'fast_engine/engine/dynamic_weapon.py'
s=p.read_text()
old='''        row = super().handle_boundary(event)\n        if row is None:\n            return None\n        actor, _base_event_key, count_increment = row\n'''
new='''        # In the first mixed squad-ammo slice the sole ordinary charge actor is\n        # the final roster member. Moris processes same-frame weapon actors in\n        # roster order, so materialize the compressed rapid prefix through this\n        # frame before the charge actor consumes its bullet. This is only needed\n        # for the owned mixed global-ammo transaction; other charge boundaries\n        # keep their existing sparse ordering.\n        if event.actor in self._squad_ammo_charge_actors:\n            self._rapid_reload.advance_to(float(event.time), inclusive=True)\n\n        row = super().handle_boundary(event)\n        if row is None:\n            return None\n        actor, _base_event_key, count_increment = row\n'''
assert s.count(old)==1,s.count(old)
p.write_text(s.replace(old,new,1))
print('mixed same-frame ordering fix applied')
