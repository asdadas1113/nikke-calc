from __future__ import annotations

from collections import Counter

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import ConditionMode
from fast_engine.engine.score import static_score_blockers

STATIC_MODES = {
    ConditionMode.HAS_BURST1_ALLY,
    ConditionMode.NO_BURST1_ALLY,
    ConditionMode.HAS_DEFENDER_ALLY,
    ConditionMode.NO_DEFENDER_ALLY,
}


def actor_has_b1_ally(compiled, actor: int) -> bool:
    return any(i != actor and m.burst_stage == '1' for i, m in enumerate(compiled.members))


def actor_has_defender_ally(compiled, actor: int) -> bool:
    return any(i != actor and m.character_class == '방어형' for i, m in enumerate(compiled.members))


def static_truth(compiled, effect) -> tuple[tuple[str, bool], ...]:
    out = []
    for rule in effect.condition_rules:
        if rule.mode is ConditionMode.HAS_BURST1_ALLY:
            out.append((rule.raw, actor_has_b1_ally(compiled, effect.actor)))
        elif rule.mode is ConditionMode.NO_BURST1_ALLY:
            out.append((rule.raw, not actor_has_b1_ally(compiled, effect.actor)))
        elif rule.mode is ConditionMode.HAS_DEFENDER_ALLY:
            out.append((rule.raw, actor_has_defender_ally(compiled, effect.actor)))
        elif rule.mode is ConditionMode.NO_DEFENDER_ALLY:
            out.append((rule.raw, not actor_has_defender_ally(compiled, effect.actor)))
    return tuple(out)


def ally_stage_override_rows(compiled, actor: int):
    return tuple(
        (e.effect_id, compiled.members[e.actor].name, e.name, e.stat, tuple(r.raw for r in e.condition_rules), tuple(t.event_key for t in e.triggers))
        for e in compiled.effects
        if e.actor != actor and (e.stat or '').startswith('burst_stage_override:')
    )


def consumers(compiled, name: str):
    state = []
    state_end = []
    mutators = []
    scaling = []
    for e in compiled.effects:
        if any(r.key == name for r in e.condition_rules):
            state.append((e.effect_id, compiled.members[e.actor].name, e.name, e.stat, tuple(r.raw for r in e.condition_rules)))
        if any((t.event_key or '') == f'event:state_end:{name}' for t in e.triggers):
            state_end.append((e.effect_id, compiled.members[e.actor].name, e.name, e.stat))
        if e.parameters.get('target_effect') == name:
            mutators.append((e.effect_id, compiled.members[e.actor].name, e.name, e.stat))
        if e.parameters.get('scaling_ref') == name:
            scaling.append((e.effect_id, compiled.members[e.actor].name, e.name, e.stat))
    return state, state_end, mutators, scaling


seen_memberships = set()
rows = []
for label, cfg in snapshot.SQUADS.items():
    members = tuple(cfg['members'])
    if len(members) != 5 or members in seen_memberships:
        continue
    seen_memberships.add(members)
    squad = spec.build_squad(list(members))
    compiled = compile_moris_squad(squad)
    blockers = tuple(static_score_blockers(compiled))
    for effect in compiled.effects:
        if (effect.stat or '') != 'remove_named_buff':
            continue
        if not effect.condition_rules or not all(r.mode in STATIC_MODES for r in effect.condition_rules):
            continue
        name = effect.parameters.get('target_effect')
        providers = tuple(p for p in compiled.effects if p.name == name and p.effect_id != effect.effect_id)
        owner = compiled.members[effect.actor].name
        rows.append((label, members, compiled, effect, providers, blockers))
        print('\n=== STATIC_REMOVER ===')
        print('membership', label, members)
        print('owner', owner)
        print('remover', effect.effect_id, effect.name, effect.stat, effect.target, effect.parameters)
        print('remover_conditions', [(r.raw, r.mode.value) for r in effect.condition_rules])
        print('remover_static_truth', static_truth(compiled, effect))
        print('remover_triggers', [(r.raw, r.event_key, r.mode.value) for r in effect.triggers])
        print('ally_stage_overrides', ally_stage_override_rows(compiled, effect.actor))
        print('providers', [
            (p.effect_id, compiled.members[p.actor].name, p.name, p.effect_type, p.stat, p.target,
             p.value, p.duration, p.max_stack,
             [(r.raw, r.mode.value) for r in p.condition_rules],
             static_truth(compiled, p),
             [(t.raw, t.event_key, t.mode.value) for t in p.triggers],
             dict(p.parameters))
            for p in providers
        ])
        if isinstance(name, str):
            print('consumers', consumers(compiled, name))
        hit = tuple(b for b in blockers if owner in b or (isinstance(name, str) and name in b))
        print('relevant_blockers', hit)

print('\nSTATIC_REMOVER_COUNT', len(rows))
print('STATIC_REMOVER_NAMES', Counter((r[3].name, r[3].parameters.get('target_effect')) for r in rows))

# Detailed public traces for the Anis : Star anchor.
anis_rows = [r for r in rows if r[3].name == '스타 폴 4' or r[3].parameters.get('target_effect') == '나만의 별']
for label, members, compiled, remover, providers, blockers in anis_rows:
    print('\n=== ANIS_STAR_PUBLIC_TRACE ===')
    print('label', label, 'members', members)
    result = simulate(
        spec.build_squad(list(members)),
        config={'duration': 35.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'},
        seed=42,
        verbose=True,
    )
    print('buff_events', [
        (float(e.t), e.kind, e.owner, e.target, e.name, e.stat, e.value)
        for e in result.log.buff_events if e.name in {'나만의 별', '모두의 별'}
    ])
    print('burst_log', [(float(e.t), e.event) for e in result.log.burst_log])

# Controlled opposite-roster trace: replace one non-Anis member with a known B1 ally.
if anis_rows:
    base_members = list(anis_rows[0][1])
    anis_idx = base_members.index('아니스 : 스타')
    replace_idx = next(i for i in range(5) if i != anis_idx)
    controlled = list(base_members)
    controlled[replace_idx] = '리틀 머메이드'
    if len(set(controlled)) == 5:
        print('\n=== ANIS_STAR_B1_CONTROL_TRACE ===')
        print('members', tuple(controlled))
        controlled_squad = spec.build_squad(controlled)
        controlled_compiled = compile_moris_squad(controlled_squad)
        actor = controlled.index('아니스 : 스타')
        print('base_stages', [(m.name, m.burst_stage) for m in controlled_compiled.members])
        print('ally_stage_overrides', ally_stage_override_rows(controlled_compiled, actor))
        for e in controlled_compiled.members[actor].effects:
            if e.name in {'나만의 별', '모두의 별', '스타 폴 2', '스타 폴 4'}:
                print('anis_effect', e.name, e.stat, static_truth(controlled_compiled, e), tuple(r.raw for r in e.condition_rules), tuple(t.event_key for t in e.triggers))
        result = simulate(
            controlled_squad,
            config={'duration': 35.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'},
            seed=42,
            verbose=True,
        )
        print('buff_events', [
            (float(e.t), e.kind, e.owner, e.target, e.name, e.stat, e.value)
            for e in result.log.buff_events if e.name in {'나만의 별', '모두의 별'}
        ])
        print('burst_log', [(float(e.t), e.event) for e in result.log.burst_log])
