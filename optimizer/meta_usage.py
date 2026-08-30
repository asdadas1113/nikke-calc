"""Threshold-free Solo Raid usage evidence for meta-guided search.

This module deliberately stops before deciding whether a character is
``low_usage``.  It turns a complete external ranking snapshot into per-character
appearance counts and can aggregate an explicitly eligible multi-season window.
The eventual low-usage cutoff, release/eligibility policy, and recency rule are
separate benchmarked policy.

A character is counted at most once per ranked player.  Solo Raid normally does
not allow one character to be reused across the five teams, but deduplicating at
player level makes the usage definition robust to malformed/external data and
matches the intended question: "what fraction of ranked players used this
character somewhere in their five-team set?"
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any


@dataclass(frozen=True)
class SeasonUsageObservation:
    character: str
    raid: int
    player_count: int
    player_appearances: int
    source_character_known: bool
    zero_evidence_safe: bool

    @property
    def usage_fraction(self) -> float | None:
        if self.player_count <= 0 or not self.source_character_known:
            return None
        if self.player_appearances == 0 and not self.zero_evidence_safe:
            return None
        return self.player_appearances / self.player_count


@dataclass(frozen=True)
class EnikkSeasonUsageSnapshot:
    """One normalized Enikk SRRankings response.

    ``incomplete_player_rows`` means at least one ranking row had no usable team
    list.  Positive appearances are still evidence, but zero appearances are not
    called proven for that snapshot.  ``mapped_characters`` records characters
    the Enikk character catalog could map into the local canonical roster; a
    missing mapping likewise prevents a zero from being treated as evidence for
    that character.
    """

    raid: int
    boss: str | None
    player_count: int
    players_with_teams: int
    incomplete_player_rows: int
    player_appearances: Mapping[str, int]
    mapped_characters: frozenset[str]
    unknown_external_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.raid <= 0:
            raise ValueError("raid must be positive")
        if self.player_count < 0 or self.players_with_teams < 0 or self.incomplete_player_rows < 0:
            raise ValueError("player counts must be non-negative")
        if self.players_with_teams + self.incomplete_player_rows != self.player_count:
            raise ValueError("player coverage counts must sum to player_count")
        for name, count in self.player_appearances.items():
            if count < 0 or count > self.player_count:
                raise ValueError(f"invalid appearance count for {name}: {count}")

    @property
    def zero_evidence_safe(self) -> bool:
        return self.player_count > 0 and self.incomplete_player_rows == 0

    def observe(self, character: str) -> SeasonUsageObservation:
        name = str(character)
        known = name in self.mapped_characters
        return SeasonUsageObservation(
            character=name,
            raid=self.raid,
            player_count=self.player_count,
            player_appearances=int(self.player_appearances.get(name, 0)),
            source_character_known=known,
            zero_evidence_safe=self.zero_evidence_safe and known,
        )


@dataclass(frozen=True)
class CharacterUsageWindow:
    """Multi-season evidence over raids the caller explicitly marks eligible.

    The caller must supply ``eligible_raids`` because external rankings alone do
    not prove whether a never-observed character had actually been released in a
    historical season.  This prevents "not present in data" from silently
    becoming zero usage for a new character.
    """

    character: str
    requested_eligible_raids: tuple[int, ...]
    usable_raids: tuple[int, ...]
    uncertain_raids: tuple[int, ...]
    positive_raids: tuple[int, ...]
    zero_raids: tuple[int, ...]
    usage_fractions: tuple[tuple[int, float], ...]
    peak_usage: float | None
    median_usage: float | None

    @property
    def complete_for_requested_window(self) -> bool:
        return bool(self.requested_eligible_raids) and not self.uncertain_raids

    @property
    def eligible_season_count(self) -> int:
        return len(self.requested_eligible_raids)

    @property
    def usable_season_count(self) -> int:
        return len(self.usable_raids)



def summarize_enikk_rankings(
    raid: int,
    rankings: Iterable[Mapping[str, Any]],
    name_map: Mapping[str, str],
    *,
    boss: str | None = None,
) -> EnikkSeasonUsageSnapshot:
    """Normalize one raw ``SRRankings`` response without assigning a cutoff.

    ``name_map`` maps Enikk external character labels from ``teams.characters``
    to local canonical names.  Production acquisition should build it from
    Enikk's character ``resource_id`` catalog rather than string similarity.
    """

    if raid <= 0:
        raise ValueError("raid must be positive")
    mapped_characters = frozenset(str(name) for name in name_map.values())
    counts: dict[str, int] = {}
    unknown: set[str] = set()
    player_count = 0
    players_with_teams = 0
    incomplete = 0

    for row in rankings:
        if not isinstance(row, Mapping):
            raise ValueError("ranking rows must be mappings")
        player_count += 1
        teams = row.get("teams")
        if not isinstance(teams, Sequence) or isinstance(teams, (str, bytes)) or not teams:
            incomplete += 1
            continue

        used_by_player: set[str] = set()
        usable_team_seen = False
        for team in teams:
            if not isinstance(team, Mapping):
                continue
            raw_chars = team.get("characters")
            if not isinstance(raw_chars, Sequence) or isinstance(raw_chars, (str, bytes)) or not raw_chars:
                continue
            usable_team_seen = True
            for external in raw_chars:
                key = str(external)
                canonical = name_map.get(key)
                if canonical is None:
                    unknown.add(key)
                    continue
                used_by_player.add(str(canonical))

        if not usable_team_seen:
            incomplete += 1
            continue
        players_with_teams += 1
        for name in used_by_player:
            counts[name] = counts.get(name, 0) + 1

    return EnikkSeasonUsageSnapshot(
        raid=raid,
        boss=boss,
        player_count=player_count,
        players_with_teams=players_with_teams,
        incomplete_player_rows=incomplete,
        player_appearances=dict(sorted(counts.items())),
        mapped_characters=mapped_characters,
        unknown_external_names=tuple(sorted(unknown)),
    )


def aggregate_character_window(
    character: str,
    snapshots: Iterable[EnikkSeasonUsageSnapshot],
    *,
    eligible_raids: Iterable[int],
) -> CharacterUsageWindow:
    """Aggregate only explicitly eligible seasons and keep uncertainty visible."""

    name = str(character)
    eligible = tuple(dict.fromkeys(int(raid) for raid in eligible_raids))
    if any(raid <= 0 for raid in eligible):
        raise ValueError("eligible raid numbers must be positive")

    by_raid: dict[int, EnikkSeasonUsageSnapshot] = {}
    for snapshot in snapshots:
        if snapshot.raid in by_raid:
            raise ValueError(f"duplicate season snapshot: {snapshot.raid}")
        by_raid[snapshot.raid] = snapshot

    usable: list[int] = []
    uncertain: list[int] = []
    positive: list[int] = []
    zero: list[int] = []
    fractions: list[tuple[int, float]] = []

    for raid in eligible:
        snapshot = by_raid.get(raid)
        if snapshot is None:
            uncertain.append(raid)
            continue
        obs = snapshot.observe(name)
        fraction = obs.usage_fraction
        if fraction is None:
            # A positive appearance remains useful even if the row coverage is
            # incomplete, but ``observe`` only returns None for unknown source
            # mapping or unsafe zero.  Preserve the positive case explicitly.
            if obs.source_character_known and obs.player_count > 0 and obs.player_appearances > 0:
                fraction = obs.player_appearances / obs.player_count
            else:
                uncertain.append(raid)
                continue
        usable.append(raid)
        fractions.append((raid, fraction))
        if obs.player_appearances > 0:
            positive.append(raid)
        elif obs.zero_evidence_safe:
            zero.append(raid)
        else:
            uncertain.append(raid)
            usable.pop()
            fractions.pop()

    values = [fraction for _raid, fraction in fractions]
    return CharacterUsageWindow(
        character=name,
        requested_eligible_raids=eligible,
        usable_raids=tuple(usable),
        uncertain_raids=tuple(uncertain),
        positive_raids=tuple(positive),
        zero_raids=tuple(zero),
        usage_fractions=tuple(fractions),
        peak_usage=max(values) if values else None,
        median_usage=float(median(values)) if values else None,
    )
