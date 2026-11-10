"""In-memory data provider registry and candidate discovery engine.

Implements the ProviderRegistry protocol with thread-safe registration,
feature/symbol discovery, and deterministic priority-based candidate ranking.
All symbol resolution is delegated exclusively to SymbolResolver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import threading
from typing import Any, Sequence

from tradingagents.dataflows.contracts.capabilities import (
    ProviderCapabilities,
    ProviderMetadata,
)
from tradingagents.dataflows.contracts.provider import MarketDataProvider
from tradingagents.dataflows.contracts.registry import ProviderRegistry
from tradingagents.dataflows.symbols import CanonicalSymbol, SymbolResolver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ProviderRegistration:
    """Internal registration record storing provider instance, priority, and metadata."""

    provider: MarketDataProvider
    priority: int
    metadata: ProviderMetadata
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    is_default: bool = False


class InMemoryProviderRegistry:
    """Thread-safe in-memory implementation of ProviderRegistry.

    Responsibilities:
      - Register and unregister MarketDataProvider instances with numeric priorities and metadata.
      - Enforce provider contract conformance at registration time.
      - Discover candidate providers for a given (symbol, feature) query using ProviderCapabilities.
      - Delegate all symbol normalization exclusively to SymbolResolver.
      - Rank candidates deterministically by priority (lower number = higher precedence).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, _ProviderRegistration] = {}

    def register(
        self,
        provider: MarketDataProvider,
        priority: int = 100,
        metadata: ProviderMetadata | None = None,
        overwrite: bool = False,
        is_default: bool = False,
    ) -> None:
        """Register a provider instance with priority (lower number = higher priority).

        Args:
            provider: MarketDataProvider instance conforming to the contract.
            priority: Positive integer ranking priority (e.g. 1 is highest priority).
            metadata: Optional ProviderMetadata value object for future routing decisions.
            overwrite: If True, allow replacing an existing registration with the same name.
            is_default: Mark provider as default fallback.

        Raises:
            ValueError: If provider_name is empty, priority <= 0, or already registered without overwrite.
            TypeError: If provider does not implement required interface methods.
        """
        if provider is None:
            raise ValueError("Provider instance cannot be None")

        name = getattr(provider, "provider_name", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Provider must declare a non-empty string 'provider_name'")

        if not isinstance(priority, int) or priority <= 0:
            raise ValueError(f"Priority must be a positive integer (> 0), got {priority!r}")

        # Invariant checks for protocol conformance
        if not callable(getattr(provider, "supports_feature", None)):
            raise TypeError(f"Provider {name!r} missing callable 'supports_feature'")
        if not callable(getattr(provider, "get_supported_symbols", None)):
            raise TypeError(f"Provider {name!r} missing callable 'get_supported_symbols'")

        # Resolve or construct metadata
        if metadata is None:
            provider_meta = getattr(provider, "metadata", None)
            if isinstance(provider_meta, ProviderMetadata):
                metadata = provider_meta
            else:
                metadata = ProviderMetadata(provider_name=name, priority=priority)

        key = name.strip().lower()

        with self._lock:
            if key in self._entries and not overwrite:
                existing_priority = self._entries[key].priority
                raise ValueError(
                    f"Provider {name!r} is already registered with priority {existing_priority}. "
                    "Use overwrite=True to update."
                )

            self._entries[key] = _ProviderRegistration(
                provider=provider,
                priority=priority,
                metadata=metadata,
                is_default=is_default,
            )
            logger.debug(
                "Registered provider %r with priority %d (total: %d)",
                key,
                priority,
                len(self._entries),
            )

    def unregister(self, provider_name: str) -> bool:
        """Remove a provider from the registry.

        Returns True if the provider was removed, False if it was not found.
        """
        if not isinstance(provider_name, str) or not provider_name.strip():
            return False

        key = provider_name.strip().lower()
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                logger.debug("Unregistered provider %r", key)
                return True
            return False

    def get_provider(self, provider_name: str) -> MarketDataProvider | None:
        """Retrieve a registered provider by name (case-insensitive)."""
        if not isinstance(provider_name, str) or not provider_name.strip():
            return None

        key = provider_name.strip().lower()
        with self._lock:
            entry = self._entries.get(key)
            return entry.provider if entry is not None else None

    def get_priority(self, provider_name: str) -> int | None:
        """Return configured priority for a provider, or None if not registered."""
        if not isinstance(provider_name, str) or not provider_name.strip():
            return None

        key = provider_name.strip().lower()
        with self._lock:
            entry = self._entries.get(key)
            return entry.priority if entry is not None else None

    def get_metadata(self, provider_name: str) -> ProviderMetadata | None:
        """Return operational metadata for a provider, or None if not registered."""
        if not isinstance(provider_name, str) or not provider_name.strip():
            return None

        key = provider_name.strip().lower()
        with self._lock:
            entry = self._entries.get(key)
            return entry.metadata if entry is not None else None

    def list_providers(self) -> Sequence[str]:
        """List all registered provider names sorted primarily by priority then name."""
        with self._lock:
            sorted_entries = sorted(
                self._entries.values(),
                key=lambda e: (e.priority, e.provider.provider_name.lower()),
            )
            return tuple(e.provider.provider_name for e in sorted_entries)

    def get_candidates(
        self, symbol: str, feature_name: str
    ) -> Sequence[MarketDataProvider]:
        """Return candidate providers supporting symbol and feature, ranked by priority.

        Delegates all symbol resolution strictly to SymbolResolver.
        Uses ProviderCapabilities for feature verification where available.
        """
        if not isinstance(symbol, str) or not symbol.strip():
            return ()
        if not isinstance(feature_name, str) or not feature_name.strip():
            return ()

        norm_feature = feature_name.strip().lower()

        # Delegate resolution strictly to SymbolResolver
        try:
            canonical = SymbolResolver.resolve(symbol)
        except Exception:
            canonical = None

        with self._lock:
            candidates: list[tuple[int, str, MarketDataProvider]] = []

            for key, entry in self._entries.items():
                provider = entry.provider

                # 1. Feature check using provider capabilities / supports_feature
                try:
                    if not provider.supports_feature(norm_feature):
                        continue
                except Exception as exc:
                    logger.warning(
                        "Provider %r raised during feature check (%r): %s",
                        key,
                        norm_feature,
                        exc,
                    )
                    continue

                # 2. Symbol check against provider supported symbols
                try:
                    supported_symbols = provider.get_supported_symbols()
                except Exception as exc:
                    logger.warning(
                        "Provider %r raised during get_supported_symbols(): %s",
                        key,
                        exc,
                    )
                    continue

                if self._provider_supports_symbol(canonical, symbol, supported_symbols):
                    candidates.append((entry.priority, provider.provider_name, provider))

            # Rank by priority ascending (1 before 10), then provider name alphabetically
            candidates.sort(key=lambda item: (item[0], item[1].lower()))
            return tuple(item[2] for item in candidates)

    def get_providers_for_symbol(self, symbol: str) -> Sequence[MarketDataProvider]:
        """Return all providers supporting a symbol regardless of feature, ranked by priority."""
        if not isinstance(symbol, str) or not symbol.strip():
            return ()

        try:
            canonical = SymbolResolver.resolve(symbol)
        except Exception:
            canonical = None

        with self._lock:
            candidates: list[tuple[int, str, MarketDataProvider]] = []
            for entry in self._entries.values():
                try:
                    supported = entry.provider.get_supported_symbols()
                except Exception:
                    continue

                if self._provider_supports_symbol(canonical, symbol, supported):
                    candidates.append(
                        (entry.priority, entry.provider.provider_name, entry.provider)
                    )

            candidates.sort(key=lambda item: (item[0], item[1].lower()))
            return tuple(item[2] for item in candidates)

    def get_providers_for_feature(
        self, feature_name: str
    ) -> Sequence[MarketDataProvider]:
        """Return all providers supporting a feature regardless of symbol, ranked by priority."""
        if not isinstance(feature_name, str) or not feature_name.strip():
            return ()

        norm_feature = feature_name.strip().lower()
        with self._lock:
            candidates: list[tuple[int, str, MarketDataProvider]] = []
            for entry in self._entries.values():
                try:
                    if entry.provider.supports_feature(norm_feature):
                        candidates.append(
                            (entry.priority, entry.provider.provider_name, entry.provider)
                        )
                except Exception:
                    continue

            candidates.sort(key=lambda item: (item[0], item[1].lower()))
            return tuple(item[2] for item in candidates)

    def get_supported_symbols_all(self) -> Sequence[str]:
        """Aggregate unique supported symbols across all registered providers."""
        with self._lock:
            symbols_set: set[str] = set()
            for entry in self._entries.values():
                try:
                    for s in entry.provider.get_supported_symbols():
                        symbols_set.add(s)
                except Exception:
                    continue
            return tuple(sorted(symbols_set))

    def get_supported_features_all(self) -> Sequence[str]:
        """Aggregate standard and registered features supported across providers."""
        standard_features = [
            "quote",
            "ohlcv",
            "orderbook",
            "funding_rate",
            "open_interest",
            "liquidations",
            "news",
            "macro",
            "sentiment",
            "economic_calendar",
        ]
        with self._lock:
            supported: set[str] = set()
            for feat in standard_features:
                for entry in self._entries.values():
                    try:
                        if entry.provider.supports_feature(feat):
                            supported.add(feat)
                            break
                    except Exception:
                        continue
            return tuple(sorted(supported))

    def clear(self) -> None:
        """Reset registry and clear all registrations."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __contains__(self, provider_name: str) -> bool:
        if not isinstance(provider_name, str):
            return False
        with self._lock:
            return provider_name.strip().lower() in self._entries

    # ------------------------------------------------------------------
    # Symbol Matching - Delegating Strictly to Canonical Symbol
    # ------------------------------------------------------------------

    @staticmethod
    def _provider_supports_symbol(
        canonical: CanonicalSymbol | None,
        raw_symbol: str,
        supported_symbols: Sequence[str],
    ) -> bool:
        """Check if provider supported symbols includes canonical symbol representations or wildcard '*'."""
        if not supported_symbols:
            return False

        if "*" in supported_symbols:
            return True

        normalized_supported = {s.strip().upper() for s in supported_symbols}
        raw_upper = raw_symbol.strip().upper()

        if raw_upper in normalized_supported:
            return True

        if canonical is not None:
            candidates_to_check = {
                canonical.canonical_id.upper(),
                canonical.yahoo_symbol.upper(),
            }
            if canonical.binance_symbol:
                candidates_to_check.add(canonical.binance_symbol.upper())
            if canonical.coinbase_symbol:
                candidates_to_check.add(canonical.coinbase_symbol.upper())

            if candidates_to_check & normalized_supported:
                return True

            # Also check without formatting slash or dash for standard compact representation
            compact_supported = {
                s.strip().upper().replace("/", "").replace("-", "")
                for s in supported_symbols
            }
            for c in candidates_to_check:
                if c.replace("/", "").replace("-", "") in compact_supported:
                    return True

        return False
