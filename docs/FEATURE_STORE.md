# Centralized Feature Store Specification

Version: 1.0.0  
Status: Architectural Blueprint (Phase 2)  
Audience: Quantitative Analysts, Feature Engineers, AI Agent Developers  

---

## 1. Executive Summary & Purpose

In a multi-agent AI trading architecture, distinct agents (e.g. Technical Analyst, Smart Money Analyst, Risk Manager, Execution Planner) often require identical derived mathematical indicators and market structure features.

Calculating technical indicators (such as EMA, RSI, ATR) or complex Smart Money Concepts (such as Fair Value Gaps and Order Blocks) separately within each agent results in:
- Significant redundant CPU computation.
- Inconsistent values if agents sample slightly different data snapshots (lookahead or snapshot bias).
- Bloated token counts and delayed prompt execution.

The **Centralized Feature Store** guarantees:
1. **Single Point of Computation**: Features are computed once upon candle completion or tick threshold and served to all agents.
2. **Point-in-Time Correctness**: Every feature record is timestamped to the exact millisecond of the data bar, eliminating lookahead bias in backtests and live execution.
3. **Multi-Asset & Multi-Timeframe Indexing**: Features are addressed by `(canonical_symbol, timeframe, feature_key, timestamp)`.
4. **Zero-Copy In-Memory Cache**: Low-latency retrieval with bounded memory consumption and automatic TTL-based pruning.

---

## 2. Supported Feature Taxonomy

### A. Mathematical & Statistical Indicators
- **Exponential Moving Averages (`EMA`)**: Periods 9, 21, 50, 200 for dynamic trend alignment.
- **Relative Strength Index (`RSI`)**: 14-period Wilder's smoothed momentum with oversold/overbought zone detection.
- **Average True Range (`ATR`)**: Volatility quantification used for dynamic stop-loss distance.
- **Average Directional Index (`ADX`)**: Trend strength indicator ($0-100$) distinguishing ranging vs trending regimes.
- **Volume-Weighted Average Price (`VWAP`)**: Session and rolling anchoring for institutional execution benchmarks.
- **Realized Volatility (`VOL_REALIZED`)**: 30-day annualized log-return standard deviation.
- **Cross-Asset Correlation (`CORR_MATRIX`)**: Rolling 30-day Pearson correlation against BTC, Gold, SPX, and DXY.

### B. Smart Money Concepts (SMC) & Institutional Price Action
- **Break of Structure (`BOS`)**: Price closing cleanly beyond recent swing highs or swing lows in the direction of the dominant trend.
- **Change of Character (`CHoCH`)**: First structural break against the dominant trend indicating potential market reversal.
- **Fair Value Gaps (`FVG`)**: 3-candle imbalance zones where price traded inefficiently (Candle 1 High $<$ Candle 3 Low in bullish FVG; Candle 1 Low $>$ Candle 3 High in bearish FVG).
- **Order Blocks (`OB`)**: Last opposing candle before aggressive institutional displacement that leaves an unfilled liquidity zone.
- **Liquidity Sweeps (`SWEEP`)**: False breakout taking buy-side or sell-side liquidity followed by an immediate aggressive rejection back into the range.
- **Volume Profile**:
  - **POC (Point of Control)**: Highest traded volume price level for the session.
  - **VAH (Value Area High)**: Upper boundary containing 70% of total session volume.
  - **VAL (Value Area Low)**: Lower boundary containing 70% of total session volume.

---

## 3. Data Contracts & Feature Record Schemas

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


class FeatureType(Enum):
    INDICATOR = "indicator"
    MARKET_STRUCTURE = "market_structure"
    LIQUIDITY = "liquidity"
    MACRO_DERIVED = "macro_derived"


@dataclass(frozen=True)
class FeatureValue:
    """Immutable single feature observation with point-in-time timestamp."""
    feature_name: str
    symbol: str
    timeframe: str
    timestamp: datetime
    value: Decimal
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("FeatureValue timestamp must be timezone-aware (UTC).")


