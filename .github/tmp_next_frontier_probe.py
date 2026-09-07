from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context import spec
from fast_engine.research.public_ranking_probe import _source_corpus
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

for members,label in _source_corpus():
    if label != '레이드_네온벨벳':
        continue
    raw=spec.build_squad(list(members))
    squad=compile_moris_squad(raw)
    print('TEAM',label, squad.names)
    print('BLOCKERS', static_score_blockers(squad))
    for i,m in enumerate(squad.members):
        print('MEMBER',i,m.name,m.weapon)
        if m.name == '벨벳':
            for e in m.effects:
                print('EFFECT', e.effect_id, e.name, e.effect_type, e.stat, e.value, e.duration, e.max_stack, e.max_trigger, e.tick_interval, dict(e.parameters), [(r.raw,r.event_key,r.mode.value,r.threshold,r.trigger_count_reducible) for r in e.triggers], [(c.raw,c.mode.value,c.key,c.value) for c in e.condition_rules], e.capability.disposition.value, tuple(e.capability.blockers), e.target_spec.mode.value, e.target_spec.runtime_supported)
