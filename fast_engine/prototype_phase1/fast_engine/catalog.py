from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .ir import CharacterIR, compile_catalog


@dataclass(frozen=True)
class FastCatalog:
    characters: tuple[CharacterIR, ...]

    @property
    def by_name(self) -> Mapping[str, CharacterIR]:
        return {c.name: c for c in self.characters}

    @classmethod
    def from_moris(cls, moris_root: Path) -> 'FastCatalog':
        return cls(compile_catalog(moris_root / 'data/parsed_skills.json'))