@dataclass(frozen=True)
class OrderBlockRecord:
    symbol: str
    timeframe: str
    timestamp: datetime
    is_bullish: bool
    top_price: Decimal
    bottom_price: Decimal
    mitigated: bool = False
    volume_surge_ratio: Decimal = Decimal("1.0")


@dataclass(frozen=True)
class FairValueGapRecord:
    symbol: str
    timeframe: str
    timestamp: datetime
    is_bullish: bool
    upper_bound: Decimal
    lower_bound: Decimal
    mitigated: bool = False
    mitigated_at: Optional[datetime] = None


@dataclass(frozen=True)
class MarketStructureSnapshot:
    """Comprehensive SMC snapshot consumed by the Gemini reasoning pipeline."""
    symbol: str
    timeframe: str
    as_of: datetime
    last_bos_direction: Optional[str]  # "BULLISH", "BEARISH", None
    last_choch_timestamp: Optional[datetime]
    active_bullish_fvgs: Tuple[FairValueGapRecord, ...] = ()
    active_bearish_fvgs: Tuple[FairValueGapRecord, ...] = ()
    active_bullish_obs: Tuple[OrderBlockRecord, ...] = ()
    active_bearish_obs: Tuple[OrderBlockRecord, ...] = ()
    session_poc: Optional[Decimal] = None
    session_vah: Optional[Decimal] = None
    session_val: Optional[Decimal] = None
```

---

## 4. Feature Store Protocol

```python
@runtime_checkable
class FeatureStore(Protocol):
    """Protocol for reading, writing, and querying derived market features."""

    def register_feature(self, feature: FeatureValue) -> None:
        """Persist a single feature observation."""
        ...

    def get_feature(
        self,
        symbol: str,
        feature_name: str,
        timeframe: str,
        as_of: Optional[datetime] = None
    ) -> Optional[FeatureValue]:
        """Retrieve the latest point-in-time value on or before `as_of`."""
        ...

    def get_market_structure(
        self,
        symbol: str,
        timeframe: str,
        as_of: Optional[datetime] = None
    ) -> MarketStructureSnapshot:
        """Retrieve the composite SMC structural snapshot."""
        ...

    def get_feature_vector(
        self,
        symbol: str,
        timeframe: str,
        feature_names: List[str],
        as_of: Optional[datetime] = None
    ) -> Dict[str, Optional[Decimal]]:
        """Retrieve a key-value dictionary of indicator features for LLM prompt embedding."""
        ...

    def invalidate_cache(self, symbol: str, timeframe: Optional[str] = None) -> None:
        """Manually purge invalidated feature sets."""
        ...
```

---

## 5. Storage Model, Refresh & Invalidation Policy

### Storage Hierarchy
1. **L1 In-Memory Ring Buffer**:
   - Holds the last 1,000 candles worth of features per symbol/timeframe tuple.
   - Access latency: $< 50\ \mu s$.
2. **L2 On-Disk Columnar Cache (Parquet/Arrow - Future)**:
   - Persists historical features across system restarts.

### Refresh Policy
- **Bar-Close Recalculation (Strict Default)**:
  - Technical indicators (RSI, ATR, ADX, EMA) and SMC structures (BOS, CHoCH, FVG) are updated **only when an OHLCV bar closes**. This eliminates false signals from intra-bar noise and repainting.
- **Real-Time VWAP & Volatility**:
  - Anchored VWAP and rolling volatility update on intra-bar trade ticks or every 10 seconds.

### Cache Invalidation Rules
- If historical OHLCV data is revised (e.g. exchange restatement or network gap fill), all derived features strictly greater than the earliest restated timestamp are evicted and scheduled for recalculation.
- Memory eviction uses an LRU (Least Recently Used) policy when total cache entries exceed configured thresholds.
