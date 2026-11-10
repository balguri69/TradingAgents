# MASTER IMPLEMENTATION ROADMAP: INSTITUTIONAL TRADING INTELLIGENCE PLATFORM
**Target Assets: BTC (Cryptocurrency), XAUUSD (Spot Gold), USDJPY (Foreign Exchange)**  
*Document Version: 1.0.0 | Status: Active Project Baseline | Single Source of Truth (SSOT)*

---

## 1. Roadmap Architecture & Execution Strategy

This document serves as the **Single Source of Truth (SSOT)** for transitioning the repository from a corporate equity tool into an **Institutional Trading Intelligence Platform**.

### Core Governance Rules
1. **Zero Paid APIs**: All features must function either with zero authentication (keyless public REST, Atom/RSS feeds) or with free-tier registration (FRED).
2. **Modular Architecture**: New asset classes and analytical capabilities are implemented via pluggable adapters and personas without rewriting the core LangGraph engine.
3. **Incremental Delivery**: Features are delivered in test-driven, verifiable increments with zero breaking changes to existing functionality.

---

## 2. Milestone Overview

```mermaid
gantt
    title Institutional Multi-Asset Platform Implementation Roadmap
    dateFormat  YYYY-MM-DD
    
    section Milestone 1: Multi-Asset Ingestion
    M1.1 Universal Multi-Asset Normalizer    :crit, m1_1, 2026-11-10, 2d
    M1.2 Free CCXT Public Crypto Adapter    :crit, m1_2, after m1_1, 3d
    M1.3 Public Domain CFTC COT Adapter     :high, m1_3, after m1_2, 3d
    M1.4 Keyless Bitcoin On-Chain Adapter   :high, m1_4, after m1_3, 2d
    M1.5 FRED Macro & Sovereign Rates       :crit, m1_5, after m1_4, 2d
    
    section Milestone 2: Analytical Desks
    M2.1 Macro Monetary & Rates Analyst     :crit, m2_1, after m1_5, 4d
    M2.2 Institutional Technical Analyst    :high, m2_2, after m2_1, 3d
    M2.3 Bitcoin On-Chain Specialist        :high, m2_3, after m2_2, 3d
    M2.4 Institutional Positioning Desk     :medium, m2_4, after m2_3, 3d
    M2.5 Multi-Asset Sentiment & Social     :medium, m2_5, after m2_4, 2d

    section Milestone 3: Execution & Sizing
    M3.1 Institutional Position Sizing Engine:crit, m3_1, after m2_5, 3d
    M3.2 Multi-Asset Alpha Settlement Engine :high, m3_2, after m3_1, 3d
    M3.3 24/7 & Continuous Calendar System  :high, m3_3, after m3_2, 2d

    section Milestone 4: Graph & Synthesis
    M4.1 Dynamic Asset LangGraph Dispatcher :crit, m4_1, after m3_3, 3d
    M4.2 Institutional Pydantic Schemas     :high, m4_2, after m4_1, 2d
    M4.3 Asset-Native Fiduciary Prompts     :high, m4_3, after m4_2, 3d

    section Milestone 5: UI & Verification
    M5.1 Institutional CLI & Rich Display   :medium, m5_1, after m4_3, 3d
    M5.2 Multi-Asset HTML Report Engine     :low, m5_2, after m5_1, 2d
    M5.3 Anti-Lookahead End-to-End Suite    :crit, m5_3, after m5_2, 4d
```

---

## 3. Detailed Feature Specifications

### Milestone 1: Multi-Asset Core Ingestion & Normalization

