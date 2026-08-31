"""Cheap hard constraints applied before any expensive simulation."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

TeamValidator = Callable[[tuple[str, ...]], bool]
_BURST_STAGES = ("1", "2", "3")
_BURST_STAGE_BITS = {"1": 1, "2": 2, "3": 4}
_ALL_BURST_STAGE_BITS = 1 | 2 | 4


@dataclass(frozen=True)
class BurstMetadata:
    """Static burst metadata plus stages a runtime override may reach."""

    stage: str
    cooldown: float | None = None
    dynamic_stages: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class BurstStructureReport:
    """Conservative pre-simulation burst-structure verdict.

    `missing_stages` are definitely absent in auto burst mode and can be hard
    pruned. `uncertain_stages` are absent statically but a runtime burst-stage
    override may reach them, so they deliberately remain legal for full Moris
    evaluation.
    """

    eligible_by_stage: Mapping[str, tuple[str, ...]]
    min_cooldown_by_stage: Mapping[str, float | None]
    missing_stages: tuple[str, ...]
    uncertain_stages: tuple[str, ...]
    deferred_reason: str | None = None

    @property
    def legal(self) -> bool:
        return not self.missing_stages

    @property
    def fully_resolved(self) -> bool:
        return self.deferred_reason is None and not self.uncertain_stages


class BurstStructureValidator:
    """Mirror only Moris burst facts that are safe to hard-prune cheaply.

    Moris permanently blocks a burst stage when that stage has no candidates.
    A candidate that is merely on cooldown makes the engine wait, so cooldown
    values are exposed as diagnostics and are *not* legality thresholds.

    Dynamic stage overrides and explicit `burst_sequence` are intentionally
    conservative: when cheap static inspection cannot prove a block, the team
    survives pruning and the simulator remains the source of truth.
    """

    def __init__(
        self,
        metadata: Mapping[str, BurstMetadata],
        *,
        stage_overrides: Mapping[str, str] | None = None,
        no_burst_names: Iterable[str] = (),
        explicit_sequence: bool = False,
    ) -> None:
        self._metadata = dict(metadata)
        self._stage_overrides = {
            name: str(stage) for name, stage in (stage_overrides or {}).items()
        }
        self._no_burst_names = frozenset(no_burst_names)
        self._explicit_sequence = explicit_sequence
        # Candidate allocation beams repeatedly ask the same structural question
        # against a small set of full/residual rosters. Cache only static burst
        # provider metadata for those roster tuples; no damage/search score lives
        # here. Values are: roster_set, name->possible-stage-mask, mask counts,
        # and names whose metadata is unknown (which remain fail-open).
        self._completion_roster_cache: dict[
            tuple[str, ...],
            tuple[
                frozenset[str],
                dict[str, int | None],
                tuple[int, ...],
                frozenset[str],
            ],
        ] = {}

    @classmethod
    def from_moris(
        cls,
        *,
        characters: Mapping[str, object] | None = None,
        config: Mapping[str, object] | None = None,
    ) -> "BurstStructureValidator":
        """Load the same parsed burst metadata used by Moris.

        This adapter reads Moris data but does not import calculator internals or
        duplicate its combat loop. Character-level `burst_stage` overrides and
        auto-mode `no_burst_char(s)` follow BurstController's input semantics.
        """

        from context import spec as char_spec

        root = Path(char_spec.__file__).resolve().parent.parent
        with open(root / "data" / "parsed_nikke.json", encoding="utf-8") as handle:
            parsed_nikke = json.load(handle)
        with open(root / "data" / "parsed_skills.json", encoding="utf-8") as handle:
            parsed_skills = json.load(handle)

        metadata: dict[str, BurstMetadata] = {}
        for name, row in parsed_nikke.items():
            dynamic_stages: set[str] = set()
            for effect in parsed_skills.get(name, ()):
                stat = str(effect.get("stat") or "")
                if not stat.startswith("burst_stage_override:"):
                    continue
                target = stat.split(":", 1)[1]
                if target.startswith("reenter"):
                    target = target[len("reenter") :]
                if target == "A":
                    dynamic_stages.update(_BURST_STAGES)
                elif target in _BURST_STAGES:
                    dynamic_stages.add(target)

            raw_cd = row.get("burst_cooldown")
            cooldown = float(raw_cd) if raw_cd is not None else None
            metadata[name] = BurstMetadata(
                stage=char_spec.burst_stage(name),
                cooldown=cooldown,
                dynamic_stages=frozenset(dynamic_stages),
            )

        char_input = characters or {}
        stage_overrides = {
            name: str(value["burst_stage"])
            for name, value in char_input.items()
            if isinstance(value, Mapping) and value.get("burst_stage")
        }

        cfg = config or {}
        explicit_sequence = cfg.get("burst_sequence") is not None
        no_burst_names: set[str] = set()
        if not explicit_sequence:
            single = cfg.get("no_burst_char")
            if single:
                no_burst_names.add(str(single))
            many = cfg.get("no_burst_chars") or ()
            no_burst_names.update(str(name) for name in many)

        return cls(
            metadata,
            stage_overrides=stage_overrides,
            no_burst_names=no_burst_names,
            explicit_sequence=explicit_sequence,
        )

    def inspect(self, members: Sequence[str]) -> BurstStructureReport:
        team = tuple(members)
        for name in team:
            if name not in self._metadata:
                raise ValueError(f"{name}: burst metadata is unavailable")

        if self._explicit_sequence:
            return BurstStructureReport(
                eligible_by_stage={stage: () for stage in _BURST_STAGES},
                min_cooldown_by_stage={stage: None for stage in _BURST_STAGES},
                missing_stages=(),
                uncertain_stages=(),
                deferred_reason="explicit burst_sequence requires simulator validation",
            )

        active_names = [name for name in team if name not in self._no_burst_names]
        eligible: dict[str, list[str]] = {stage: [] for stage in _BURST_STAGES}
        for name in active_names:
            meta = self._metadata[name]
            stage = self._stage_overrides.get(name, meta.stage)
            if stage == "A":
                for target in _BURST_STAGES:
                    eligible[target].append(name)
            elif stage in eligible:
                eligible[stage].append(name)

        statically_missing = [stage for stage in _BURST_STAGES if not eligible[stage]]
        dynamic_possible = {
            stage
            for name in active_names
            for stage in self._metadata[name].dynamic_stages
        }
        uncertain = tuple(
            stage for stage in statically_missing if stage in dynamic_possible
        )
        definitely_missing = tuple(
            stage for stage in statically_missing if stage not in dynamic_possible
        )

        min_cooldown: dict[str, float | None] = {}
        for stage, names in eligible.items():
            values = [
                self._metadata[name].cooldown
                for name in names
                if self._metadata[name].cooldown is not None
            ]
            min_cooldown[stage] = min(values) if values else None

        return BurstStructureReport(
            eligible_by_stage={stage: tuple(names) for stage, names in eligible.items()},
            min_cooldown_by_stage=min_cooldown,
            missing_stages=definitely_missing,
            uncertain_stages=uncertain,
        )

    def _possible_stages_for(self, name: str) -> frozenset[str] | None:
        """Return stages this member might satisfy; None means fail-open unknown."""

        meta = self._metadata.get(name)
        if meta is None:
            return None
        if name in self._no_burst_names:
            return frozenset()

        stage = self._stage_overrides.get(name, meta.stage)
        possible: set[str] = set(meta.dynamic_stages)
        if stage == "A":
            possible.update(_BURST_STAGES)
        elif stage in _BURST_STAGES:
            possible.add(stage)
        return frozenset(possible)

    @staticmethod
    def _stage_mask(stages: Iterable[str]) -> int:
        mask = 0
        for stage in stages:
            mask |= _BURST_STAGE_BITS.get(stage, 0)
        return mask

    def _completion_roster_profile(
        self,
        roster: tuple[str, ...],
    ) -> tuple[
        frozenset[str],
        dict[str, int | None],
        tuple[int, ...],
        frozenset[str],
    ]:
        cached = self._completion_roster_cache.get(roster)
        if cached is not None:
            return cached

        roster_set = frozenset(roster)
        if len(roster_set) != len(roster):
            raise ValueError("available_roster must contain unique members")

        masks: dict[str, int | None] = {}
        counts = [0] * (_ALL_BURST_STAGE_BITS + 1)
        unknown: set[str] = set()
        for name in roster:
            possible = self._possible_stages_for(name)
            if possible is None:
                masks[name] = None
                unknown.add(name)
                continue
            mask = self._stage_mask(possible)
            masks[name] = mask
            counts[mask] += 1

        value = (
            roster_set,
            masks,
            tuple(counts),
            frozenset(unknown),
        )
        self._completion_roster_cache[roster] = value
        return value

    def can_complete(
        self,
        members: Sequence[str],
        available_roster: Sequence[str],
        *,
        team_size: int,
    ) -> bool:
        """Whether a partial membership can still satisfy hard burst structure.

        This is a simulation-free *impossibility* test for candidate beams. It is
        deliberately optimistic: dynamic stage possibilities are treated as
        available and any unknown metadata fails open. Therefore False means the
        remaining slots provably cannot cover every required auto-burst stage;
        True does not claim the completed team will be strong or even ultimately
        legal under other constraints.

        Only three burst stages exist. A cached roster profile reduces the
        repeated question to the selected members plus an 8-state minimum-provider
        DP; it does not rescan a 100+ character roster for every beam partial.
        """

        partial = tuple(str(name) for name in members)
        roster = tuple(str(name) for name in available_roster)
        if team_size <= 0:
            raise ValueError("team_size must be positive")

        selected = set(partial)
        if len(partial) != len(selected) or len(partial) > team_size:
            return False

        roster_set, masks, base_counts, unknown_names = self._completion_roster_profile(
            roster
        )
        if not selected.issubset(roster_set):
            raise ValueError("partial members must belong to available_roster")
        if len(roster) < team_size:
            return False
        if self._explicit_sequence:
            return True

        counts = list(base_counts)
        covered_mask = 0
        for name in partial:
            mask = masks[name]
            if mask is None:
                return True
            covered_mask |= mask
            counts[mask] -= 1

        missing_mask = _ALL_BURST_STAGE_BITS & ~covered_mask
        if missing_mask == 0:
            return True

        remaining_slots = team_size - len(partial)
        if remaining_slots <= 0:
            return False

        # Any unselected unknown character might supply a missing stage, so this
        # hard-only validator must fail open while there is a slot for it.
        if unknown_names - selected:
            return True

        # More than one remaining character with the same stage mask can never
        # improve coverage of the three required stages, so mask presence is
        # sufficient. dp[mask] is the fewest distinct characters needed to supply
        # that subset of the currently missing stages.
        unreachable = team_size + 1
        dp = [unreachable] * (_ALL_BURST_STAGE_BITS + 1)
        dp[0] = 0
        for provider_mask in range(1, _ALL_BURST_STAGE_BITS + 1):
            if counts[provider_mask] <= 0:
                continue
            relevant_mask = provider_mask & missing_mask
            if relevant_mask == 0:
                continue
            previous = tuple(dp)
            for supplied_mask, count in enumerate(previous):
                if count >= unreachable:
                    continue
                combined = supplied_mask | relevant_mask
                candidate_count = count + 1
                if candidate_count < dp[combined]:
                    dp[combined] = candidate_count
            if dp[missing_mask] <= remaining_slots:
                return True

        return dp[missing_mask] <= remaining_slots

    def __call__(self, members: tuple[str, ...]) -> bool:
        return self.inspect(members).legal


@dataclass(frozen=True)
class TeamRequirement:
    """Named generic team-level hard requirement.

    The optimizer intentionally does not know what the requirement represents.
    A later policy may use this hook for healing, shields, mitigation, boss-specific
    survival routes, or any other condition without teaching candidate discovery,
    marginal measurement, or refinement about those concepts.
    """

    label: str
    validator: TeamValidator

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("team requirement label must be non-empty")

    def __call__(self, members: tuple[str, ...]) -> bool:
        return bool(self.validator(tuple(members)))


@dataclass(frozen=True)
class ConstraintSet:
    """Optimizer-side hard constraints.

    Moris-backed validators stay pluggable so the calculator remains the source
    of truth. Only conditions proven impossible should return False here.

    `requirements` is the named extension point for future policy constraints.
    It is deliberately domain-agnostic: no healer/sustain semantics live in the
    optimizer core. The ConstraintSet itself is callable so every search stage
    can receive the same legality object as its existing ``legal(team)`` hook.
    """

    team_size: int = 5
    include: frozenset[str] = field(default_factory=frozenset)
    exclude: frozenset[str] = field(default_factory=frozenset)
    validators: tuple[TeamValidator, ...] = ()
    requirements: tuple[TeamRequirement, ...] = ()

    def __post_init__(self) -> None:
        labels = [requirement.label for requirement in self.requirements]
        if len(labels) != len(set(labels)):
            raise ValueError("team requirement labels must be unique")

    def validate_team(self, members: Sequence[str]) -> bool:
        team = tuple(members)
        member_set = set(team)
        if len(team) != self.team_size or len(member_set) != len(team):
            return False
        if not self.include.issubset(member_set):
            return False
        if self.exclude.intersection(member_set):
            return False
        if not all(validator(team) for validator in self.validators):
            return False
        return all(requirement(team) for requirement in self.requirements)

    def failed_requirements(self, members: Sequence[str]) -> tuple[str, ...]:
        """Return labels of named policy requirements rejected by this team.

        Built-in shape/include/exclude/anonymous-validator failures are not mixed
        into this diagnostic. This keeps future UI explanations stable without
        forcing policy semantics into the optimizer core.
        """

        team = tuple(members)
        return tuple(
            requirement.label
            for requirement in self.requirements
            if not requirement(team)
        )

    def __call__(self, members: tuple[str, ...]) -> bool:
        return self.validate_team(members)


def teams_are_disjoint(teams: Iterable[Sequence[str]]) -> bool:
    used: set[str] = set()
    for team in teams:
        ordered = tuple(team)
        members = set(ordered)
        if len(members) != len(ordered) or used.intersection(members):
            return False
        used.update(members)
    return True
