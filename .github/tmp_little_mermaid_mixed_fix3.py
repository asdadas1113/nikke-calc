from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'fast_engine/tests/test_damage_little_mermaid_mixed_squad_ammo.py'
s=p.read_text()
old='''    runtime.weapons.attach_squad_ammo_thresholds(thresholds)\n    return runtime\n'''
new='''    runtime.weapons.attach_squad_ammo_thresholds(thresholds)\n    # Mirror production StaticDamageScoreCursor wiring: burst-triggered ammo\n    # refills and force reloads must mutate the same live weapon runtime used by\n    # the mixed global-ammo proof. Omitting these sinks creates a false Helm\n    # reload divergence at the first Siren Song refill.\n    runtime.dispatcher.attach_ammo_charge_sink(runtime.weapons.apply_ammo_charge)\n    runtime.dispatcher.attach_force_reload_sink(runtime.weapons.apply_force_reload)\n    return runtime\n'''
assert s.count(old)==1,s.count(old)
p.write_text(s.replace(old,new,1))
print('mixed fixture production sink wiring applied')