#### Feature 1.1: Universal Multi-Asset Symbol & Asset Normalizer
- **Description**: Extend symbol resolution to deterministically classify and normalize raw user inputs into canonical vendor symbols:
  - `BTC`, `BTCUSD`, `BTC-USD`, `BTCUSDT`, `BTC/USDT` $\rightarrow$ `BTC-USD` (Yahoo) / `BTC/USDT` (CCXT).
  - `XAUUSD`, `XAUUSD+`, `XAU`, `GOLD`, `XAU/USD` $\rightarrow$ `GC=F` (Yahoo) / `XAU/USD` (Cash spot).
  - `USDJPY`, `USDJPY+`, `USD/JPY`, `USD-JPY` $\rightarrow$ `USDJPY=X` (Yahoo) / `USD/JPY` (Interbank FX).
  - Introduces `classify_asset(symbol)` returning `"crypto"`, `"commodity"`, `"forex"`, or `"stock"`.
- **Priority**: **Critical**
- **Required Data Sources**: Local syntactic parser (no external network required).
- **Required Providers**: None.
- **Free Alternatives**: N/A (Pure Python regex & string normalization).
- **Test Coverage**: Unit tests covering 30+ symbol variations, alias checks, slash stripping, and directory traversal safety.
- **Dependencies**: `tradingagents/dataflows/symbols.py`.
- **Estimated Complexity**: Low (1-2 days).
- **Completion Status**: **Completed** (Implemented & Verified in `symbols.py` and `test_multiasset_symbols.py`).

---

#### Feature 1.2: Free CCXT Public Crypto Market Data Adapter
- **Description**: Connects to Binance and Coinbase public REST endpoints via `ccxt` without API keys to fetch spot OHLCV, order book spread, and perpetual funding rates for BTC.
- **Priority**: **Critical**
- **Required Data Sources**: Public exchange REST endpoints (Binance `/api/v3/klines`, `/fapi/v1/fundingRate`).
- **Required Providers**: Open-source `ccxt` library.
- **Free Alternatives**: Direct REST HTTP queries to Binance/Coinbase public API endpoints if `ccxt` is omitted.
- **Test Coverage**: Unit tests with recorded/mocked HTTP responses; timeout handling tests (10s limit).
- **Dependencies**: `ccxt>=4.0` (or `requests`), `pandas`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

#### Feature 1.3: Public Domain CFTC COT Positioning Adapter
- **Description**: Automated extractor and parser for U.S. Commodity Futures Trading Commission (CFTC) Commitments of Traders disaggregated futures reports (COMEX Gold Code `088691`, JPY Futures Code `097741`). Extracts managed money net positioning, commercial hedger bias, and historical crowding percentiles.
- **Priority**: **High**
- **Required Data Sources**: `https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip`.
- **Required Providers**: U.S. Government Public Domain (Free, Keyless).
- **Free Alternatives**: None needed (CFTC is official, public, and unrestricted).
- **Test Coverage**: Unit tests parsing sample CFTC fixed-width/CSV lines; network fallback tests.
- **Dependencies**: `requests`, `zipfile`, `pandas`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

#### Feature 1.4: Keyless Bitcoin On-Chain & Network Adapter
- **Description**: Queries open public endpoints to extract Bitcoin network health metrics: mining difficulty trajectory, hashrate estimates, and priority mempool transaction fee rates (`sat/vB`).
- **Priority**: **High**
- **Required Data Sources**: Mempool.space API (`/api/v1/difficulty-adjustments`, `/api/v1/fees/recommended`), Blockchain.info API.
- **Required Providers**: Public Community Open APIs (Free, Keyless).
- **Free Alternatives**: Blockstream.info public API, CoinGecko free ping.
- **Test Coverage**: Unit tests verifying JSON parsing, offline graceful degradation to neutral placeholders.
- **Dependencies**: `requests`.
- **Estimated Complexity**: Low (1-2 days).
- **Completion Status**: Pending.

---

