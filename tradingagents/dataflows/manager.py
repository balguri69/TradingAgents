"""Production Market Data Provider Manager.

Single orchestration layer for all market data ingestion across the platform.
Agents and analytical components access market data exclusively through this manager.
Responsible for:
  - Dynamic provider selection and priority failover
  - Provider health, latency, and circuit state tracking
  - Static exchange metadata caching (live data is never cached)
  - Strict domain validation and invariant verification
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
import threading
import time
from typing import Any, Callable, Sequence, TypeVar

from tradingagents.dataflows.contracts.manager import MarketDataProviderManager
from tradingagents.dataflows.contracts.provider import ExchangeProvider, MarketDataProvider
from tradingagents.dataflows.contracts.registry import ProviderRegistry
from tradingagents.dataflows.dto.market_data import (
    CandleDTO,
    ExchangeInfoDTO,
    FundingRateDTO,
    MarkPriceDTO,
    OHLCVSeriesDTO,
    OpenInterestDTO,
    OrderBookDTO,
    QuoteDTO,
    SymbolFilterDTO,
)
from tradingagents.dataflows.dto.telemetry import (
    HealthStatusDTO,
    ProviderHealth,
)
from tradingagents.dataflows.enums import CircuitState, HealthState, Timeframe
from tradingagents.dataflows.exceptions import (
    DTOValidationError,
    NoMarketDataError,
    VendorError,
    VendorRateLimitError,
    VendorUnavailableError,
)
from tradingagents.dataflows.registry import InMemoryProviderRegistry
from tradingagents.dataflows.symbols import CanonicalSymbol, SymbolResolver

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DefaultMarketDataProviderManager(MarketDataProviderManager):
    """Institutional multi-asset market data orchestrator.

    Guarantees:
      - Agents interact only with this manager, never directly with raw providers.
      - Dynamic failover across ranked candidate providers when errors occur.
      - Comprehensive health telemetry and circuit breaker state tracking.
      - Live data (quotes, books, rates) is strictly un-cached.
      - Static exchange metadata (precision, tick size, step size) is cached with configurable TTL.
    """

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        metadata_cache_ttl_seconds: int = 3600,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_seconds: float = 60.0,
    ) -> None:
        self._registry = registry if registry is not None else InMemoryProviderRegistry()
        self._metadata_cache_ttl = metadata_cache_ttl_seconds
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_cooldown_seconds = circuit_cooldown_seconds

        self._lock = threading.RLock()

        # Telemetry & Circuit Tracking
        self._health_records: dict[str, ProviderHealth] = {}
        self._last_failure_times: dict[str, float] = {}

        # Static Metadata Caches: live market data is NEVER cached
        # Format: (expiry_timestamp, DTO)
        self._symbol_filters_cache: dict[tuple[str, str], tuple[float, SymbolFilterDTO]] = {}
        self._exchange_info_cache: dict[str, tuple[float, ExchangeInfoDTO]] = {}

    # ------------------------------------------------------------------
    # MarketDataProviderManager Protocol Methods
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str, as_of: datetime | None = None) -> QuoteDTO:
        """Fetch live or point-in-time quote via managed provider failover."""
        return self._execute_with_failover(
            symbol=symbol,
            feature_name="quote",
            operation_fn=lambda p, s: p.get_quote(s.canonical_id, as_of=as_of),
        )

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_date: datetime,
        end_date: datetime,
    ) -> OHLCVSeriesDTO:
        """Fetch historical candlestick series with transparent pagination."""
        if start_date.tzinfo is None or end_date.tzinfo is None:
            raise ValueError("start_date and end_date must be timezone-aware (UTC)")
        if start_date > end_date:
            raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

        return self._execute_with_failover(
            symbol=symbol,
            feature_name="ohlcv",
            operation_fn=lambda p, s: p.get_ohlcv(
                symbol=s.canonical_id,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
            ),
        )

    def get_orderbook(
        self, symbol: str, depth: int = 20, as_of: datetime | None = None
    ) -> OrderBookDTO:
        """Fetch L2 market depth snapshot via managed provider failover."""
        return self._execute_with_failover(
            symbol=symbol,
            feature_name="orderbook",
            operation_fn=lambda p, s: p.get_orderbook(
                symbol=s.canonical_id, depth=depth, as_of=as_of
            ),
        )

    def get_funding_rate(
        self, symbol: str, as_of: datetime | None = None
    ) -> FundingRateDTO:
        """Fetch derivative perpetual swap funding rate via capability routing."""
        return self._execute_with_failover(
            symbol=symbol,
            feature_name="funding_rate",
            operation_fn=lambda p, s: p.get_funding_rate(s.canonical_id, as_of=as_of),
        )

    def get_open_interest(self, symbol: str) -> OpenInterestDTO:
        """Fetch derivative open interest via capability routing."""
        return self._execute_with_failover(
            symbol=symbol,
            feature_name="open_interest",
            operation_fn=lambda p, s: (
                p.get_open_interest(s.canonical_id)
                if hasattr(p, "get_open_interest")
                else (_ for _ in ()).throw(
                    NotImplementedError(f"Provider {p.provider_name} does not support open_interest")
                )
            ),
        )

    def get_mark_price(self, symbol: str) -> MarkPriceDTO:
        """Fetch derivative perpetual mark and index prices via capability routing."""
        return self._execute_with_failover(
            symbol=symbol,
            feature_name="funding_rate",
            operation_fn=lambda p, s: (
                p.get_mark_price(s.canonical_id)
                if hasattr(p, "get_mark_price")
                else (_ for _ in ()).throw(
                    NotImplementedError(f"Provider {p.provider_name} does not support mark_price")
                )
            ),
        )

    # ------------------------------------------------------------------
    # Static Exchange Metadata (Cached with TTL)
    # ------------------------------------------------------------------

    def get_symbol_filters(self, symbol: str) -> SymbolFilterDTO:
        """Retrieve tick size, lot step size, and precision rules (cached with TTL)."""
        canonical = SymbolResolver.resolve(symbol)
        now = time.monotonic()

        # Check internal cache
        with self._lock:
            for (prov_name, sym_key), (expiry, cached_filter) in self._symbol_filters_cache.items():
                if sym_key == canonical.canonical_id and now < expiry:
                    return cached_filter

        # Fetch live via failover and cache static result
        def _fetch_filter(provider: MarketDataProvider, s: CanonicalSymbol) -> SymbolFilterDTO:
            if hasattr(provider, "get_symbol_filters"):
                return provider.get_symbol_filters(s.canonical_id)
            raise NotImplementedError(f"Provider {provider.provider_name} does not support symbol filters")

        filters = self._execute_with_failover(
            symbol=symbol,
            feature_name="quote",
            operation_fn=_fetch_filter,
        )

        with self._lock:
            expiry = now + self._metadata_cache_ttl
            self._symbol_filters_cache[(filters.exchange, canonical.canonical_id)] = (
                expiry,
                filters,
            )

        return filters

    def get_exchange_info(self, provider_name: str | None = None) -> ExchangeInfoDTO:
        """Retrieve venue exchange information catalog (cached with TTL)."""
        now = time.monotonic()

        with self._lock:
            if provider_name and provider_name in self._exchange_info_cache:
                expiry, cached_info = self._exchange_info_cache[provider_name]
                if now < expiry:
                    return cached_info

        # Select provider
        target_provider: MarketDataProvider | None = None
        if provider_name:
            target_provider = self._registry.get_provider(provider_name)
        else:
            # Pick first available registered exchange provider
            for p_name in self._registry.list_providers():
                p = self._registry.get_provider(p_name)
                if isinstance(p, ExchangeProvider) or hasattr(p, "get_exchange_info"):
                    target_provider = p
                    break

        if target_provider is None or not hasattr(target_provider, "get_exchange_info"):
            raise NoMarketDataError(f"No exchange provider available to fetch exchange info for {provider_name}")

        info = target_provider.get_exchange_info()

        with self._lock:
            expiry = now + self._metadata_cache_ttl
            self._exchange_info_cache[target_provider.provider_name] = (expiry, info)

        return info

    def clear_metadata_cache(self) -> None:
        """Evict all cached exchange metadata (symbol filters and exchange info)."""
        with self._lock:
            self._symbol_filters_cache.clear()
            self._exchange_info_cache.clear()

    # ------------------------------------------------------------------
    # Diagnostic Health & Circuit Telemetry
    # ------------------------------------------------------------------

    def health_check(self) -> Sequence[HealthStatusDTO]:
        """Execute active diagnostic health checks across all registered providers."""
        statuses: list[HealthStatusDTO] = []
        for p_name in self._registry.list_providers():
            provider = self._registry.get_provider(p_name)
            if provider is None:
                continue
            try:
                status = provider.health_check()
                statuses.append(status)
                if status.state == HealthState.HEALTHY:
                    self._record_success(p_name, status.latency_ms)
                else:
                    self._record_failure(p_name, Exception(status.error_message or "Health check unhealthy"))
            except Exception as exc:
                self._record_failure(p_name, exc)
                statuses.append(
                    HealthStatusDTO(
                        provider_name=p_name,
                        state=HealthState.UNHEALTHY,
                        latency_ms=Decimal("0.0"),
                        last_successful_query=None,
                        error_message=str(exc),
                        circuit_state=self._get_or_create_health(p_name).circuit_state,
                    )
                )
        return tuple(statuses)

    def get_provider_health(self, provider_name: str) -> ProviderHealth | None:
        """Return real-time operational health and circuit tracking for a provider."""
        with self._lock:
            key = provider_name.strip().lower()
            return self._health_records.get(key)

    def get_all_provider_health(self) -> Sequence[ProviderHealth]:
        """Return snapshot of all provider health telemetry records."""
        with self._lock:
            return tuple(self._health_records.values())

    # ------------------------------------------------------------------
    # Orchestration, Failover & Execution Mechanics
    # ------------------------------------------------------------------

    def _execute_with_failover(
        self,
        symbol: str,
        feature_name: str,
        operation_fn: Callable[[MarketDataProvider, CanonicalSymbol], T],
    ) -> T:
        """Execute operation against highest priority healthy provider with automatic failover."""
        canonical = SymbolResolver.resolve(symbol)
        candidates = self._registry.get_candidates(canonical.canonical_id, feature_name)

        if not candidates:
            raise NoMarketDataError(
                f"No registered data provider supports symbol {canonical.canonical_id!r} with feature {feature_name!r}"
            )

        last_error: Exception | None = None

        for candidate in candidates:
            p_name = candidate.provider_name.lower()

            if not self._can_use_provider(p_name):
                logger.debug(
                    "Skipping provider %r for %s (%s): circuit OPEN",
                    p_name,
                    canonical.canonical_id,
                    feature_name,
                )
                continue

            t0 = time.monotonic()
            try:
                result = operation_fn(candidate, canonical)
                elapsed_ms = Decimal(f"{(time.monotonic() - t0) * 1000:.2f}")

                # Strict validation of returned DTO
                self._validate_result_dto(result, canonical.canonical_id, feature_name)

                # Record successful telemetry
                self._record_success(p_name, elapsed_ms)
                return result

            except Exception as exc:
                elapsed_ms = Decimal(f"{(time.monotonic() - t0) * 1000:.2f}")
                self._record_failure(p_name, exc)
                last_error = exc
                logger.warning(
                    "Provider %r failed for %s (%s): %s. Attempting failover...",
                    p_name,
                    canonical.canonical_id,
                    feature_name,
                    exc,
                )

        # All candidate providers failed or were unavailable
        raise NoMarketDataError(
            f"All candidate providers failed for symbol {canonical.canonical_id!r} "
            f"with feature {feature_name!r}. Last error: {last_error}"
        ) from last_error

    def _validate_result_dto(self, dto: Any, expected_symbol: str, feature_name: str) -> None:
        """Verify returned DTO adheres to domain invariants."""
        if dto is None:
            raise DTOValidationError(f"Provider returned None for {expected_symbol} ({feature_name})")

        dto_sym = getattr(dto, "symbol", None)
        if dto_sym is not None and not isinstance(dto_sym, str):
            raise DTOValidationError(f"DTO symbol must be string, got {type(dto_sym)}")

        # Timestamp validations
        ts = getattr(dto, "timestamp", None)
        if ts is not None and ts.tzinfo is None:
            raise DTOValidationError(f"DTO timestamp for {expected_symbol} must be UTC timezone-aware")

    # ------------------------------------------------------------------
    # Circuit Breaker & Health State Machine
    # ------------------------------------------------------------------

    def _get_or_create_health(self, provider_name: str) -> ProviderHealth:
        """Internal helper to retrieve or initialize a provider's health record."""
        key = provider_name.strip().lower()
        if key not in self._health_records:
            self._health_records[key] = ProviderHealth(
                provider_name=key,
                status=HealthState.HEALTHY,
                latency_ms=Decimal("0.0"),
                success_rate=Decimal("1.0"),
                last_successful_request=None,
                failure_count=0,
                circuit_state=CircuitState.CLOSED,
                total_requests=0,
                total_successes=0,
            )
        return self._health_records[key]

    def _can_use_provider(self, provider_name: str) -> bool:
        """Check if provider's circuit breaker allows requests."""
        with self._lock:
            rec = self._get_or_create_health(provider_name)
            if rec.circuit_state == CircuitState.CLOSED:
                return True
            if rec.circuit_state == CircuitState.HALF_OPEN:
                return True

            # If OPEN, check if cooldown window has elapsed
            last_fail = self._last_failure_times.get(provider_name, 0.0)
            if time.monotonic() - last_fail >= self._circuit_cooldown_seconds:
                # Transition to HALF_OPEN to probe availability
                self._health_records[provider_name] = ProviderHealth(
                    provider_name=rec.provider_name,
                    status=HealthState.DEGRADED,
                    latency_ms=rec.latency_ms,
                    success_rate=rec.success_rate,
                    last_successful_request=rec.last_successful_request,
                    failure_count=rec.failure_count,
                    circuit_state=CircuitState.HALF_OPEN,
                    total_requests=rec.total_requests,
                    total_successes=rec.total_successes,
                )
                logger.info("Circuit for provider %r transitioned to HALF_OPEN", provider_name)
                return True

            return False

    def _record_success(self, provider_name: str, latency_ms: Decimal) -> None:
        """Update provider health upon successful request."""
        with self._lock:
            key = provider_name.strip().lower()
            rec = self._get_or_create_health(key)
            now_utc = datetime.now(timezone.utc)

            total_reqs = rec.total_requests + 1
            total_succs = rec.total_successes + 1
            success_rate = Decimal(f"{total_succs / total_reqs:.4f}")

            # Status classification based on success rate
            status = HealthState.HEALTHY if success_rate >= Decimal("0.90") else HealthState.DEGRADED

            self._health_records[key] = ProviderHealth(
                provider_name=key,
                status=status,
                latency_ms=latency_ms,
                success_rate=success_rate,
                last_successful_request=now_utc,
                failure_count=0,
                circuit_state=CircuitState.CLOSED,
                total_requests=total_reqs,
                total_successes=total_succs,
            )

    def _record_failure(self, provider_name: str, error: Exception) -> None:
        """Update provider health and evaluate circuit trip upon request failure."""
        with self._lock:
            key = provider_name.strip().lower()
            rec = self._get_or_create_health(key)
            now_mono = time.monotonic()
            self._last_failure_times[key] = now_mono

            total_reqs = rec.total_requests + 1
            total_succs = rec.total_successes
            success_rate = Decimal(f"{total_succs / total_reqs:.4f}") if total_reqs > 0 else Decimal("0.0")
            fail_count = rec.failure_count + 1

            # Trip circuit to OPEN if consecutive failures breach threshold
            if fail_count >= self._circuit_failure_threshold:
                circuit_state = CircuitState.OPEN
                status = HealthState.UNHEALTHY
                logger.warning(
                    "Circuit for provider %r tripped to OPEN (%d consecutive failures)",
                    key,
                    fail_count,
                )
            else:
                circuit_state = rec.circuit_state
                status = HealthState.DEGRADED

            self._health_records[key] = ProviderHealth(
                provider_name=key,
                status=status,
                latency_ms=rec.latency_ms,
                success_rate=success_rate,
                last_successful_request=rec.last_successful_request,
                failure_count=fail_count,
                circuit_state=circuit_state,
                total_requests=total_reqs,
                total_successes=total_succs,
            )
