"""Local-only BlaBlaLink Worker account bundle for optimizer benchmarks.

The existing Worker adapter intentionally returns only an audited account snapshot.
Real-account optimizer diagnostics also need the normalized calculator payload and
the identifier-free raw sidecar in order to derive provenance such as exact
Overload-piece evidence. This module exposes those three views together without
performing network I/O or retaining Worker account identifiers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .account_bundle import AuditedAccountSnapshot, normalize_account_bundle
from .blablalink import _profile_from_area, select_blablalink_area


@dataclass(frozen=True)
class WorkerAccountBundle:
    """One normalized Worker payload plus the raw evidence used to audit it."""

    snapshot: AuditedAccountSnapshot
    profile_payload: Mapping[str, Any]
    raw_sidecar: Mapping[str, Any]

    @property
    def roster(self) -> tuple[str, ...]:
        return self.snapshot.roster

    @property
    def blocking_unknowns(self):
        return self.snapshot.blocking_unknowns


def build_worker_account_bundle(
    worker_payload: Mapping[str, Any],
    *,
    preferred_area: int | None = None,
    level_mode: str = "fixed",
    unknown_policy: str = "error",
) -> WorkerAccountBundle:
    """Normalize one in-memory Worker response and retain only safe audit inputs.

    ``_profile_from_area`` already strips the Worker ``openid`` and keeps only
    simulation/provenance fields in its raw sidecar. The returned bundle therefore
    gives local benchmark code access to exact raw option slots without turning an
    account identifier into optimizer state or cache identity.
    """

    area = select_blablalink_area(worker_payload, preferred_area=preferred_area)
    profile, raw_sidecar = _profile_from_area(area)
    snapshot = normalize_account_bundle(
        profile,
        raw_sidecar,
        level_mode=level_mode,
        unknown_policy=unknown_policy,
    )
    return WorkerAccountBundle(
        snapshot=snapshot,
        profile_payload=profile,
        raw_sidecar=raw_sidecar,
    )