#### Feature 1.5: FRED Sovereign Rates & Real Yields Expansion
- **Description**: Expands the FRED vendor to extract Bank of Japan policy rates (`IRSTCI01JPM156N`), Japan 10Y Sovereign Yields (`IRLTLT01JPM156N`), US 10Y Real Yields (`DFII10`), and US 10Y Breakeven Inflation (`T10YIE`).
- **Priority**: **Critical**
- **Required Data Sources**: St. Louis Fed FRED API.
- **Required Providers**: Federal Reserve Bank of St. Louis (Free API Key).
- **Free Alternatives**: Yahoo Finance reference proxies (`^TNX` for 10Y Treasury).
- **Test Coverage**: Unit tests testing metric alias resolution, empty observation filtering, and offline fallbacks.
- **Dependencies**: `requests`, `pytz`.
- **Estimated Complexity**: Low (1-2 days).
- **Completion Status**: Pending.

---

### Milestone 2: Institutional Analytical Desks

#### Feature 2.1: Macro Monetary & Sovereign Parity Analyst
- **Description**: Dedicated analytical agent for **USDJPY** and **XAUUSD**. Analyzes central bank interest rate differentials (Fed vs. BOJ), 10Y sovereign yield spreads, real rate opportunity costs, and terms-of-trade balance of payments.
- **Priority**: **Critical**
- **Required Data Sources**: FRED API, Yahoo DXY (`DX-Y.NYB`).
- **Required Providers**: Quick-Think LLM Tier (GPT-4o-mini / Gemini Flash / Claude Haiku).
- **Free Alternatives**: Public central bank published target rates.
- **Test Coverage**: Agent prompt rendering tests; structured output validation; mock tool-turn tests.
- **Dependencies**: `tradingagents/agents/analysts/macro_monetary_analyst.py`.
- **Estimated Complexity**: Medium (3-4 days).
- **Completion Status**: Pending.

---

#### Feature 2.2: Institutional Technical & Market Structure Analyst
- **Description**: Re-engineers technical analysis from retail indicators to institutional market structure: order blocks, fair value gaps (FVG), liquidity sweeps, and ATR-14 volatility boundaries.
- **Priority**: **High**
- **Required Data Sources**: `get_stock_data` / CCXT daily and weekly OHLCV, `stockstats`.
- **Required Providers**: Quick-Think LLM Tier.
- **Free Alternatives**: `stockstats` local open-source calculation engine.
- **Test Coverage**: Unit tests validating indicator calculations, snapshot verification grounding, and Markdown table output formatting.
- **Dependencies**: `stockstats>=0.6.5`, `pandas`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

#### Feature 2.3: Bitcoin On-Chain Specialist Analyst
- **Description**: Dedicated analytical agent for **BTC**. Evaluates decentralized network security budgets, miner capitulation vs. accumulation cycles, and on-chain velocity.
- **Priority**: **High**
- **Required Data Sources**: Mempool.space, Blockchain.info open APIs.
- **Required Providers**: Quick-Think LLM Tier.
- **Free Alternatives**: DeFiLlama open APIs.
- **Test Coverage**: Agent turn tests with mocked on-chain payloads; structured schema verification.
- **Dependencies**: `tradingagents/agents/analysts/onchain_analyst.py`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

#### Feature 2.4: Institutional Positioning Desk
- **Description**: Analytical agent synthesizing speculative vs. commercial positioning from CFTC COT reports (for Gold & JPY) and perpetual funding rates (for BTC) to identify overcrowded trades and short-squeeze risks.
- **Priority**: **Medium**
- **Required Data Sources**: CFTC open COT data, CCXT / Binance funding rate feeds.
- **Required Providers**: Quick-Think LLM Tier.
- **Free Alternatives**: Keyless public funding rate endpoints.
- **Test Coverage**: Unit tests for crowding classification thresholds and contrarian warning generation.
- **Dependencies**: `cftc_cot_adapter.py`, `ccxt_adapter.py`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

