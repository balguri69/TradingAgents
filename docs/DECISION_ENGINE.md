# Complete 14-Stage Institutional Decision Pipeline

*Document Version: 2.0.0 | Status: Architectural Design | Scope: End-to-End Decision Framework*

---

## 1. Executive Pipeline Architecture

The platform's decision pipeline transforms raw market feeds into institutional trade recommendations through a 14-stage progressive refinement process. Each stage acts as a rigorous quantitative and heuristic filter. If risk boundaries are violated, if data freshness fails, or if mathematical expected value is non-positive, the pipeline halts or defaults to an explicit capital-preservation `HOLD`.

```mermaid
flowchart TD
    S1["1. Raw Market Data Ingestion"] --> S2["2. Universal Normalization (SymbolResolver)"]
    S2 --> S3["3. Mathematical Indicator Calculation"]
    S3 --> S4["4. Market Structure & Liquidity Gating"]
    S4 --> S5["5. Smart Money Concepts & COT Flow"]
    S5 --> S6["6. Global Macroeconomic & Rates Analysis"]
    S6 --> S7["7. News & Geopolitical Event Synthesis"]
    S7 --> S8["8. Crowd Sentiment & Prediction Calibration"]
    S8 --> S9["9. Bitcoin On-Chain Flow Analysis"]
    S9 --> S10["10. Quantitative Probability Engine (P_win, Entropy)"]
    S10 --> S11["11. Fiduciary Risk Management Engine"]
    S11 --> S12["12. Actionable Trade Recommendation Formulation"]
    S12 --> S13["13. Adversarial Reasoning & Dialectical Synthesis"]
    S13 --> S14["14. Gemini Final Review & Audit Verification"]

    Gating["Pipeline Veto: Output HOLD (Preserve Capital)"]
    S4 -.->|Illiquid / Wide Spread| Gating
    S10 -.->|E[V] <= 0 or High Uncertainty| Gating
    S11 -.->|Excessive Drawdown / SL > 2.5%| Gating
    S14 -.->|Hallucination or Inadequate Evidence| Gating
```

---

## 2. Stage-by-Stage Input, Transformation & Output Contracts

### Stage 1: Raw Market Data Ingestion
- **Inputs**: Raw external queries from keyless public REST / WebSocket endpoints.
- **Transformation**: Captures raw bytes, assigns collection timestamp, records network latency.
- **Outputs**: `TransportResponse` (raw status, headers, body bytes).

### Stage 2: Universal Normalization (`SymbolResolver`)
- **Inputs**: User input string, `TransportResponse`.
- **Transformation**: Resolves `CanonicalSymbol` (`BTC/USD`, `XAU/USD`, `USD/JPY`), validates JSON schemas, parses numeric values into exact `Decimal` precision, and attaches `ProvenanceMetadata` and `FreshnessMetadata`.
- **Outputs**: Normalized, validated DTOs: `QuoteDTO`, `OHLCVSeriesDTO`, `OrderBookDTO`.

### Stage 3: Mathematical Indicator Calculation
- **Inputs**: `OHLCVSeriesDTO` historical bars.
- **Transformation**: Calculates deterministic quantitative indicators: EMA (20, 50, 200), ATR(14), RSI(14), MACD(12, 26, 9), and Bollinger Bands. Zero LLM involvement; pure mathematical processing.
- **Outputs**: `TechnicalIndicatorsDTO` (timeseries array of computed values).

### Stage 4: Market Structure & Liquidity Gating
- **Inputs**: `OrderBookDTO`, computed ATR, bid-ask spreads.
- **Transformation**: Measures L2 liquidity depth, identifies Fair Value Gaps (FVG), Point of Control (POC), and Value Area High/Low (VAH/VAL).
- **Outputs**: `MarketStructureDTO` (`spread_bps`, `liquidity_regime`, `key_liquidity_pools`).
- **Gating**: If spread exceeds limit ($>15$ bps for BTC, $>25$ bps for Gold) $\rightarrow$ **Veto Trade (HOLD)**.

### Stage 5: Smart Money Concepts (SMC) & Institutional Flow
- **Inputs**: CFTC Commitments of Traders (COT) disaggregated reports, order flow imbalance metrics.
- **Transformation**: Analyzes Managed Money vs Commercial Hedger positioning percentiles, institutional accumulation/distribution signs, and liquidity pool sweeps.
- **Outputs**: `SmartMoneyDTO` (`net_institutional_bias`, `cot_crowding_percentile`, `liquidity_sweep_detected`).

