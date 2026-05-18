"""Watch-mode universe rotation for scaled scanning.

Selects symbols for each watch cycle so that:
- Core / benchmark symbols are always included first
- Open-snapshot symbols are always included (continuity)
- Prior high-priority candidates are included (continuity)
- Remaining slots rotate through the discovery universe (round-robin)

No duplicates. Max symbols per cycle is enforced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RotationResult:
    """Describes symbol selection for one watch cycle."""

    symbols: list[str]
    bucket_id: int
    core_count: int
    open_snapshot_count: int
    previous_candidate_count: int
    discovery_count: int
    total: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket_id": self.bucket_id,
            "core_count": self.core_count,
            "open_snapshot_count": self.open_snapshot_count,
            "previous_candidate_count": self.previous_candidate_count,
            "discovery_count": self.discovery_count,
            "total": self.total,
        }


class WatchUniverseRotator:
    """Manages symbol selection across watch cycles.

    Guarantees core symbols and open-snapshot symbols are always included.
    Rotates through the discovery universe via round-robin across cycles.
    Deduplicates across all categories and respects max_symbols_per_cycle.
    """

    def __init__(self, all_symbols: list[str], config: dict[str, Any]) -> None:
        self.all_symbols = [s.strip().upper() for s in all_symbols if s.strip()]
        self.max_per_cycle: int = int(config.get("max_symbols_per_cycle", 175))
        self.core_symbols: list[str] = [
            s.strip().upper() for s in config.get("core_symbols", []) if s.strip()
        ]
        self.core_max: int = int(config.get("core_max_symbols", 50))
        self.bucket_size: int = int(config.get("rotating_bucket_size", 125))
        self.keep_previous: bool = bool(config.get("keep_previous_candidates", True))
        self.always_include_open: bool = bool(config.get("always_include_open_snapshots", True))
        self._bucket_index: int = 0
        self._previous_candidates: list[str] = []

    @property
    def bucket_id(self) -> int:
        return self._bucket_index

    def get_cycle_symbols(
        self,
        open_snapshot_symbols: list[str] | None = None,
    ) -> RotationResult:
        """Select symbols for one cycle.

        Precedence (highest to lowest):
          1. Core symbols (always first, capped at core_max)
          2. Open snapshot symbols (continuity)
          3. Previous high-priority candidates (continuity)
          4. Discovery rotation (round-robin through full universe)

        Returns a RotationResult with the ordered, deduplicated symbol list.
        """
        seen: set[str] = set()
        result: list[str] = []

        def _add(symbol: str) -> bool:
            sym = symbol.strip().upper()
            if sym and sym not in seen and len(result) < self.max_per_cycle:
                seen.add(sym)
                result.append(sym)
                return True
            return False

        # 1. Core symbols
        core_added = 0
        for s in self.core_symbols[: self.core_max]:
            if _add(s):
                core_added += 1

        # 2. Open snapshot symbols
        open_added = 0
        if self.always_include_open and open_snapshot_symbols:
            for s in open_snapshot_symbols:
                if _add(s):
                    open_added += 1

        # 3. Previous high-priority candidates
        prev_added = 0
        if self.keep_previous:
            for s in self._previous_candidates:
                if _add(s):
                    prev_added += 1

        # 4. Discovery rotation
        available = [s for s in self.all_symbols if s not in seen]
        bucket_id = self._bucket_index
        discovery_added = 0

        if available and len(result) < self.max_per_cycle:
            start = self._bucket_index % len(available)
            pool: list[str] = []
            for i in range(min(self.bucket_size, len(available))):
                pool.append(available[(start + i) % len(available)])
            for s in pool:
                if _add(s):
                    discovery_added += 1
            self._bucket_index = (self._bucket_index + len(pool)) % max(len(self.all_symbols), 1)

        return RotationResult(
            symbols=result,
            bucket_id=bucket_id,
            core_count=core_added,
            open_snapshot_count=open_added,
            previous_candidate_count=prev_added,
            discovery_count=discovery_added,
            total=len(result),
        )

    def update_previous_candidates(self, high_priority_symbols: list[str]) -> None:
        """Update the carry-forward list for next cycle's continuity step."""
        self._previous_candidates = [s.strip().upper() for s in high_priority_symbols if s.strip()]
