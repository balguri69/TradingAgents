# Universal Data Provider Interface Specification

*Document Version: 3.0.0 | Status: Architectural Contract | Scope: Multi-Asset Ingestion & Metadata*

---

## 1. Architectural Philosophy & Invariants

The `MarketDataProvider` architecture establishes an institutional, vendor-agnostic ingestion contract across all supported global assets: **Crypto (BTC), Commodities (XAUUSD), Foreign Exchange (USDJPY, EURUSD, GBPUSD), and Equities/Indices**.

### Core Invariants:
1. **Strict Provider Purity (Zero Business Logic)**: Providers must **never** contain trading logic, technical indicators, or investment heuristics. Their sole responsibility is fetching, validating, normalizing, and returning standardized DTOs.
2. **Transport Decoupling**: Providers communicate exclusively through an injected `TransportClient` Protocol, isolating business normalization from socket or HTTP protocols.
3. **Canonical Symbol Operation**: Providers never convert symbols internally. They receive the vendor-specific symbol from the `SymbolResolver` or query the resolver.
4. **Declarative Provider Capabilities**: Each provider advertises a rich `ProviderCapabilities` entity instead of hardcoded capability checks.
5. **Full Provenance & Data Freshness Tracking**: Every DTO carries immutable provenance and freshness metadata so the AI engine always knows where data originated and how fresh it is.
6. **Schema Versioning**: Every DTO embeds `schema_version` to guarantee backward-compatible evolution.
7. **Cache-Agnostic Transport Hooks**: Caching is abstracted via `CacheBackend`, supporting In-Memory, SQLite, Redis, and Disk backends without coupling transport clients to concrete storage engines.
8. **Point-in-Time Backtesting Compatibility**: Live and backtesting operations use identical method signatures via point-in-time `as_of` parameters.

---

## 2. Core Metadata Entities: Provenance, Freshness & Schema Versioning

### 2.1 Provenance Metadata
The AI reasoning engine must always trace the origin of every factual observation:

```python
@dataclass(frozen=True)
class ProvenanceMetadata:
    """Immutable audit trail of data origin and transport collection."""
    provider_name: str          # e.g., "binance", "coinbase", "cftc", "fred"
    exchange: str               # e.g., "Binance Spot", "Coinbase Exchange", "COMEX"
    normalized_symbol: str      # Canonical ID (e.g. "BTC/USD", "XAU/USD")
    requested_symbol: str       # Raw symbol user or system requested (e.g. "BTC")
    asset_class: str            # "crypto", "commodity", "forex", "stock", "index"
    timeframe: str | None       # "1m", "1h", "1d", or None for tick/snapshot
    request_id: str             # UUID tracing the query lifecycle
    request_timestamp: datetime # UTC timestamp when query was dispatched
    collection_timestamp: datetime # UTC timestamp when response was parsed
    schema_version: str = "1.0.0"
```

### 2.2 Data Freshness Metadata
Stale data in financial markets leads to severe miscalculations. Every DTO carries freshness metrics:

```python
@dataclass(frozen=True)
class FreshnessMetadata:
    """Quantitative freshness and latency metrics of an observation."""
    source_timestamp: datetime   # Exchange matching engine timestamp
    received_timestamp: datetime # Application ingestion timestamp
    age_seconds: Decimal         # (received_timestamp - source_timestamp) in seconds
    is_stale: bool               # Evaluated against asset-class SLA threshold
    freshness_score: Decimal     # Normalized [0.0 = completely stale to 1.0 = immediate]
```

### 2.3 Schema Versioning & Evolution Protocol
All DTOs expose `schema_version: str = "1.0.0"`.
- **Additive Evolution**: New fields must have default values (`None` or default factory), ensuring existing consumers parsing serialized representations do not break.
- **Breaking Changes**: If a field type changes or is removed, the major version increments (e.g. `2.0.0`), and a schema migration adapter is provided.

---

## 3. Universal Provider Capabilities Model (`ProviderCapabilities`)

Providers declare capabilities declaratively, enabling the `ProviderRegistry` and `MarketDataProviderManager` to perform dynamic query routing without hardcoded checks:

```python
@dataclass(frozen=True)
class ProviderCapabilities:
    """Comprehensive institutional capability declaration for a data provider."""
    asset_classes: tuple[str, ...]               # e.g. ("crypto",), ("forex", "commodity")
    supported_features: tuple[str, ...]          # e.g. ("quote", "ohlcv", "orderbook", "funding_rate")
    supported_timeframes: tuple[str, ...]        # e.g. ("1m", "5m", "15m", "1h", "4h", "1d")
    supported_symbols: tuple[str, ...]          # List of canonical symbols supported
    supports_websocket: bool = False             # Capable of persistent streaming
    supports_orderbook: bool = False             # Provides L2 market depth
    supports_funding_rate: bool = False          # Provides perpetual swap funding rates
    supports_macro: bool = False                 # Provides macroeconomic indicators
    supports_news: bool = False                  # Provides news and wire reports
    supports_sentiment: bool = False             # Provides crowd/social sentiment
    supports_onchain: bool = False               # Provides blockchain on-chain metrics
    supports_cot: bool = False                   # Provides CFTC COT positioning
    historical_depth_days: int = 365             # Historical lookback horizon
    latency_class: str = "standard"              # "ultra_low" (<50ms), "low" (<200ms), "standard"
    update_frequency_seconds: Decimal = Decimal("1.0") # Refresh rate
    rate_limit_per_minute: int = 1200            # Upstream rate limit budget
    cacheable: bool = True                       # Safe to cache downstream
    reliability_score: Decimal = Decimal("0.99") # Historical uptime SLA (0.0 to 1.0)
```

