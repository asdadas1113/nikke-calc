"""Strict JSON input adapter for production bounded Meta/Cold evidence.

This module is intentionally separate from the historical descriptive benchmark
parser. Production inputs must state the expected ranking cohort and every source
of uncertainty explicitly; omitted uncertainty never becomes zero by default.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from .meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    SoloRaidPeriod,
    SoloRaidSchedule,
)
from .meta_epoch_input import resolve_meta_epoch_input
from .meta_usage_bounds import (
    CertifiedEnikkSeasonUsageSnapshot,
    RankingCoverageContract,
)


@dataclass(frozen=True)
class BoundedMetaEvidenceInput:
    completed_through: date
    policy: LowUsagePolicy
    schedule: SoloRaidSchedule
    epochs: Mapping[str, MetaEpochEvidence]
    snapshots: tuple[CertifiedEnikkSeasonUsageSnapshot, ...]
    restoration_batch_size: int
    cold_exploration_limit: int
    protected_names: tuple[str, ...]


def _required(row: Mapping[str, Any], key: str, label: str) -> Any:
    if key not in row:
        raise ValueError(f"{label}.{key} is required")
    return row[key]


def _date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label}: expected ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}: invalid ISO date {value!r}") from exc


def _string_tuple(value: Any, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{label}: expected string list")
    result = tuple(value)
    if nonempty and not result:
        raise ValueError(f"{label}: must not be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{label}: duplicate values")
    return result


def _int_mapping(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label}: expected object")
    result: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{label}: keys must be strings")
        if isinstance(raw, bool):
            raise ValueError(f"{label}[{key!r}]: expected integer")
        try:
            parsed = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}[{key!r}]: expected integer") from exc
        if parsed != raw:
            raise ValueError(f"{label}[{key!r}]: expected exact integer")
        result[key] = parsed
    return result


def _parse_schedule(payload: Mapping[str, Any]) -> SoloRaidSchedule:
    row = _required(payload, "schedule", "meta")
    if not isinstance(row, Mapping):
        raise ValueError("meta.schedule must be an object")
    periods_raw = _required(row, "periods", "meta.schedule")
    if not isinstance(periods_raw, list):
        raise ValueError("meta.schedule.periods must be a list")
    periods: list[SoloRaidPeriod] = []
    for index, item in enumerate(periods_raw):
        label = f"meta.schedule.periods[{index}]"
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} must be an object")
        periods.append(
            SoloRaidPeriod(
                raid=int(_required(item, "raid", label)),
                start_on=_date(_required(item, "start_on", label), f"{label}.start_on"),
                end_on=_date(_required(item, "end_on", label), f"{label}.end_on"),
            )
        )
    complete = _required(row, "complete", "meta.schedule")
    if not isinstance(complete, bool):
        raise ValueError("meta.schedule.complete must be boolean")
    source = _required(row, "source", "meta.schedule")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("meta.schedule.source must be a non-empty string")
    return SoloRaidSchedule(tuple(periods), complete=complete, source=source)


def _parse_policy(payload: Mapping[str, Any]) -> LowUsagePolicy:
    row = _required(payload, "policy", "meta")
    if not isinstance(row, Mapping):
        raise ValueError("meta.policy must be an object")
    return LowUsagePolicy(
        completed_seasons=int(_required(row, "completed_seasons", "meta.policy")),
        max_peak_usage=float(_required(row, "max_peak_usage", "meta.policy")),
    )


def _parse_contract(payload: Mapping[str, Any]) -> RankingCoverageContract:
    row = _required(payload, "coverage_contract", "meta")
    if not isinstance(row, Mapping):
        raise ValueError("meta.coverage_contract must be an object")
    servers = _string_tuple(
        _required(row, "servers", "meta.coverage_contract"),
        "meta.coverage_contract.servers",
        nonempty=True,
    )
    source = _required(row, "source", "meta.coverage_contract")
    if not isinstance(source, str):
        raise ValueError("meta.coverage_contract.source must be a string")
    return RankingCoverageContract(
        servers=servers,
        rank_start=int(_required(row, "rank_start", "meta.coverage_contract")),
        rank_end=int(_required(row, "rank_end", "meta.coverage_contract")),
        team_count=int(_required(row, "team_count", "meta.coverage_contract")),
        team_size=int(_required(row, "team_size", "meta.coverage_contract")),
        source=source,
    )


def _parse_explicit_epochs(payload: Mapping[str, Any]) -> dict[str, MetaEpochEvidence] | None:
    if "epochs" not in payload:
        return None
    raw = payload["epochs"]
    if not isinstance(raw, Mapping):
        raise ValueError("meta.epochs must be an object")
    result: dict[str, MetaEpochEvidence] = {}
    for character, row in raw.items():
        if not isinstance(character, str) or not isinstance(row, Mapping):
            raise ValueError("meta.epochs entries must map character strings to objects")
        try:
            knowledge = MetaEpochKnowledge(str(_required(row, "knowledge", f"meta.epochs[{character!r}]")))
        except ValueError as exc:
            raise ValueError(f"meta.epochs[{character!r}].knowledge is invalid") from exc
        valid_from = None
        if knowledge is MetaEpochKnowledge.KNOWN:
            valid_from = _date(
                _required(row, "valid_from", f"meta.epochs[{character!r}]"),
                f"meta.epochs[{character!r}].valid_from",
            )
        source = _required(row, "source", f"meta.epochs[{character!r}]")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"meta.epochs[{character!r}].source must be non-empty")
        result[character] = MetaEpochEvidence(
            character=character,
            knowledge=knowledge,
            valid_from=valid_from,
            source=source,
            reason=str(row.get("reason") or ""),
        )
    return result


def _registry_rows(payload: Mapping[str, Any], key: str) -> Sequence[Mapping[str, Any]] | None:
    if key not in payload:
        return None
    raw = payload[key]
    if not isinstance(raw, list) or not all(isinstance(row, Mapping) for row in raw):
        raise ValueError(f"meta.{key} must be a list of objects")
    return tuple(raw)


def _parse_snapshots(
    payload: Mapping[str, Any],
    contract: RankingCoverageContract,
) -> tuple[CertifiedEnikkSeasonUsageSnapshot, ...]:
    raw = _required(payload, "snapshots", "meta")
    if not isinstance(raw, list):
        raise ValueError("meta.snapshots must be a list")
    snapshots: list[CertifiedEnikkSeasonUsageSnapshot] = []
    required_uncertainty = (
        "observed_complete_player_slots",
        "missing_player_slots",
        "malformed_player_slots",
        "mapping_uncertain_player_slots",
        "ambiguous_player_slots",
    )
    for index, row in enumerate(raw):
        label = f"meta.snapshots[{index}]"
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} must be an object")
        for key in required_uncertainty:
            _required(row, key, label)
        appearances = _int_mapping(
            _required(row, "player_appearances", label),
            f"{label}.player_appearances",
        )
        ambiguous = _int_mapping(
            row["ambiguous_player_slots"],
            f"{label}.ambiguous_player_slots",
        )
        mapped = _string_tuple(
            _required(row, "mapped_characters", label),
            f"{label}.mapped_characters",
        )
        unknown = _string_tuple(
            _required(row, "unknown_external_names", label),
            f"{label}.unknown_external_names",
        )
        snapshots.append(
            CertifiedEnikkSeasonUsageSnapshot(
                raid=int(_required(row, "raid", label)),
                boss=None if row.get("boss") is None else str(row["boss"]),
                contract=contract,
                observed_complete_player_slots=int(row["observed_complete_player_slots"]),
                missing_player_slots=int(row["missing_player_slots"]),
                malformed_player_slots=int(row["malformed_player_slots"]),
                mapping_uncertain_player_slots=int(row["mapping_uncertain_player_slots"]),
                ambiguous_player_slots=ambiguous,
                player_appearances=appearances,
                mapped_characters=frozenset(mapped),
                unknown_external_names=tuple(sorted(unknown)),
            )
        )
    return tuple(snapshots)


def parse_bounded_meta_evidence(
    payload: Mapping[str, Any],
    *,
    roster: Sequence[str],
) -> BoundedMetaEvidenceInput:
    """Parse one production Meta evidence document with fail-open semantics.

    The declared coverage contract is mandatory even when the snapshot list is
    temporarily empty. Every snapshot must explicitly provide all uncertainty
    counters, including ``ambiguous_player_slots``. Epoch evidence may be supplied
    either as explicit rows or through first-availability/change-event registry
    rows; mixing the modes is rejected by :func:`resolve_meta_epoch_input`.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("meta payload must be an object")
    names = tuple(str(name) for name in roster)
    if len(set(names)) != len(names):
        raise ValueError("roster must contain unique names")

    completed_through = _date(
        _required(payload, "completed_through", "meta"),
        "meta.completed_through",
    )
    policy = _parse_policy(payload)
    schedule = _parse_schedule(payload)
    contract = _parse_contract(payload)
    explicit_epochs = _parse_explicit_epochs(payload)
    first_availability = _registry_rows(payload, "first_availability")
    change_events = _registry_rows(payload, "change_events")
    epochs = resolve_meta_epoch_input(
        names,
        through=completed_through,
        explicit_epochs=explicit_epochs,
        first_availability_rows=first_availability,
        change_event_rows=change_events,
        source="bounded-meta-input",
    )
    snapshots = _parse_snapshots(payload, contract)

    restoration_batch_size = int(
        _required(payload, "restoration_batch_size", "meta")
    )
    if restoration_batch_size <= 0:
        raise ValueError("meta.restoration_batch_size must be positive")
    cold_exploration_limit = int(
        _required(payload, "cold_exploration_limit", "meta")
    )
    if cold_exploration_limit < 0:
        raise ValueError("meta.cold_exploration_limit must be non-negative")
    protected_names = _string_tuple(
        _required(payload, "protected_names", "meta"),
        "meta.protected_names",
    )
    unknown_protected = tuple(name for name in protected_names if name not in set(names))
    if unknown_protected:
        raise ValueError(
            "meta.protected_names contains characters outside roster: "
            + ", ".join(sorted(unknown_protected))
        )

    return BoundedMetaEvidenceInput(
        completed_through=completed_through,
        policy=policy,
        schedule=schedule,
        epochs=epochs,
        snapshots=snapshots,
        restoration_batch_size=restoration_batch_size,
        cold_exploration_limit=cold_exploration_limit,
        protected_names=protected_names,
    )
