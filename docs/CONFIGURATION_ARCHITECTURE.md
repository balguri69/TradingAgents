# Centralized Configuration Architecture Specification

Version: 1.0.0  
Status: Architectural Blueprint (Phase 2)  
Audience: DevOps Engineers, System Architects, Quant Developers  

---

## 1. Executive Summary & Design Principles

Hardcoded constants (such as endpoint URLs, timeout durations, risk percentages, indicator periods, or symbol aliases) inside business logic represent severe technical debt. In an institutional trading system, configurations must be declarative, modular, environment-aware, and strictly validated at platform boot.

### Architectural Principles
1. **Zero Hardcoded Constants**: Every parameter, threshold, URL, weight, and credential reference lives in declarative YAML configuration files.
2. **Modular File Separation**: Configurations are split into domain-specific modules rather than one monolithic file.
3. **Strict Schema & Type Validation**: All configuration files are deserialized into strongly typed, immutable dataclasses. Any missing required parameter or type mismatch halts startup immediately.
4. **Environment Variable Interpolation**: Sensitive secrets (API keys) and environment overrides are injected dynamically via `${ENV_VAR:default_value}` syntax.
5. **Zero Paid Services**: All default configurations use 100% free, public endpoints (e.g. Binance Spot/Futures, Coinbase Public, Yahoo Finance, FRED, CFTC Commitments of Traders, Blockchain.info / Mempool.space).

---

## 2. Configuration Directory Hierarchy

```
config/
├── providers.yaml      # Market data endpoints, rate limits, feature flags, priority
├── risk.yaml           # Account risk limits, max drawdown, single-asset caps, VaR thresholds
├── features.yaml       # Indicator parameters (EMA, RSI, ATR), SMC thresholds, lookbacks
├── models.yaml         # Gemini model parameters (flash, pro, temperature, safety settings)
├── symbols.yaml        # Multi-asset universe, lot sizes, tick steps, vendor symbol mappings
├── cache.yaml          # In-memory and disk cache TTLs, eviction policies, capacity
└── news.yaml           # RSS feeds, macro economic calendar sources, sentiment weights
```

---

## 3. Modular YAML Specifications & Schemas

### A. `providers.yaml` (Market Data Endpoints & Discovery)
```yaml
version: "1.0"
providers:
  binance_spot:
    enabled: true
    priority: 1
    asset_classes: ["CRYPTO"]
    base_url: "https://api.binance.com"
    connect_timeout_seconds: 3.0
    read_timeout_seconds: 5.0
    rate_limit_requests_per_minute: 1200
    capabilities:
      quotes: true
      ohlcv: true
      orderbook: true
      funding_rate: false
      news: false

  binance_futures:
    enabled: true
    priority: 1
    asset_classes: ["CRYPTO"]
    base_url: "https://fapi.binance.com"
    connect_timeout_seconds: 3.0
    read_timeout_seconds: 5.0
    rate_limit_requests_per_minute: 1200
    capabilities:
      quotes: true
      ohlcv: true
      orderbook: true
      funding_rate: true
      news: false

  yahoo_finance:
    enabled: true
    priority: 2
    asset_classes: ["EQUITY", "FOREX", "COMMODITY", "INDEX"]
    base_url: "https://query1.finance.yahoo.com"
    connect_timeout_seconds: 5.0
    read_timeout_seconds: 10.0
    rate_limit_requests_per_minute: 360
    capabilities:
      quotes: true
      ohlcv: true
      orderbook: false
      funding_rate: false
      news: true

  fred_macro:
    enabled: true
    priority: 1
    asset_classes: ["MACRO"]
    base_url: "https://fred.stlouisfed.org"
    connect_timeout_seconds: 5.0
    read_timeout_seconds: 10.0
    capabilities:
      macro_series: true
```

### B. `risk.yaml` (Portfolio & Execution Risk Limits)
```yaml
version: "1.0"
risk:
  account:
    max_daily_drawdown_percent: 2.0
    hard_kill_switch_action: "CANCEL_ALL_AND_HALT"
    max_gross_leverage: 3.0
    max_single_asset_nav_percent: 25.0
    max_single_trade_risk_bps: 100.0  # 1.0% NAV risk per trade
  
  invalidation:
    enforce_mandatory_stop_loss: true
    min_risk_reward_ratio: 2.0         # Reject any proposal < 1:2.0 R:R
    max_slippage_tolerance_bps: 15.0

  circuit_breakers:
    consecutive_loss_limit: 3
    cool_off_period_minutes: 60
```

### C. `features.yaml` (Indicator & Structure Calculation)
```yaml
version: "1.0"
features:
  indicators:
    ema_periods: [9, 21, 50, 200]
    rsi:
      period: 14
      overbought_threshold: 70.0
      oversold_threshold: 30.0
    atr:
      period: 14
      multiplier_stop_loss: 1.5
    adx:
      period: 14
      trend_threshold: 25.0

  market_structure:
    swing_lookback_bars: 5
    fvg_min_size_bps: 5.0
    order_block_volume_surge_ratio: 1.5
    volume_profile:
      bins: 100
      value_area_percent: 70.0
```

### D. `models.yaml` (Gemini Orchestration & Prompts)
```yaml
version: "1.0"
models:
  gemini_flash:
    model_name: "gemini-1.5-flash"
    api_key: "${GEMINI_API_KEY:}"
    temperature: 0.2
    max_output_tokens: 1024
    role: "Perception, News Summarization, Fast Feature Filtering"

  gemini_pro:
    model_name: "gemini-1.5-pro"
    api_key: "${GEMINI_API_KEY:}"
    temperature: 0.1
    max_output_tokens: 4096
    role: "Dialectical Bull/Bear Debate, Multi-Asset Reasoning"

  gemini_risk_auditor:
    model_name: "gemini-1.5-pro"
    api_key: "${GEMINI_API_KEY:}"
    temperature: 0.0
    max_output_tokens: 2048
    role: "Fiduciary Review, Hallucination Check, Invalidation Verification"
```

### E. `cache.yaml` (Cache TTLs & Invalidation)
```yaml
version: "1.0"
cache:
  backend: "in_memory"
  max_memory_mb: 512
  ttl_seconds:
    realtime_quotes: 1.0
    orderbook_l2: 2.0
    funding_rates: 300.0        # 5 minutes
    ohlcv_1m: 60.0              # 1 minute
    ohlcv_1h: 3600.0            # 1 hour
    macro_series: 86400.0       # 24 hours
    news_sentiment: 1800.0      # 30 minutes
```

---

## 4. Configuration Loader Protocol & Schema Validator

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Protocol, runtime_checkable
from pathlib import Path


@runtime_checkable
class ConfigLoader(Protocol):
    """Protocol for reading, parsing, validating, and injecting platform configurations."""

    def load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """Load YAML file with environment variable interpolation (${VAR:default})."""
        ...

    def get_providers_config(self) -> Any:
        """Return validated ProvidersConfig typed dataclass."""
        ...

    def get_risk_config(self) -> Any:
        """Return validated RiskConfig typed dataclass."""
        ...

    def get_features_config(self) -> Any:
        """Return validated FeaturesConfig typed dataclass."""
        ...

    def get_models_config(self) -> Any:
        """Return validated ModelsConfig typed dataclass."""
        ...
```