---

## 4. Rich Provider Health Model & Dynamic Ranking

A simple binary healthy/unhealthy flag is insufficient for institutional execution. The health manager maintains a continuous multi-dimensional health model:

```python
@dataclass(frozen=True)
class ProviderHealthModel:
    """Rich multi-dimensional operational telemetry for provider ranking."""
    provider_name: str
    health_score: Decimal             # Normalized aggregate score [0.0 to 1.0]
    average_latency_ms: Decimal       # Exponential Moving Average (EMA) of latency
    availability: Decimal             # Successful queries / total queries [0.0 to 1.0]
    timeout_percentage: Decimal       # Timeouts / total queries [0.0 to 1.0]
    rate_limit_frequency: Decimal     # HTTP 429 encounters / total queries
    success_rate: Decimal             # Recent window success rate [0.0 to 1.0]
    failure_rate: Decimal             # Recent window failure rate [0.0 to 1.0]
    last_successful_request: datetime | None
    last_failed_request: datetime | None
    circuit_state: str = "closed"     # "closed", "open", "half_open"
```

### Dynamic Provider Ranking Formula
The `ProviderManager` ranks candidate providers using a weighted utility function:

$$\text{Rank Score} = (\text{Health Score} \times 0.40) + (\text{Reliability Score} \times 0.30) + \left(1 - \frac{\text{Latency}}{\text{MaxLatency}}\right) \times 0.20 + (\text{Freshness} \times 0.10)$$

Providers with active open circuit breakers are automatically assigned $\text{Rank Score} = 0.0$ and bypassed.

---

## 5. Cache Architecture (Interface Specification)

The transport and ingestion layer is decoupled from concrete storage engines via the `CacheBackend` Protocol:

```python
@runtime_checkable
class CacheBackend(Protocol):
    """Abstract protocol for pluggable cache storage."""
    
    def get(self, key: str) -> bytes | None:
        """Retrieve cached payload bytes or return None on cache miss."""
        ...
        
    def set(self, key: str, value: bytes, ttl_seconds: float) -> None:
        """Store payload with explicit time-to-live."""
        ...
        
    def delete(self, key: str) -> None:
        """Invalidate specific cache key."""
        ...
        
    def clear(self) -> None:
        """Flush cache namespace."""
        ...
```

### Supported Storage Engines:
1. **Memory (`InMemoryCacheBackend`)**: Ultra-low latency volatile dictionary cache (ideal for quotes: TTL 5s, order books: TTL 2s).
2. **SQLite (`SQLiteCacheBackend`)**: Zero-dependency persistent disk cache for historical OHLCV bars and CFTC reports.
3. **Redis (`RedisCacheBackend` - Future Optional)**: Distributed shared cache for multi-process or cluster deployments.
4. **Filesystem Disk (`DiskCacheBackend`)**: Raw JSON/text payload cache preserving existing `files.py` compatibility.

---

## 6. Provider Registry Specification

The `ProviderRegistry` acts as an Inversion of Control (IoC) discovery and query engine:

```python
@runtime_checkable
class ProviderRegistry(Protocol):
    """Universal discovery and capability filtering registry."""

    def register(self, provider: MarketDataProvider, capabilities: ProviderCapabilities) -> None:
        """Register provider with explicit capability declaration."""
        ...

    def get_provider(self, provider_name: str) -> MarketDataProvider | None:
        """Retrieve provider instance by name."""
        ...

    def filter_by_capability(self, feature_name: str) -> Sequence[MarketDataProvider]:
        """Return providers declaring support for a feature (e.g. 'funding_rate')."""
        ...

    def filter_by_asset_class(self, asset_class: str) -> Sequence[MarketDataProvider]:
        """Return providers capable of serving an asset class (e.g. 'crypto', 'forex')."""
        ...

    def filter_by_symbol(self, canonical_symbol: str) -> Sequence[MarketDataProvider]:
        """Return providers declaring explicit support for a canonical symbol."""
        ...

    def get_candidates(
        self,
        canonical_symbol: str,
        feature_name: str,
        min_health_score: Decimal = Decimal("0.70"),
    ) -> Sequence[MarketDataProvider]:
        """Return candidate providers matching symbol, feature, and minimum health, ranked automatically."""
        ...
```