#### Feature 2.5: Multi-Asset Sentiment & Prediction Markets Desk
- **Description**: Re-routes social sentiment away from stock subreddits to asset-specific communities (`r/Bitcoin`, `r/Gold`, `r/Forex`) and connects to Polymarket keyless Gamma API for forward-looking event probabilities (Fed rate cuts, inflation).
- **Priority**: **Medium**
- **Required Data Sources**: Reddit public Atom/RSS search feeds, Polymarket Gamma API, StockTwits cashtags.
- **Required Providers**: Quick-Think LLM Tier.
- **Free Alternatives**: All sources are 100% free and keyless.
- **Test Coverage**: Unit tests verifying subreddit routing per asset class; lookahead date-window safety.
- **Dependencies**: `reddit.py`, `stocktwits.py`, `polymarket.py`.
- **Estimated Complexity**: Low (1-2 days).
- **Completion Status**: Pending.

---

### Milestone 3: Quantitative Execution & Sizing Engine

#### Feature 3.1: Institutional Multi-Asset Position Sizing Engine
- **Description**: Replaces ambiguous share counts with mathematically rigorous risk-based sizing:
  - **Forex (USDJPY)**: Standard, Mini, and Micro Lots ($0.01\text{ JPY} = 1\text{ pip}$).
  - **Gold (XAUUSD)**: Troy Ounces and standard COMEX contracts (100 oz).
  - **Bitcoin (BTC)**: Exact coin units (6 decimals) and Satoshis ($10^8\text{ sats} = 1\text{ BTC}$).
  - Enforces:
    $$\text{Units} = \frac{\text{Account Equity} \times \text{Risk \%}}{|P_{\text{entry}} - P_{\text{stop}}|}$$
- **Priority**: **Critical**
- **Required Data Sources**: Caller portfolio equity and asset price levels.
- **Required Providers**: Pure Python quantitative math.
- **Free Alternatives**: N/A.
- **Test Coverage**: Math verification tests across diverse account sizes ($10k, $100k, $1M), pip calculations, and zero/negative price guards.
- **Dependencies**: `tradingagents/agents/trader/sizing.py`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

#### Feature 3.2: Multi-Asset Alpha Settlement Engine
- **Description**: Replaces universal `SPY` benchmark in `settlement.py` with asset-specific opportunity-cost benchmarks:
  - **BTC**: Compared against `BTC-USD` passive hold (tactical timing alpha).
  - **XAUUSD**: Compared against inverse Dollar Index (`DX-Y.NYB`).
  - **USDJPY**: Compared against Trade-Weighted US Dollar (`DTWEXBGS`).
- **Priority**: **High**
- **Required Data Sources**: Historical price series of target asset and corresponding benchmark.
- **Required Providers**: Quick-Think LLM Tier (`Reflector`).
- **Free Alternatives**: Yahoo Finance benchmark series.
- **Test Coverage**: Unit tests verifying alpha calculations across win, loss, and flat scenarios; resolution date lookahead protection.
- **Dependencies**: `tradingagents/memory/settlement.py`, `tradingagents/default_config.py`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

#### Feature 3.3: 24/7 & Continuous Calendar System
- **Description**: Eliminates traditional equity weekend/holiday gap assumptions for Bitcoin. Allows daily midnight UTC bars to be processed continuously without triggering false `MAX_OHLCV_STALE_DAYS` alerts.
- **Priority**: **High**
- **Required Data Sources**: Calendar engine in `date_window.py`.
- **Required Providers**: Pure Python (`datetime`, `pandas`).
- **Free Alternatives**: N/A.
- **Test Coverage**: Date boundary tests for crypto (24/7) vs. forex (24/5) vs. equities (NYSE calendar).
- **Dependencies**: `tradingagents/dataflows/date_window.py`.
- **Estimated Complexity**: Low (1-2 days).
- **Completion Status**: Pending.

---

### Milestone 4: LangGraph Topology & Fiduciary Synthesis

#### Feature 4.1: Dynamic Asset-Class LangGraph Dispatcher
- **Description**: Dynamic graph compiler that configures the LangGraph parallel analytical nodes based on the target asset class:
  - If **Crypto**: Market Analyst + On-Chain Analyst + Sentiment Analyst + News Analyst.
  - If **Commodity**: Market Analyst + Macro Monetary Analyst + Positioning Analyst + News Analyst.
  - If **Forex**: Market Analyst + Macro Monetary Analyst + Positioning Analyst + News Analyst.
