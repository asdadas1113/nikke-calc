from pathlib import Path
import sys, inspect
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine import score
from fast_engine.engine.dynamic_weapon import MultiSignalChargeCadenceRuntime
from fast_engine.engine.dynamic_reload import DynamicRapidReloadRuntime

for fn in (
    TriggerDispatcher._temporary_self_charge_weapon_change_shape_supported,
    TriggerDispatcher._temporary_self_rapid_weapon_change_shape_supported,
    TriggerDispatcher._temporary_self_rapid_to_single_charge_weapon_change_shape_supported,
    TriggerDispatcher.is_executable_effect,
    TriggerDispatcher.is_runtime_executable_effect,
    score._temporary_self_charge_weapon_change_score_supported,
    score._dynamic_charge_score_actors,
    score._dynamic_rapid_reload_score_actors,
):
    print('\n###',fn.__qualname__)
    print(inspect.getsource(fn))
