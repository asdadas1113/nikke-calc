from pathlib import Path
import sys, inspect
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine import score
from fast_engine.engine.dynamic_weapon import MultiSignalChargeCadenceRuntime
from fast_engine.engine.dynamic_reload import DynamicRapidReloadRuntime
from fast_engine.engine.weapon import DynamicChargeCadenceRuntime

for fn in (
    TriggerDispatcher._temporary_self_charge_weapon_change_runtime_supported,
    TriggerDispatcher._temporary_self_rapid_weapon_change_runtime_supported,
    TriggerDispatcher.dispatch,
    MultiSignalChargeCadenceRuntime.__init__,
    MultiSignalChargeCadenceRuntime.attach_score_shot_sink,
    MultiSignalChargeCadenceRuntime.attach_score_block_sink,
    MultiSignalChargeCadenceRuntime.sync,
    DynamicRapidReloadRuntime.attach_score_sink,
    DynamicRapidReloadRuntime.attach_effective_weapon,
    DynamicRapidReloadRuntime.sync,
    DynamicRapidReloadRuntime.handle_boundary,
    DynamicChargeCadenceRuntime.sync,
    score._temporary_self_rapid_weapon_change_score_supported,
    score._actor_has_unhandled_count_event,
    score._dynamic_charge_score_actors,
    score._dynamic_rapid_reload_score_actors,
):
    print('\n###',fn.__qualname__)
    print(inspect.getsource(fn))
