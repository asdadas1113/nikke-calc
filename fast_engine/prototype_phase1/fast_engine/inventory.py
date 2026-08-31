from __future__ import annotations
import json, re, sys, os
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MORIS = Path(os.environ.get('MORIS_ROOT', str(REPO_ROOT)))
OUT = Path(os.environ.get('FAST_FEAS_OUT', str(Path(__file__).resolve().parents[1] / '_feasibility_output')))

skills = json.loads((MORIS/'data/parsed_skills.json').read_text(encoding='utf-8'))
impl_text = (MORIS/'context/IMPL-STATUS.md').read_text(encoding='utf-8')

# Parse documented stat implementation status. Only rows whose first column is a stat-like key.
impl_status: dict[str,str] = {}
for line in impl_text.splitlines():
    if not line.startswith('| `'):
        continue
    cols=[c.strip() for c in line.strip().strip('|').split('|')]
    if len(cols) < 2:
        continue
    status_cell = next((c for c in cols[1:] if any(m in c for m in ('✅','⚠️','❌','🚫'))), None)
    if status_cell is None:
        continue
    key=cols[0].strip('`')
    # Avoid condition/target table rows and prose examples.
    if key.startswith('"') or ' 발동' in key or ':' in key and key.startswith(('self_','target_','allies_','enemies_')):
        continue
    impl_status[key]=status_cell

# Pattern aliases in the status doc.
def status_for_stat(stat: str | None) -> str:
    if not stat:
        return 'unknown'
    if stat in impl_status:
        return impl_status[stat]
    if stat.startswith('burst_stage_override:'):
        return '✅'
    if stat.startswith('sequential_damage:'):
        return '✅'
    if stat.startswith('bonus_damage:'):
        return '✅'
    if stat.startswith('armor_break_damage:'):
        return '✅'
    if stat.startswith('debuff_immune:'):
        return '✅'
    return 'unknown'

FAST_DIRECT_STATS = {
    'atk_pct','atk_caster_based_pct','atk_dmg_pct','crit_rate','normal_atk_crit_rate','crit_dmg',
    'normal_atk_dmg_pct','reload_speed_pct','charge_speed_pct','charge_dmg_pct','charge_dmg_mag_pct',
    'split_dmg_pct','received_dmg_pct','projectile_attachment_dmg_pct','projectile_explosion_dmg_pct',
    'max_ammo_pct','element_bonus_pct','ammo_charge_pct',
}
FAST_DIRECT_DAMAGE = {
    'damage','bonus_damage','burst_damage','split_damage','dot_damage',
    'projectile_attachment_damage','projectile_explosion_damage',
}