- **Priority**: **Critical**
- **Required Data Sources**: LangGraph workflow assembly.
- **Required Providers**: LangGraph framework.
- **Free Alternatives**: N/A.
- **Test Coverage**: End-to-end graph compilation tests for all three asset classes; checkpointer resumption tests.
- **Dependencies**: `tradingagents/graph/setup.py`, `tradingagents/graph/analyst_execution.py`.
- **Estimated Complexity**: Medium (3 days).
- **Completion Status**: Pending.

---

#### Feature 4.2: Institutional Pydantic Schemas
- **Description**: Introduces strict Pydantic schemas for the Research Manager (`InstitutionalResearchPlan`), Trader (`InstitutionalProposal`), and Portfolio Manager (`InstitutionalDecision`), including conviction ratings, vehicles, order types, and risk parameters.
- **Priority**: **High**
- **Required Data Sources**: JSON schema validation.
- **Required Providers**: Pydantic / LangChain structured output.
- **Free Alternatives**: N/A.
- **Test Coverage**: Pydantic serialization/deserialization tests; fallback tests for providers lacking native tool-calling.
- **Dependencies**: `tradingagents/agents/schemas.py`, `tradingagents/agents/structured.py`.
- **Estimated Complexity**: Low (1-2 days).
- **Completion Status**: Pending.

---

#### Feature 4.3: Asset-Native Fiduciary Prompts
- **Description**: Complete prompt overhaul for `Bull Researcher`, `Bear Researcher`, `Research Manager`, `Aggressive Analyst`, `Conservative Analyst`, `Neutral Analyst`, and `Portfolio Manager` to evaluate macroeconomic regimes, liquidity contagion, and sovereign risk.
- **Priority**: **High**
- **Required Data Sources**: Prompt text templates.
- **Required Providers**: Deep-Think & Quick-Think LLM Tiers.
- **Free Alternatives**: N/A.
- **Test Coverage**: Prompt template rendering tests; string variable interpolation checks.
- **Dependencies**: `tradingagents/agents/researchers/*`, `tradingagents/agents/managers/*`, `tradingagents/agents/risk_mgmt/*`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

### Milestone 5: Institutional UI, Dashboard & Verification

#### Feature 5.1: Institutional CLI Terminal & Rich Live Display
- **Description**: Updates Typer CLI and Rich dashboard to display asset-native units (pips, funding rates, real yields, satoshis, lots) and adds asset presets (`--asset crypto|commodity|forex`).
- **Priority**: **Medium**
- **Required Data Sources**: CLI live message buffer.
- **Required Providers**: Rich, Typer.
- **Free Alternatives**: N/A.
- **Test Coverage**: Headless CLI execution tests; flag parsing unit tests.
- **Dependencies**: `cli/display.py`, `cli/main.py`, `cli/run.py`.
- **Estimated Complexity**: Medium (2-3 days).
- **Completion Status**: Pending.

---

#### Feature 5.2: Multi-Asset HTML Report Engine
- **Description**: Updates standalone HTML report generator to render multi-asset metrics: pip targets, COMEX contract breakdowns, funding rate histories, and KaTeX KaTeX risk formulas.
- **Priority**: **Low**
- **Required Data Sources**: Final run state dictionary.
- **Required Providers**: `markdown-it-py`.
- **Free Alternatives**: N/A.
- **Test Coverage**: HTML rendering smoke tests; missing field resilience tests.
- **Dependencies**: `tradingagents/report_html.py`, `tradingagents/reporting.py`.
- **Estimated Complexity**: Low (1-2 days).
- **Completion Status**: Pending.

---

