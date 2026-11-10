# Master Architecture: Institutional Multi-Asset AI Trading Intelligence Platform

**Target Global Assets:**
- **Bitcoin (BTC)**: Digital Liquidity & Store of Value
- **Gold (XAUUSD)**: Real Yield Hedge & Central Bank Reserve Asset
- **Forex (USDJPY, EURUSD, GBPUSD)**: Central Bank Monetary Policy & Carry Trade
- **Equities & Indices (S&P 500, NASDAQ, Blue-Chips)**: Corporate Fundamentals & Equity Risk Premia

**AI Engine**: Powered by Google Gemini Multi-Model Orchestration (Flash, Pro, Deep Thinking).

---

## 1. System Vision & Architectural Philosophy

The objective of the platform is **not simply collecting market data**. The objective is to build an institutional AI system capable of producing **statistically grounded, risk-adjusted probability distributions, confidence bounds, explainable fiduciary trade recommendations, and verifiable reasoning**.

The architecture enforces six core engineering principles:
1. **Separation of Concerns (SoC)**: Ingestion, normalization, analytical reasoning, consensus moderation, risk gating, and presentation are strictly decoupled.
2. **Unidirectional Dependency Graph**: Higher-level orchestrators depend upon domain abstractions; domain abstractions depend on low-level data vendors. Circular dependencies are strictly forbidden.
3. **Pluggable Discovery via Provider Registry**: The universal manager never directly imports concrete providers. Providers register dynamically with a central `ProviderRegistry` and declare explicit `ProviderCapabilities`.
4. **Transport Layer Decoupling**: Providers communicate through an injected `TransportClient` Protocol, completely isolated from raw socket or HTTP libraries.
5. **Strict Provider Purity (Zero Business Logic)**: Providers strictly fetch, validate, normalize, and return immutable DTOs with provenance and freshness metadata. They contain zero trading rules, indicators, or heuristics.
6. **100% Free & Open-Source (FOSS)**: Zero paid APIs. Built on keyless public REST/WebSocket endpoints and public domain data (CFTC, FRED).

---