ARITHMETIC_STATS = {
    'atk_pct','atk_caster_based_pct','atk_from_hp_pct','def_pct','def_caster_based_pct',
    'crit_rate','normal_atk_crit_rate','crit_dmg','normal_atk_crit_dmg','core_dmg_pct','part_dmg_pct',
    'atk_dmg_pct','burst_dmg_pct','pierce_dmg_pct','dot_dmg_pct','split_dmg_pct','charge_dmg_pct',
    'charge_dmg_mag_pct','charge_dmg_per_max_ammo_pct','charge_speed_overflow_conversion_pct','sequential_dmg_pct','received_dmg_pct',
    'element_bonus_pct','normal_atk_dmg_pct','armor_break_dmg_pct','projectile_attachment_dmg_pct',
    'projectile_explosion_dmg_pct','accuracy_pct','mg_warmup_speed_pct','attack_speed_pct',
    'reload_speed_pct','charge_speed_pct','charge_speed_caster_based_pct','charge_time_flat',
    'max_ammo_pct','max_ammo_flat','pellet_count','pellet_count_fixed','pierce_enabled','armor_break_enabled',
    'element_code_override','dmg_scale_mag_pct','atk_buff_mag_pct','burst_dmg_aoe_pct','shield_dmg_pct',
    'element_received_dmg_pct','optimal_range_max_pct','optimal_range_min','optimal_range_max','optimal_range_dmg_pct',
    'projectile_dmg_pct','intercept_dmg_pct','explosion_range','pierce_range',
}
DAMAGE_STATS = {
    'damage','bonus_damage','burst_damage','split_damage','dot_damage','armor_break_damage','core_damage',
    'projectile_attachment_damage','projectile_explosion_damage','auto_damage','fixed_damage_from_dealt_pct',
}
TIMELINE_STATS = {
    'burst_cooldown_reduce','burst_cooldown','burst_reentry','fullburst_duration','force_reload','reload_time_fixed',
    'skill_cooldown_reduce_pct','skill_cooldown_pct','skill_cooldown','effect_interval','force_skill_use',
    'burst_charge_pct','burst_charge_speed_pct','infinite_ammo','max_ammo_infinite','squad_ammo_consume_as',
    'charge_time_fixed','charge_speed_buff_immune','charge_speed_debuff_immune','gauge_consume_as_ammo',
}
STATE_STATS = {
    'remove_named_buff','buff_stack_add','buff_stack_remove','buff_max_stack_add','buff_stack_init',
    'named_buff_duration_extend','trigger_count_reduce','persona_state','targeting_exclude','debuff_stack_add',
    'debuff_stack_remove','debuff_cleanse','debuff_immune','harmful_immune_count','possessed','lock_on','focus_fire',
    'gauge_charge_enabled','gauge_max_add','effect_target_count_add','effect_range_pct',
}
HP_STATS = {
    'heal_hp_pct','max_hp_pct','max_hp_only_pct','hp_caster_based_pct','hp_only_caster_based_pct','lifesteal_pct',
    'current_hp_reduce','heal_received_pct','outgoing_heal_pct','heal_given_pct','heal_equal_split','heal_split',
    'heal_overcharge_store','heal_overcharge_store_atk_pct','heal_overcharge_discharge','shield_from_max_hp_pct',
    'shared_shield_from_max_hp_pct','shield_heal_from_caster_max_hp_pct','next_shield_hp_pct','shield_restore_pct',
    'revive','undying','invincible','shield_invincible','indomitable','decoy','decoy_from_max_hp_pct',
    'decoy_heal_from_caster_max_hp_pct','hp_copy','cover_heal_pct','cover_revive','cover_hp_caster_based_pct',
    'cover_heal_from_caster_max_hp_pct','cover_max_hp_caster_based_pct','cover_received_dmg_split','received_dmg_split',
    'cover_def_pct','cover_disabled','heal_given_pct','shield_dmg_pct','shield_heal_from_caster_max_hp_pct',
}
CONTROL_STATS = {'taunt','stun','stun_immune','stealth','enemy_movement_disable','force_move','targeting_exclude'}
SPECIAL_STATS = {
    'damage_accumulate','damage_accumulate_ratio_pct','accumulate_max_scale_pct','atk_copy','heal_overcharge_store_atk_pct',
    'heal_overcharge_discharge','feather_refresh','fixed_damage_from_dealt_pct','squad_ammo_consume_as',
}
STATEFUL_GENERIC_SPECIAL = {'damage_accumulate','damage_accumulate_ratio_pct','fixed_damage_from_dealt_pct'}


