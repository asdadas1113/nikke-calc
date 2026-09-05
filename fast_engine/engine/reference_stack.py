from __future__ import annotations

def finite_reference_stack_capture_shape(effect) -> bool:
    ref = effect.parameters.get("scaling_ref")
    duration = effect.duration
    max_stack = effect.max_stack if effect.max_stack is not None else 1.0
    return (
        effect.effect_type == "buff"
        and effect.parameters.get("scaling") == "stack_count"
        and isinstance(ref, str) and bool(ref)
        and set(effect.parameters) == {"scaling", "scaling_ref"}
        and duration is not None and float(duration) > 0.0
        and float(max_stack) == 1.0
        and effect.max_trigger is None and effect.tick_interval is None
    )