## 2. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Layer1["1. Presentation & Interface Layer"]
        CLI["Typer CLI (cli/main.py, cli/prompts.py)"]
        Dashboard["Rich Terminal Dashboard (cli/display.py)"]
        Exporter["Institutional Audit & Report Exporter"]
    end

    subgraph Layer2["2. Orchestration & Graph Layer (LangGraph)"]
        Dispatcher["Dynamic Asset Dispatcher"]
        Clock["MarketClock (Session & Trading Day Scheduler)"]
        Engine["LangGraph Trading Engine (graph/trading_graph.py)"]
        Checkpointer["SQLite State Checkpointer (graph/checkpointer.py)"]
        Clock --> Engine
    end

    subgraph Layer3["3. Multi-Model Gemini AI Orchestration Layer"]
        GeminiFlash["Gemini Flash: Fast Perceptual Extraction & News Filtering"]
        GeminiPro["Gemini Pro: Dialectical Bull/Bear Debate & Macro Synthesis"]
        GeminiDeep["Gemini Deep Thinking: Fiduciary Risk & Final Audit Gate"]
    end

    subgraph Layer4["4. Specialized Analytical Desks & Synthesis"]
        TechnicalDesk["Technical Analyst Desk (Indicators & Momentum)"]
        MarketStructureDesk["Market Structure Desk (L2 Order Book & Liquidity)"]
        SmartMoneyDesk["Smart Money / COT Desk (CFTC Institutional Crowding)"]
        MacroDesk["Macro Monetary Desk (Yield Curves & Inflation)"]
        NewsDesk["News Analyst Desk (Catalyst Severity & Timing)"]
        SentimentDesk["Sentiment Desk (Crowd Index & Prediction Odds)"]
        OnChainDesk["Bitcoin On-Chain Specialist (Mempool & Hashrate)"]
        
        ProbEngine["Quantitative Probability Engine (P_win, E[V], Entropy)"]
        RiskEngine["Fiduciary Risk Engine (ATR Stop-Loss & Volatility Sizing)"]
        Trader["Portfolio Trader / Execution Desk"]
    end

    subgraph Layer5["5. Universal Ingestion Infrastructure Layer"]
        Resolver["Universal SymbolResolver (CanonicalAsset Mappings)"]
        Limiter["Inbound RateLimiter (Token Bucket)"]
        Manager["MarketDataProviderManager (Universal Ingestion Orchestrator)"]
        Registry["ProviderRegistry (Capability Discovery & Filtering)"]
        HealthMgr["ProviderHealthManager (Latency EMA & Circuit Breaker)"]
        Cache["Pluggable CacheBackend (Memory / SQLite / Redis / Disk)"]
        Telemetry["Observability Sink (RequestMetricsDTO)"]

        Resolver --> Limiter
        Limiter --> Manager
        Manager <--> Registry
        Manager <--> HealthMgr
        Manager <--> Cache
        Manager --> Telemetry
    end

    subgraph Layer6["6. Decoupled Transport & FOSS Providers"]
        TransportInterface["TransportClient (Protocol)"]
        REST["RestTransportClient (urllib.request)"]
        WS["WebSocketTransportClient (Future Streaming)"]
        
        Binance["BinancePublicProvider (Spot & Futures)"]
        Coinbase["CoinbasePublicProvider (Spot)"]
        CFTC["CFTCPublicProvider (Commitments of Traders)"]
        FRED["FREDMacroProvider (Yields & Rates)"]
        Yahoo["YahooFinanceProvider (Legacy Equities & FX)"]
        Polymarket["PolymarketGammaProvider (Prediction Markets)"]
        
        TransportInterface --> REST
        TransportInterface --> WS
        Binance --> TransportInterface
        Coinbase --> TransportInterface
        CFTC --> TransportInterface
        FRED --> TransportInterface
        Yahoo --> TransportInterface
        Polymarket --> TransportInterface
    end

    Layer1 --> Layer2
    Layer2 --> Layer3
    Layer3 <--> Layer4
    Layer4 --> Layer5
    Layer5 --> Layer6
    Layer2 -.-> Checkpointer