### Stage 6: Global Macroeconomic & Rates Analysis
- **Inputs**: FRED macro timeseries (Fed Funds, 10Y Treasury, 2Y Treasury, TIPS 10Y Real Rates, M2 Money Supply).
- **Transformation**: Computes yield curve slope ($Y_{10} - Y_2$), real rate trajectory (critical for Gold), and central bank policy divergence (Fed vs BOJ for USDJPY).
- **Outputs**: `MacroRegimeDTO` (`liquidity_regime`, `real_rate_bias`, `sovereign_yield_spread`).

### Stage 7: News & Geopolitical Event Synthesis
- **Inputs**: Chronologically bounded news feeds, wire reports, regulatory announcements.
- **Transformation**: Uses **Gemini Flash** to filter low-relevance clickbait, classify catalyst severity (Minor, Moderate, Major, Systemic), and flag imminent high-impact binary events (e.g., FOMC rate decision within 24 hours).
- **Outputs**: `NewsCatalystReportDTO` (`net_sentiment`, `primary_catalysts`, `imminent_binary_event`).

### Stage 8: Crowd Sentiment & Prediction Calibration
- **Inputs**: Social discussions (Reddit, StockTwits), Polymarket binary prediction odds.
- **Transformation**: Measures crowd sentiment velocity, detects extreme euphoria or panic, and computes market-implied odds for macro events.
- **Outputs**: `SentimentSignalDTO` (`crowd_sentiment_index`, `contrarian_warning`, `polymarket_odds`).

### Stage 9: Bitcoin On-Chain Flow Analysis (Crypto Only)
- **Inputs**: Mempool transaction fees, network hash rate, active address velocity from Mempool.space.
- **Transformation**: Assesses blockchain health, miner capitulation/accumulation metrics, and fee spikes.
- **Outputs**: `OnChainMetricsDTO` (`hashrate_trend`, `mempool_congestion`, `network_activity_score`).

### Stage 10: Quantitative Probability Engine
- **Inputs**: Synthesized outputs from Stages 3 through 9.
- **Transformation**: Computes multi-factor evidence weights, calculates Shannon Entropy across conflicting desk signals, executes Monte Carlo simulations, and evaluates expected value:
  $$\mathbb{E}[V] = (P_{\text{long}} \times R_{\text{win}}) - (P_{\text{short}} \times 1.0) - \text{Friction}$$
- **Outputs**: `ProbabilityEstimateDTO` (`P_long`, `P_short`, `P_neutral`, `confidence_score`, `uncertainty_score`, `E[V]`).
- **Gating**: If $\mathbb{E}[V] \le 0.0$ or uncertainty $> 0.75$ $\rightarrow$ **Veto Trade (HOLD)**.

### Stage 11: Fiduciary Risk Management Engine
- **Inputs**: `ProbabilityEstimateDTO`, `TechnicalIndicatorsDTO` (ATR), portfolio NAV, current drawdowns.
- **Transformation**: Multi-persona risk evaluation (Aggressive, Conservative, Neutral). Computes minimum ATR-based stop-loss distance ($2.0 \times \text{ATR}$), maximum portfolio risk allocation ($\le 1.5\%$), and position size in basis points via volatility parity.
- **Outputs**: `RiskAssessmentDTO` (`risk_verdict`, `mandatory_stop_loss`, `max_position_size_bps`, `reward_risk_hurdle`).
- **Gating**: If risk cannot be contained within $1.5\%$ portfolio equity $\rightarrow$ **Veto Trade (HOLD)**.

### Stage 12: Actionable Trade Recommendation Formulation
- **Inputs**: Outputs from Probability and Risk engines.
- **Transformation**: Constructs actionable execution parameters: Entry price, Stop-Loss price, Take-Profit 1 (conservative), Take-Profit 2 (runner), and position size.
- **Outputs**: `TradePlanDTO` (`action`, `entry`, `sl`, `tp1`, `tp2`, `size_bps`, `invalidation_rules`).

### Stage 13: Adversarial Reasoning & Dialectical Synthesis
- **Inputs**: `TradePlanDTO`, full evidence package.
- **Transformation**: Orchestrated via **Gemini Pro**. Bullish and Bearish research personas conduct structured dialectical debate, stress-testing thesis assumptions and probing blind spots until the Research Manager achieves consensus.
- **Outputs**: `AdversarialDebateDTO` (transcripts, thesis challenge records, consensus summary).

### Stage 14: Gemini Final Review & Audit Verification
- **Inputs**: Final synthesized package, audit log, and trade plan.
- **Transformation**: Executed by **Gemini Deep Thinking** (extended reasoning model). Performs final fiduciary sanity checks:
  1. Validates that citations match underlying data (anti-hallucination check).
  2. Confirms that stop-loss satisfies capital preservation mandates.
  3. Audits mathematical consistency between expected value and position size.
- **Outputs**: Final `FiduciaryAuditReportDTO` and authorization token. Renders recommendation card to terminal UI.