def stat_subsystem(stat: str | None, typ: str) -> str:
    if not stat:
        return 'state' if typ == 'buff' else ('weapon_change' if typ == 'weapon_change' else 'special')
    status=status_for_stat(stat)
    if '❌' in status or '🚫' in status:
        return 'moris_nop'
    if typ == 'weapon_change':
        return 'weapon_change'
    if typ == 'damage' or stat in DAMAGE_STATS or stat.startswith(('sequential_damage:','bonus_damage:','armor_break_damage:')):
        if stat in SPECIAL_STATS or stat == 'fixed_damage_from_dealt_pct':
            return 'special'
        return 'damage'
    if stat.startswith('burst_stage_override:'):
        return 'timeline'
    if stat.startswith('debuff_immune:'):
        return 'state'
    if stat.startswith('gauge_') or stat in {'gauge_consume'}:
        return 'state'
    if stat in STATE_STATS:
        return 'state'
    if stat in HP_STATS or stat.startswith(('heal_','cover_','shield_','decoy_')):
        return 'hp_shield'
    if stat in TIMELINE_STATS:
        return 'timeline'
    if stat in CONTROL_STATS:
        return 'control'
    if stat in SPECIAL_STATS or 'accumulate' in stat or stat in {'feather_refresh','possessed'}:
        return 'special'
    if stat in ARITHMETIC_STATS:
        return 'arithmetic'
    if stat in {'ammo_charge_pct','ammo_charge_flat'}:
        return 'weapon_runtime'
    if stat in {'explosion_range','pierce_range','optimal_range_min','optimal_range_max','optimal_range_max_pct'}:
        return 'moris_nop'
    return 'unknown'


def timing_family(t: str) -> str:
    if t in {'battle_start','passive'}: return 'lifecycle'
    if t.startswith(('burst_cast','conditional_burst_cast_count','burst_enter:','full_burst_start','full_burst_end','squad_burst_cast')): return 'burst'
    if t.startswith(('hit_count','conditional_hit_count','full_charge','core_hit','crit_hit','pellet_hit','multi_hit','non_full_charge_hit','charge_hold','part_hit_count','body_hit_count','weapon_hit')) or t in {'on_attack','last_bullet','last_bullet_fire'}: return 'weapon_hit'
    if t.startswith('every:'): return 'periodic'
    if t.startswith('stack_reach:'): return 'state_counter'
    if t.startswith(('hp_below','received_hit','fatal_hit')): return 'incoming_hp'
    if t.startswith('squad_ammo_consume:'): return 'ammo'
    if t.startswith('event:'): return 'named_event'
    if t in {'enemy_death','squad_part_break','squad_part_hit','feather_tick'}: return 'encounter_event'
    return 'custom'


def condition_family(c: str) -> str:
    if c.startswith(('self_state:','not_self_state:','target_state:','not_target_state:')): return 'named_state'
    if c.startswith(('self_stack_above:','target_stack_above:')): return 'stack'
    if c.startswith(('gauge_above:','gauge_below:','gauge_eq:','gauge_mod:')): return 'gauge'
    if c.startswith(('self_hp_','ally_hp_')): return 'hp'
    if c.startswith('prob:') or c == 'trigger_hit_crit': return 'rng'
    if c in {'during_full_burst','not_during_full_burst','during_charge','burst_casted','burst_not_casted','back_row'}: return 'simple_runtime'
    if c.startswith(('target_code:','enemy_count_')) or c == 'core_hit': return 'enemy'
    if c in {'no_burst1_ally','has_burst1_ally','no_defender_ally','has_defender_ally','squad_ally_exists'}: return 'roster'
    if 'cover' in c: return 'cover'
    if c in {'during_shield','target_stunned'}: return 'control_hp'
    if c.startswith('self_stat_above:'): return 'derived_stat'
    if c == 'focusing': return 'special'
    return 'custom'


def target_family(t) -> str:
    if isinstance(t,list): return 'composite'
    if not isinstance(t,str): return 'custom'
    if t in {'self','all_allies','all_allies_excl_self'} or t.startswith(('allies:','allies_adjacent:')): return 'ally_static'
    if t.startswith(('allies_weapon:','allies_weapon_excl_self:','allies_class:','allies_code:','allies_code_weapon:','allies_code_weapon_leftmost:','allies_burst3','allies_same_squad','allies_named:','all_allies_burst_','allies_burst_casted_','allies_top_base_charge_time:')): return 'ally_filter_static'
    if t.startswith(('allies_top_atk','allies_lowest_hp','allies_top_def','allies_lowest_atk_burst3','allies_below_def','allies_weapon_top_atk')): return 'ally_dynamic_rank'
    if t.startswith(('allies_with_buff:','allies_without_buff:','allies_burst3_persona','allies_random_debuffed:')): return 'ally_state_filter'
    if t.startswith('allies_random:'): return 'ally_random'
    if 'cover' in t or t in {'all_projectiles'}: return 'unsupported_model'
    if t.startswith(('enemy','enemies','target','same_target','all_enemies')) or t in {'target','enemy','same_target','target_body','target_and_nearby'}: return 'enemy_singleton'
    if t in skills: return 'named_character'
    return 'custom'


