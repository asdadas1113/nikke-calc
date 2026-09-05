from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

p=ROOT/'fast_engine/engine/score.py'
s=p.read_text(encoding='utf-8')
old='''    if any(\n        (other.stat or \"\").startswith(\"burst_stage_override:reenter\")\n        for other in squad.effects\n    ):\n        return False\n'''
new='''    if any(\n        (other.stat or \"\").startswith(\"burst_stage_override:reenter\")\n        and not _roster_static_burst1_condition_unreachable(squad, other)\n        for other in squad.effects\n    ):\n        return False\n'''
assert old in s
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

p=ROOT/'fast_engine/tests/test_damage_maid_mast_stack_mutation.py'
s=p.read_text(encoding='utf-8')
old='''                hangover = self._effect(compiled, '마스트 : 로망틱 메이드', '숙취')\n                self.assertTrue(\n                    _full_burst_end_stack_condition_unreachable_after_owned_decrement(\n                        compiled, remover\n                    )\n                )\n                self.assertTrue(\n                    _full_burst_end_stack_condition_unreachable_after_owned_decrement(\n                        compiled, hangover\n                    )\n                )\n'''
new='''                self.assertTrue(\n                    _full_burst_end_stack_condition_unreachable_after_owned_decrement(\n                        compiled, remover\n                    )\n                )\n'''
assert old in s
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('tightened Maid Mast proof around reachable re-entry only')
