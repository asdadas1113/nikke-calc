from __future__ import annotations
from pathlib import Path
import sys, inspect
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine import score
from fast_engine.engine.dynamic_weapon import MultiSignalChargeCadenceRuntime
from fast_engine.engine.weapon import DynamicChargeCadenceRuntime
from fast_engine.engine.burst_runtime import BurstRuntime

objs=[
    TriggerDispatcher._temporary_self_charge_weapon_change_shape_supported,
    TriggerDispatcher._temporary_self_rapid_weapon_change_shape_supported,
    TriggerDispatcher.is_executable_effect,
    score._temporary_self_charge_weapon_change_score_supported,
    score._temporary_self_rapid_weapon_change_score_supported,
    score._dynamic_charge_score_actors,
    score._dynamic_rapid_reload_score_actors,
    score.StaticNormalAttackObserver,
    DynamicChargeCadenceRuntime.start,
    DynamicChargeCadenceRuntime.sync,
    MultiSignalChargeCadenceRuntime.__init__,
    MultiSignalChargeCadenceRuntime.start,
    MultiSignalChargeCadenceRuntime.sync,
    BurstRuntime._sync_dynamic_weapons,
]
for obj in objs:
    print('\n###',obj.__qualname__,flush=True)
    print(inspect.getsource(obj),flush=True)