def readiness(e: dict) -> tuple[str,list[str]]:
    typ=e.get('type','')
    stat=e.get('stat')
    sub=stat_subsystem(stat,typ)
    reasons=[]
    if sub == 'moris_nop':
        return 'N', [f'moris:{status_for_stat(stat)}']
    tfams={timing_family(t) for t in (e.get('trigger') or {}).get('timing',[])}
    cfams={condition_family(c) for c in (e.get('trigger') or {}).get('condition',[])}
    targ=target_family(e.get('target'))
    scaling=e.get('scaling')
    advanced_fields=set(e)-{'source','type','name','trigger','target','stat','polarity','values','fixed_value','duration','max_stack','max_trigger','scaling','scaling_ref','trigger_values','tick_interval','note','favorite'}

    if sub == 'unknown': reasons.append(f'unknown_stat:{stat}')
    if 'custom' in tfams: reasons.append('custom_timing')
    if 'custom' in cfams: reasons.append('custom_condition')
    if targ in {'custom','unsupported_model'}: reasons.append(f'target:{targ}')
    if advanced_fields: reasons.append('fields:'+','.join(sorted(advanced_fields)))

    direct = (
        (stat in FAST_DIRECT_STATS or (typ=='damage' and (stat in FAST_DIRECT_DAMAGE or stat.startswith('sequential_damage:'))))
        and tfams <= {'lifecycle','burst','weapon_hit','periodic'}
        and cfams <= {'simple_runtime','enemy','roster'}
        and targ in {'ally_static','ally_filter_static','enemy_singleton','named_character'}
        and not scaling and not advanced_fields
    )
    if direct:
        return 'A', []

    if sub in {'arithmetic','damage','weapon_runtime','control'}:
        if tfams <= {'lifecycle','burst','weapon_hit','periodic','named_event','encounter_event','ammo'} \
           and cfams <= {'simple_runtime','enemy','roster','rng','derived_stat'} \
           and targ in {'ally_static','ally_filter_static','ally_dynamic_rank','ally_random','enemy_singleton','named_character','composite'} \
           and scaling in {None,'max_hp','caster_max_hp','caster_final_atk'} \
           and not any(r.startswith(('unknown_stat','custom_','target:','fields:')) for r in reasons):
            return 'B', []

    if sub in {'state','hp_shield','timeline','weapon_change','weapon_runtime','arithmetic','damage','control'} or stat in STATEFUL_GENERIC_SPECIAL:
        if 'custom' not in tfams and 'custom' not in cfams and targ != 'custom':
            if not advanced_fields - {
                'duration_bullets','damage_coeff','gauge_max','full_charge_mult','activation_limit','tick_start',
                'target_code','event_scope','consume_next_shield','scaling_hp_pct','hits_parts','target_skill',
                'first_damage_coeff','release_stat','release_target','post_fire_delay','cover_during_delay','toggle',
                'max_ammo_buff_applies','core_dmg_mult','ramp_interval','pellets','fire_rate','max_ammo_gauge_ref',
                'target_effect','gauge_id','gauge_max','duration_values','skill_damage','damage_formula','first_damage_coeff',
                'charge_time','max_ammo','weapon_type','accumulate_ratio_pct'
            }:
                return 'C', reasons

    return 'D', reasons or [f'subsystem:{sub}',f'target:{targ}',f'timing:{sorted(tfams)}',f'condition:{sorted(cfams)}']


