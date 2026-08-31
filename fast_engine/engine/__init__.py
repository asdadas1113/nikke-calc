"""Greenfield score-oriented Fast Engine runtime.

Moris owns input assembly and final authority. This package owns the cheap
continuous-time ranking runtime used between those two boundaries.
"""

from .compiler import compile_moris_squad
from .model import CompiledCharacter, CompiledSquad, EnemyStaticProfile, FastScore
from .scheduler import EventKind, EventScheduler, ScheduledEvent

__all__ = [
    "CompiledCharacter",
    "CompiledSquad",
    "EnemyStaticProfile",
    "EventKind",
    "EventScheduler",
    "FastScore",
    "ScheduledEvent",
    "compile_moris_squad",
]