#### Feature 5.3: Anti-Lookahead End-to-End Test Suite
- **Description**: Comprehensive end-to-end integration tests running BTC, XAUUSD, and USDJPY through simulated historical dates to verify zero future data leakage across all FOSS adapters.
- **Priority**: **Critical**
- **Required Data Sources**: Scripted mock data and historical test fixtures.
- **Required Providers**: Pytest.
- **Free Alternatives**: N/A.
- **Test Coverage**: 100% path coverage for point-in-time boundaries.
- **Dependencies**: `tests/test_graph_end_to_end.py`.
- **Estimated Complexity**: High (3-4 days).
- **Completion Status**: Pending.

---

## 4. Master Tracking Table

| ID | Feature Name | Priority | Complexity | Target Asset | Free / FOSS Tech | Status |
|---|---|---|---|---|---|---|
| **1.1** | Universal Multi-Asset Symbol Normalizer | **Critical** | Low | BTC, XAU, JPY | Python Regex | **Completed** |
| **1.2** | CCXT Public Crypto Market Data Adapter | **Critical** | Medium | BTC | `ccxt` / Binance REST | **Pending** |
| **1.3** | CFTC Open COT Positioning Adapter | **High** | Medium | XAU, JPY | CFTC.gov Public Zip | **Pending** |
| **1.4** | Keyless Bitcoin On-Chain Adapter | **High** | Low | BTC | Mempool.space API | **Pending** |
| **1.5** | FRED Sovereign Rates & Real Yields | **Critical** | Low | XAU, JPY | St. Louis Fed FRED | **Pending** |
| **2.1** | Macro Monetary & Parity Analyst | **Critical** | Medium | XAU, JPY | FRED / Quick LLM | **Pending** |
| **2.2** | Institutional Technical & Structure Analyst| **High** | Medium | BTC, XAU, JPY | `stockstats` / Quick LLM | **Pending** |
| **2.3** | Bitcoin On-Chain Specialist Analyst | **High** | Medium | BTC | Mempool / Quick LLM | **Pending** |
| **2.4** | Institutional Positioning Desk | **Medium** | Medium | BTC, XAU, JPY | CFTC / CCXT / Quick LLM | **Pending** |
| **2.5** | Multi-Asset Sentiment & Prediction Desk | **Medium** | Low | BTC, XAU, JPY | Reddit / Polymarket | **Pending** |
| **3.1** | Institutional Position Sizing Engine | **Critical** | Medium | BTC, XAU, JPY | Quant Math (Lots/Sats) | **Pending** |
| **3.2** | Multi-Asset Alpha Settlement Engine | **High** | Medium | BTC, XAU, JPY | Asset Benchmark Return | **Pending** |
| **3.3** | 24/7 & Continuous Calendar System | **High** | Low | BTC | Python Datetime | **Pending** |
| **4.1** | Dynamic Asset-Class LangGraph Dispatcher| **Critical** | Medium | BTC, XAU, JPY | LangGraph StateGraph | **Pending** |
| **4.2** | Institutional Pydantic Schemas | **High** | Low | BTC, XAU, JPY | Pydantic v2 | **Pending** |
| **4.3** | Asset-Native Fiduciary Prompts | **High** | Medium | BTC, XAU, JPY | Deep & Quick LLMs | **Pending** |
| **5.1** | Institutional CLI & Rich Live Display | **Medium** | Medium | BTC, XAU, JPY | Typer / Rich | **Pending** |
| **5.2** | Multi-Asset HTML Report Engine | **Low** | Low | BTC, XAU, JPY | Markdown-it | **Pending** |
| **5.3** | Anti-Lookahead End-to-End Suite | **Critical** | High | BTC, XAU, JPY | Pytest Integration | **Pending** |

---

## 5. Next Immediate Action Item

According to the phased roadmap, Feature 1.1 is complete. The next item awaiting approval is:
**Feature 1.2: Free CCXT Public Crypto Market Data Adapter**
- Connects to public exchange REST endpoints (Binance/Coinbase) without API keys to fetch spot OHLCV, spreads, and perpetual funding rates for BTC.
- Implements `tradingagents/dataflows/adapters/ccxt_adapter.py`.
- Implements `tests/test_ccxt_adapter.py`.
