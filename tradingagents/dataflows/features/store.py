"""Thread-safe, high-performance in-memory Feature Store for quantitative market features.

Guarantees:
- Strict point-in-time correctness (zero future leakage, timestamp <= as_of).
- O(1) retrieval for latest observations.
- Thread-safe concurrency via reentrant locks (RLock).
- Configurable default and per-entry TTL with passive and active purge.
- Selective cache invalidation across symbols, timeframes, or feature namespaces.
- Zero external dependencies.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import datetime, timezone
import threading
import time
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureStore
from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError


class InMemoryFeatureStore(FeatureStore):
    """High-performance thread-safe in-memory feature storage."""

    def __init__(
        self,
        default_ttl_seconds: float | None = None,
        max_history_per_series: int = 2000,
    ) -> None:
        """Initialize the feature store.

        Args:
            default_ttl_seconds: Optional default TTL in seconds for stored features.
            max_history_per_series: Maximum chronological observations retained per series key.
        """
        if default_ttl_seconds is not None and default_ttl_seconds <= 0:
            raise ValueError(f"default_ttl_seconds must be positive, got {default_ttl_seconds}")
        if max_history_per_series <= 0:
            raise ValueError(f"max_history_per_series must be positive, got {max_history_per_series}")

        self._default_ttl_seconds = default_ttl_seconds
        self._max_history_per_series = max_history_per_series
        self._lock = threading.RLock()

        # Key structure: (canonical_symbol: str, timeframe_val: str, feature_name: str)
        # _latest: SeriesKey -> (feature_dto, expire_at_monotonic | None)
        self._latest: dict[tuple[str, str, str], tuple[BaseFeatureDTO, float | None]] = {}

        # _history: SeriesKey -> list of (timestamp, expire_at_monotonic | None, feature_dto)
        # Maintained in strictly ascending order by timestamp for bisect lookups.
        self._history: dict[tuple[str, str, str], list[tuple[datetime, float | None, BaseFeatureDTO]]] = defaultdict(list)

    @staticmethod
    def _normalize_timeframe(tf: Timeframe | str) -> str:
        """Extract canonical string value for a timeframe."""
        if isinstance(tf, Timeframe):
            return tf.value
        return str(tf)

    @staticmethod
    def _make_key(symbol: str, timeframe: Timeframe | str, feature_name: str) -> tuple[str, str, str]:
        """Construct normalized composite series key."""
        return (symbol.strip().upper(), InMemoryFeatureStore._normalize_timeframe(timeframe), feature_name.strip())

    def store_feature(
        self,
        feature: BaseFeatureDTO,
        ttl_seconds: float | None = None,
    ) -> None:
        """Store a single immutable feature observation."""
        if not isinstance(feature, BaseFeatureDTO):
            raise DTOValidationError(f"Expected BaseFeatureDTO instance, got {type(feature)}")

        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        expire_at = (time.monotonic() + ttl) if (ttl is not None and ttl > 0) else None

        key = self._make_key(feature.symbol, feature.timeframe, feature.feature_name)
        ts = feature.timestamp

        with self._lock:
            # 1. Update latest if this feature is as fresh or newer than current latest
            current_latest = self._latest.get(key)
            if current_latest is None or ts >= current_latest[0].timestamp:
                self._latest[key] = (feature, expire_at)

            # 2. Update chronological historical series
            series = self._history[key]
            # Binary search to find position or exact timestamp match
            idx = bisect.bisect_left(series, ts, key=lambda item: item[0])

            if idx < len(series) and series[idx][0] == ts:
                # Existing exact timestamp -> overwrite with latest calculation
                series[idx] = (ts, expire_at, feature)
            else:
                # Insert at sorted position
                series.insert(idx, (ts, expire_at, feature))

            # Enforce max history ring-buffer boundary
            if len(series) > self._max_history_per_series:
                excess = len(series) - self._max_history_per_series
                del series[:excess]

    def store_features(
        self,
        features: Sequence[BaseFeatureDTO],
        ttl_seconds: float | None = None,
    ) -> int:
        """Atomically store a batch of immutable feature observations."""
        with self._lock:
            count = 0
            for feat in features:
                self.store_feature(feat, ttl_seconds=ttl_seconds)
                count += 1
            return count

    def get_latest(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        feature_name: str,
    ) -> BaseFeatureDTO | None:
        """Retrieve the most recent observation for a series in O(1) time."""
        key = self._make_key(symbol, timeframe, feature_name)
        now_mono = time.monotonic()

        with self._lock:
            record = self._latest.get(key)
            if record is None:
                return None

            feat, expire_at = record
            if expire_at is not None and expire_at < now_mono:
                # Evict expired latest
                del self._latest[key]
                return None

            return feat

    def get_as_of(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        feature_name: str,
        as_of: datetime,
    ) -> BaseFeatureDTO | None:
        """Retrieve the latest observation where timestamp <= as_of (zero future leakage)."""
        validate_utc_datetime(as_of, "as_of")
        key = self._make_key(symbol, timeframe, feature_name)
        now_mono = time.monotonic()

        with self._lock:
            series = self._history.get(key)
            if not series:
                return None

            # bisect_right finds the insertion point after all elements <= as_of
            idx = bisect.bisect_right(series, as_of, key=lambda item: item[0])
            if idx == 0:
                # All observations in history are strictly in the future relative to as_of
                return None

            # Look backwards from idx - 1 for the most recent unexpired observation
            for candidate_idx in range(idx - 1, -1, -1):
                cand_ts, cand_expire, cand_feat = series[candidate_idx]
                if cand_expire is not None and cand_expire < now_mono:
                    # Candidate observation has expired
                    continue
                # Found valid point-in-time feature
                return cand_feat

            return None

    def get_batch(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        feature_names: Sequence[str],
        as_of: datetime | None = None,
    ) -> dict[str, BaseFeatureDTO]:
        """Retrieve multiple features for a symbol/timeframe in a single atomic snapshot."""
        results: dict[str, BaseFeatureDTO] = {}
        with self._lock:
            for name in feature_names:
                feat = (
                    self.get_as_of(symbol, timeframe, name, as_of)
                    if as_of is not None
                    else self.get_latest(symbol, timeframe, name)
                )
                if feat is not None:
                    results[name] = feat
        return results

    def invalidate(
        self,
        symbol: str | None = None,
        timeframe: Timeframe | str | None = None,
        feature_name: str | None = None,
    ) -> int:
        """Invalidate cached entries matching the specified filter criteria.

        If symbol, timeframe, and feature_name are all None, all entries are cleared.
        """
        norm_sym = symbol.strip().upper() if symbol is not None else None
        norm_tf = self._normalize_timeframe(timeframe) if timeframe is not None else None
        norm_fn = feature_name.strip() if feature_name is not None else None

        with self._lock:
            keys_to_remove = [
                key for key in self._history.keys()
                if (norm_sym is None or key[0] == norm_sym)
                and (norm_tf is None or key[1] == norm_tf)
                and (norm_fn is None or key[2] == norm_fn)
            ]

            for key in keys_to_remove:
                self._history.pop(key, None)
                self._latest.pop(key, None)

            return len(keys_to_remove)

    def purge_expired(self) -> int:
        """Purge all entries whose TTL has elapsed."""
        now_mono = time.monotonic()
        purged_count = 0

        with self._lock:
            # Purge from _latest
            latest_keys_to_remove = [
                k for k, (_, exp) in self._latest.items()
                if exp is not None and exp < now_mono
            ]
            for k in latest_keys_to_remove:
                del self._latest[k]

            # Purge from _history
            empty_history_keys: list[tuple[str, str, str]] = []
            for k, series in self._history.items():
                initial_len = len(series)
                unexpired = [item for item in series if item[1] is None or item[1] >= now_mono]
                purged_count += (initial_len - len(unexpired))
                if not unexpired:
                    empty_history_keys.append(k)
                else:
                    self._history[k] = unexpired

            for k in empty_history_keys:
                del self._history[k]

        return purged_count

    def count_series(self) -> int:
        """Return the number of active series keys in the store."""
        with self._lock:
            return len(self._history)

    def total_observations(self) -> int:
        """Return the total number of cached observations across all series."""
        with self._lock:
            return sum(len(series) for series in self._history.values())
