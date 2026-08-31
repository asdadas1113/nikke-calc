"""Strict Solo Raid usage bounds from a declared ranking-coverage contract.

This module is the Cold-safe counterpart to the descriptive ``meta_usage``
normalizer.  It never assumes that an omitted ranking row means zero usage.
Instead a caller declares the cohort shape that the external source is expected
to cover (servers, rank interval, team count, team size), and every missing or
unusable player slot remains adversarial uncertainty.

For one character in one season:

    lower = observed_appearances / expected_player_slots
    upper = (observed_appearances + uncertain_player_slots) / expected_player_slots

The upper bound assumes every uncertain player used the character.  Therefore a
LOW decision based on ``upper <= cutoff`` is conservative even when a small
number of source rows are absent.  No popularity score or Moris score exists in
this module.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RankingCoverageContract:
    """Explicit expected shape of one external Solo Raid ranking cohort."""

    servers: tuple[str, ...]
    rank_start: int
    rank_end: int
    team_count: int
    team_size: int
    source: str

    def __post_init__(self) -> None:
        if not self.servers or len(set(self.servers)) != len(self.servers):
            raise ValueError("coverage contract servers must be unique and non-empty")
        if any(not str(server).strip() for server in self.servers):
            raise ValueError("coverage contract server names must be non-empty")
        if self.rank_start <= 0 or self.rank_end < self.rank_start:
            raise ValueError("coverage contract rank range is invalid")
        if self.team_count <= 0 or self.team_size <= 0:
            raise ValueError("coverage contract team_count/team_size must be positive")
        if not self.source.strip():
            raise ValueError("coverage contract source must be non-empty")

    @property
    def ranks(self) -> tuple[int, ...]:
        return tuple(range(self.rank_start, self.rank_end + 1))

    @property
    def expected_player_slots(self) -> int:
        return len(self.servers) * len(self.ranks)

    @property
    def expected_slots(self) -> frozenset[tuple[str, int]]:
        return frozenset((server, rank) for server in self.servers for rank in self.ranks)


@dataclass(frozen=True)
class BoundedSeasonUsageObservation:
    character: str
    raid: int
    expected_player_slots: int
    observed_appearances: int
    uncertain_player_slots: int
    source_character_known: bool

    @property
    def lower_fraction(self) -> float | None:
        if not self.source_character_known or self.expected_player_slots <= 0:
            return None
        return self.observed_appearances / self.expected_player_slots

    @property
    def upper_fraction(self) -> float | None:
        if not self.source_character_known or self.expected_player_slots <= 0:
            return None
        possible = min(
            self.expected_player_slots,
            self.observed_appearances + self.uncertain_player_slots,
        )
        return possible / self.expected_player_slots

    @property
    def exact(self) -> bool:
        return self.source_character_known and self.uncertain_player_slots == 0


@dataclass(frozen=True)
class CertifiedEnikkSeasonUsageSnapshot:
    """One SRRankings season certified against an explicit cohort contract."""

    raid: int
    boss: str | None
    contract: RankingCoverageContract
    observed_complete_player_slots: int
    missing_player_slots: int
    malformed_player_slots: int
    mapping_uncertain_player_slots: int
    player_appearances: Mapping[str, int]
    mapped_characters: frozenset[str]
    unknown_external_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.raid <= 0:
            raise ValueError("raid must be positive")
        counts = (
            self.observed_complete_player_slots,
            self.missing_player_slots,
            self.malformed_player_slots,
            self.mapping_uncertain_player_slots,
        )
        if any(value < 0 for value in counts):
            raise ValueError("coverage counts must be non-negative")
        if (
            self.observed_complete_player_slots
            + self.missing_player_slots
            + self.malformed_player_slots
            != self.contract.expected_player_slots
        ):
            raise ValueError(
                "complete + missing + malformed slots must equal expected_player_slots"
            )
        if self.mapping_uncertain_player_slots > self.observed_complete_player_slots:
            raise ValueError("mapping-uncertain slots cannot exceed complete rows")
        for name, count in self.player_appearances.items():
            if count < 0 or count > self.observed_complete_player_slots:
                raise ValueError(f"invalid appearance count for {name}: {count}")

    @property
    def expected_player_slots(self) -> int:
        return self.contract.expected_player_slots

    @property
    def uncertain_player_slots(self) -> int:
        # Mapping-uncertain rows are structurally present but may hide an
        # appearance of any canonical character whose absence is being tested.
        return (
            self.missing_player_slots
            + self.malformed_player_slots
            + self.mapping_uncertain_player_slots
        )

    @property
    def fully_complete(self) -> bool:
        return self.uncertain_player_slots == 0

    def observe(self, character: str) -> BoundedSeasonUsageObservation:
        name = str(character)
        return BoundedSeasonUsageObservation(
            character=name,
            raid=self.raid,
            expected_player_slots=self.expected_player_slots,
            observed_appearances=int(self.player_appearances.get(name, 0)),
            uncertain_player_slots=self.uncertain_player_slots,
            source_character_known=name in self.mapped_characters,
        )


@dataclass(frozen=True)
class BoundedCharacterUsageWindow:
    character: str
    requested_eligible_raids: tuple[int, ...]
    usable_raids: tuple[int, ...]
    uncertain_raids: tuple[int, ...]
    bounds: tuple[tuple[int, float, float], ...]
    peak_lower_usage: float | None
    peak_upper_usage: float | None

    @property
    def complete_for_requested_window(self) -> bool:
        return bool(self.requested_eligible_raids) and not self.uncertain_raids


def certify_enikk_rankings(
    raid: int,
    rankings: Iterable[Mapping[str, Any]],
    name_map: Mapping[str, str],
    *,
    contract: RankingCoverageContract,
    boss: str | None = None,
) -> CertifiedEnikkSeasonUsageSnapshot:
    """Validate SRRankings rows and retain missing/malformed slots as uncertainty.

    Duplicate server/rank slots, duplicate player ids, or rows outside the declared
    cohort are contract violations and raise.  A row inside the cohort but with an
    invalid 5x5 team shape is retained as one malformed/unknown player slot rather
    than silently contributing zero appearances.
    """

    if raid <= 0:
        raise ValueError("raid must be positive")
    mapped_characters = frozenset(str(name) for name in name_map.values())
    expected_slots = contract.expected_slots
    seen_slots: set[tuple[str, int]] = set()
    seen_players: set[str] = set()
    appearances: dict[str, int] = {}
    unknown_names: set[str] = set()
    malformed = 0
    mapping_uncertain = 0
    complete = 0

    for index, row in enumerate(rankings):
        if not isinstance(row, Mapping):
            raise ValueError("ranking rows must be mappings")
        server = str(row.get("server"))
        try:
            rank = int(row.get("rank"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"ranking row {index} lacks a valid rank") from exc
        slot = (server, rank)
        if slot not in expected_slots:
            raise ValueError(f"ranking row outside coverage contract: {slot}")
        if slot in seen_slots:
            raise ValueError(f"duplicate server/rank slot: {slot}")
        seen_slots.add(slot)

        player = row.get("playerid")
        if player is None or not str(player):
            raise ValueError(f"ranking row {index} lacks playerid")
        player_key = str(player)
        if player_key in seen_players:
            raise ValueError(f"duplicate playerid in ranking cohort: {player_key}")
        seen_players.add(player_key)

        teams = row.get("teams")
        structurally_valid = (
            isinstance(teams, Sequence)
            and not isinstance(teams, (str, bytes))
            and len(teams) == contract.team_count
        )
        raw_external: list[str] = []
        if structurally_valid:
            for team in teams:
                if not isinstance(team, Mapping):
                    structurally_valid = False
                    break
                chars = team.get("characters")
                if (
                    not isinstance(chars, Sequence)
                    or isinstance(chars, (str, bytes))
                    or len(chars) != contract.team_size
                ):
                    structurally_valid = False
                    break
                raw_external.extend(str(value) for value in chars)
        if structurally_valid and len(raw_external) != len(set(raw_external)):
            structurally_valid = False

        if not structurally_valid:
            malformed += 1
            continue

        complete += 1
        used_by_player: set[str] = set()
        row_has_unknown_mapping = False
        for external in raw_external:
            canonical = name_map.get(external)
            if canonical is None:
                unknown_names.add(external)
                row_has_unknown_mapping = True
                continue
            used_by_player.add(str(canonical))
        if row_has_unknown_mapping:
            mapping_uncertain += 1
        for name in used_by_player:
            appearances[name] = appearances.get(name, 0) + 1

    missing = len(expected_slots - seen_slots)
    return CertifiedEnikkSeasonUsageSnapshot(
        raid=raid,
        boss=boss,
        contract=contract,
        observed_complete_player_slots=complete,
        missing_player_slots=missing,
        malformed_player_slots=malformed,
        mapping_uncertain_player_slots=mapping_uncertain,
        player_appearances=dict(sorted(appearances.items())),
        mapped_characters=mapped_characters,
        unknown_external_names=tuple(sorted(unknown_names)),
    )


def aggregate_bounded_character_window(
    character: str,
    snapshots: Iterable[CertifiedEnikkSeasonUsageSnapshot],
    *,
    eligible_raids: Iterable[int],
) -> BoundedCharacterUsageWindow:
    """Aggregate conservative lower/upper usage bounds across requested seasons."""

    name = str(character)
    eligible = tuple(dict.fromkeys(int(raid) for raid in eligible_raids))
    if any(raid <= 0 for raid in eligible):
        raise ValueError("eligible raid numbers must be positive")

    by_raid: dict[int, CertifiedEnikkSeasonUsageSnapshot] = {}
    for snapshot in snapshots:
        if snapshot.raid in by_raid:
            raise ValueError(f"duplicate season snapshot: {snapshot.raid}")
        by_raid[snapshot.raid] = snapshot

    usable: list[int] = []
    uncertain: list[int] = []
    bounds: list[tuple[int, float, float]] = []
    for raid in eligible:
        snapshot = by_raid.get(raid)
        if snapshot is None:
            uncertain.append(raid)
            continue
        obs = snapshot.observe(name)
        lower = obs.lower_fraction
        upper = obs.upper_fraction
        if lower is None or upper is None:
            uncertain.append(raid)
            continue
        usable.append(raid)
        bounds.append((raid, lower, upper))

    lowers = [lower for _raid, lower, _upper in bounds]
    uppers = [upper for _raid, _lower, upper in bounds]
    return BoundedCharacterUsageWindow(
        character=name,
        requested_eligible_raids=eligible,
        usable_raids=tuple(usable),
        uncertain_raids=tuple(uncertain),
        bounds=tuple(bounds),
        peak_lower_usage=max(lowers) if lowers else None,
        peak_upper_usage=max(uppers) if uppers else None,
    )