```

---

## 3. Class Diagram: Core Contracts, Protocols & DTOs

```mermaid
classDiagram
    class TransportClient {
        <<Protocol>>
        +execute_request(endpoint_url, params, headers, timeout, **kwargs) TransportResponse
    }

    class MarketDataProvider {
        <<Abstract>>
        +provider_name: str
        +capabilities: ProviderCapabilities
        +get_supported_symbols() Sequence[str]
        +supports_feature(feature_name) bool
        +health_check() HealthStatusDTO
        +get_quote(symbol, as_of) QuoteDTO
        +get_ohlcv(symbol, timeframe, start, end) OHLCVSeriesDTO
        +get_orderbook(symbol, depth, as_of) OrderBookDTO
        +get_funding_rate(symbol, as_of) FundingRateDTO
    }

    class ProviderRegistry {
        <<Protocol>>
        +register(provider, capabilities) None
        +get_provider(name) MarketDataProvider
        +filter_by_capability(feature) Sequence[MarketDataProvider]
        +filter_by_asset_class(asset_class) Sequence[MarketDataProvider]
        +filter_by_symbol(canonical_symbol) Sequence[MarketDataProvider]
        +get_candidates(symbol, feature, min_health) Sequence[MarketDataProvider]
    }

    class MarketDataProviderManager {
        <<Protocol>>
        +get_quote(symbol, as_of) QuoteDTO
        +get_ohlcv(symbol, timeframe, start, end) OHLCVSeriesDTO
        +get_orderbook(symbol, depth, as_of) OrderBookDTO
        +get_funding_rate(symbol, as_of) FundingRateDTO
        +health_check() Sequence[HealthStatusDTO]
    }

    class MarketClock {
        <<Protocol>>
        +is_market_open(asset, at_time) bool
        +next_open(asset, at_time) datetime
        +next_close(asset, at_time) datetime
        +current_session(asset, at_time) SessionType
        +trading_day(asset, at_time) date
    }

    class SymbolResolver {
        <<Protocol>>
        +resolve(raw_input) CanonicalSymbol
        +to_vendor_symbol(canonical, vendor_name) str
        +from_vendor_symbol(vendor_symbol, vendor_name) CanonicalSymbol
    }

    class CacheBackend {
        <<Protocol>>
        +get(key) bytes
        +set(key, value, ttl_seconds) None
        +delete(key) None
        +clear() None
    }

    class QuoteDTO {
        +symbol: str
        +price: Decimal
        +bid: Decimal
        +ask: Decimal
        +bid_size: Decimal
        +ask_size: Decimal
        +volume_24h: Decimal
        +timestamp: datetime
        +provenance: ProvenanceMetadata
        +freshness: FreshnessMetadata
        +schema_version: str
    }

    class ProviderCapabilities {
        +asset_classes: tuple
        +supported_features: tuple
        +supported_timeframes: tuple
        +supported_symbols: tuple
        +supports_websocket: bool
        +supports_orderbook: bool
        +supports_funding_rate: bool
        +latency_class: str
        +rate_limit_per_minute: int
        +reliability_score: Decimal
    }

    class ProviderHealthModel {
        +provider_name: str
        +health_score: Decimal
        +average_latency_ms: Decimal
        +availability: Decimal
        +timeout_percentage: Decimal
        +rate_limit_frequency: Decimal
        +circuit_state: str
    }

    MarketDataProvider ..> TransportClient : uses
    ProviderRegistry o-- MarketDataProvider : aggregates
    MarketDataProviderManager o-- ProviderRegistry : queries
    MarketDataProviderManager o-- CacheBackend : caches
    MarketDataProvider --> ProviderCapabilities : declares
    QuoteDTO --> ProvenanceMetadata : contains
    QuoteDTO --> FreshnessMetadata : contains
```

---

## 4. Sequence Diagram: Dynamic Provider Discovery, Health Ranking & Failover

```mermaid
sequenceDiagram
    autonumber
    actor Engine as Decision Pipeline Node
    participant Resolver as Universal SymbolResolver
    participant Limiter as Inbound RateLimiter
    participant Manager as MarketDataProviderManager
    participant Cache as CacheBackend
    participant Registry as ProviderRegistry
    participant Health as ProviderHealthManager
    participant Binance as BinancePublicProvider
    participant Coinbase as CoinbasePublicProvider
    participant Transport as TransportClient

    Engine->>Resolver: resolve("BTC")
    Resolver-->>Engine: CanonicalSymbol(id="BTC/USD", class=CRYPTO)
    
    Engine->>Limiter: request_ohlcv("BTC/USD", timeframe="1h")
    Limiter->>Limiter: Token bucket quota check
    Limiter->>Manager: get_ohlcv("BTC/USD", "1h")
    
    Manager->>Cache: get("ohlcv:BTC/USD:1h")
    alt Cache Hit
        Cache-->>Manager: cached serialized bytes
        Manager-->>Engine: return OHLCVSeriesDTO (with Freshness metadata)
    else Cache Miss
        Manager->>Registry: get_candidates(symbol="BTC/USD", feature="ohlcv")
        Registry-->>Manager: [BinanceProvider, CoinbaseProvider]
        
        Manager->>Health: rank_candidates([Binance, Coinbase])
        Health-->>Manager: [Binance (Rank: 0.94), Coinbase (Rank: 0.91)]
        
        Note over Manager,Binance: Attempt Primary: Binance
        Manager->>Binance: get_ohlcv("BTCUSDT", "1h")
        Binance->>Transport: execute_request("https://api.binance.com/api/v3/klines")
        
        alt Binance Success
            Transport-->>Binance: HTTP 200 OK (raw JSON)
            Binance->>Binance: validate schema & normalize to OHLCVSeriesDTO
            Binance-->>Manager: OHLCVSeriesDTO
            Manager->>Health: record_success("binance", latency=42.1ms)
            Manager->>Cache: set("ohlcv:BTC/USD:1h", bytes, ttl=3600)
            Manager-->>Engine: return OHLCVSeriesDTO
        else Binance Times Out / 5xx Error
            Transport-->>Binance: HTTP 500 / Timeout
            Binance-->>Manager: raise VendorUnavailableError
            Manager->>Health: record_failure("binance", TimeoutError)
            
            Note over Manager,Coinbase: Automatic Failover to Secondary: Coinbase
            Manager->>Coinbase: get_ohlcv("BTC-USD", "1h")
            Coinbase->>Transport: execute_request("https://api.exchange.coinbase.com/products/BTC-USD/candles")
            Transport-->>Coinbase: HTTP 200 OK (raw JSON)
            Coinbase->>Coinbase: validate schema & normalize to OHLCVSeriesDTO
            Coinbase-->>Manager: OHLCVSeriesDTO
            Manager->>Health: record_success("coinbase", latency=58.3ms)
            Manager->>Cache: set("ohlcv:BTC/USD:1h", bytes, ttl=3600)
            Manager-->>Engine: return OHLCVSeriesDTO (provenance: coinbase)
        end
    end