def build_inventory(*, write_outputs: bool = True) -> dict:
    rows=[]
    read_counter=Counter(); subsystem_counter=Counter(); char_level={}; blocker_stats=Counter(); blocker_reasons=Counter()
    for ch, effs in skills.items():
        levels=[]
        for i,e in enumerate(effs):
            r, reasons=readiness(e)
            sub=stat_subsystem(e.get('stat'),e.get('type',''))
            read_counter[r]+=1; subsystem_counter[sub]+=1; levels.append(r)
            if r=='D':
                blocker_stats[e.get('stat','<none>')]+=1
                blocker_reasons.update(reasons)
            rows.append({
                'character':ch,'index':i,'source':e.get('source'),'name':e.get('name'),'type':e.get('type'),
                'stat':e.get('stat'),'moris_status':status_for_stat(e.get('stat')),'subsystem':sub,
                'readiness':r,'timing_families':sorted({timing_family(t) for t in (e.get('trigger') or {}).get('timing',[])}),
                'condition_families':sorted({condition_family(c) for c in (e.get('trigger') or {}).get('condition',[])}),
                'target_family':target_family(e.get('target')),'scaling':e.get('scaling'),'reasons':reasons,
            })
        order={'N':0,'A':0,'B':1,'C':2,'D':3}
        worst=max((order[x] for x in levels),default=0)
        char_level[ch]=worst

    stage_counts=Counter(char_level.values())
    cum={stage:sum(v for lvl,v in stage_counts.items() if lvl<=stage) for stage in range(4)}

    summary={
        'characters':len(skills), 'effects':len(rows), 'effect_readiness':dict(read_counter),
        'subsystems':dict(subsystem_counter), 'character_worst_stage_counts':dict(stage_counts),
        'cumulative_character_coverage':cum,
        'top_D_stats':blocker_stats.most_common(30), 'top_D_reasons':blocker_reasons.most_common(30),
    }
    if write_outputs:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT/'inventory.json').write_text(json.dumps({'summary': summary, 'effects': rows}, ensure_ascii=False, indent=2), encoding='utf-8')

    lines=[]
    lines.append('# Fast Engine feasibility inventory')
    lines.append('')
    lines.append(f'- Moris parsed characters: **{len(skills)}**')
    lines.append(f'- Parsed effects: **{len(rows)}**')
    lines.append('')
    lines.append('## Effect readiness')
    lines.append('')
    for k in ['N','A','B','C','D']:
        n=read_counter[k]; lines.append(f'- {k}: {n} ({n/len(rows)*100:.1f}%)')
    lines.append('')
    lines.append('N = Moris itself is NOP/unimplemented for score parity; A = existing fast core; B = generic primitive; C = stateful generic subsystem; D = special/fallback.')
    lines.append('')
    lines.append('## Cumulative character coverage')
    lines.append('')
    for stage,label in [(0,'N+A only'),(1,'through B'),(2,'through C'),(3,'all incl. D')]:
        n=cum[stage]; lines.append(f'- {label}: {n}/{len(skills)} ({n/len(skills)*100:.1f}%)')
    lines.append('')
    lines.append('## Subsystems by effect count')
    lines.append('')
    for k,v in subsystem_counter.most_common(): lines.append(f'- {k}: {v}')
    lines.append('')
    lines.append('## Top D blockers')
    lines.append('')
    for k,v in blocker_stats.most_common(25): lines.append(f'- `{k}`: {v}')
    lines.append('')
    lines.append('## Top D reasons')
    lines.append('')
    for k,v in blocker_reasons.most_common(25): lines.append(f'- `{k}`: {v}')
    if write_outputs:
        (OUT/'inventory.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return {'summary': summary, 'effects': rows}


def main() -> None:
    result = build_inventory(write_outputs=True)
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
