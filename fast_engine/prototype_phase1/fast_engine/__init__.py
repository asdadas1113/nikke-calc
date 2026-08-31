"""Optimizer-oriented Fast Engine prototype built from the Moris skill DSL."""

from .ir import CharacterIR, EffectIR, TriggerIR, compile_catalog, compile_effect
from .routing import FastSupportProfile, RouteDecision, route_team

__all__ = [
    'CharacterIR', 'EffectIR', 'TriggerIR', 'compile_catalog', 'compile_effect',
    'FastSupportProfile', 'RouteDecision', 'route_team',
]