```

---

## 5. Multi-Model Gemini AI Orchestration Layer

The platform leverages Google Gemini's specialized model hierarchy to optimize latency, token efficiency, dialectical depth, and fiduciary safety:

```mermaid
flowchart TD
    TaskRouter{"Analytical Task Dispatcher"}
    
    subgraph Tier1["Tier 1: Gemini Flash (Fast Perceptual & Extraction)"]
        FlashModel["gemini-2.5-flash: Low Latency / High Throughput"]
        NewsFilter["News Relevance Filtering & Entity Extraction"]
        SentimentTagger["Crowd Sentiment & Binary Odds Scoring"]
        IndicatorParser["Mathematical Indicator Anomaly Tagging"]
    end
    
    subgraph Tier2["Tier 2: Gemini Pro (Dialectical Reasoning & Narrative)"]
        ProModel["gemini-2.5-pro: Extended Context & Dialectical Logic"]
        BullPersona["Bullish Researcher Persona (Thesis Defense)"]
        BearPersona["Bearish Researcher Persona (Downside Stress-Testing)"]
        MacroSynthesizer["Cross-Asset Macro Regime Synthesis"]
    end
    
    subgraph Tier3["Tier 3: Gemini Deep Thinking (Fiduciary Audit Gate)"]
        ThinkingModel["gemini-2.5-pro-thinking / o3-mini: Deep Multi-Step Reasoning"]
        RiskCommittee["Multi-Persona Risk Gate (Aggressive / Conservative / Neutral)"]
        ProbabilityAuditor["Mathematical Expected Value & Entropy Audit"]
        FinalAuthorization["Final Fiduciary Trade Authorization"]
    end

    TaskRouter -->|Perceptual / High Volume| Tier1
    TaskRouter -->|Dialectical Debate| Tier2
    TaskRouter -->|Fiduciary Audit & Risk| Tier3
    
    Tier1 --> NewsFilter
    Tier1 --> SentimentTagger
    Tier1 --> IndicatorParser
    
    Tier2 --> BullPersona
    Tier2 --> BearPersona
    Tier2 --> MacroSynthesizer
    
    Tier3 --> RiskCommittee
    Tier3 --> ProbabilityAuditor
    Tier3 --> FinalAuthorization
```
