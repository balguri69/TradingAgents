"""Production-ready Yahoo Finance data provider.

Supports multi-asset market data ingestion for TradFi instruments:
  - Gold (GC=F, XAU/USD)
  - Forex (USDJPY=X, EURUSD=X, GBPUSD=X)
  - Equities & ETFs (AAPL, MSFT, SPY, QQQ)
  - Benchmark Indices (^GSPC, ^NDX, ^DJI)

Uses unauthenticated public REST endpoints:
  - Chart & OHLCV: https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
  - Real-time Quotes: https://query1.finance.yahoo.com/v7/finance/quote
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import logging
from typing import Any, Sequence
import urllib.parse

from tradingagents.dataflows.contracts.capabilities import (
    ProviderCapabilities,
    ProviderMetadata,
)
from tradingagents.dataflows.contracts.provider import ExchangeProvider
from tradingagents.dataflows.contracts.transport import TimeoutConfig, TransportClient
from tradingagents.dataflows.dto.market_data import (
    CandleDTO,
    ExchangeInfoDTO,
    OHLCVSeriesDTO,
    OrderBookDTO,
    QuoteDTO,
    SymbolFilterDTO,
)
from tradingagents.dataflows.dto.telemetry import HealthStatusDTO
from tradingagents.dataflows.enums import HealthState, Timeframe
from tradingagents.dataflows.exceptions import (
    DTOValidationError,
    NoMarketDataError,
    VendorError,
    VendorRateLimitError,
    VendorUnavailableError,
)
from tradingagents.dataflows.symbols import AssetClass, CanonicalSymbol, SymbolResolver
from tradingagents.dataflows.transport import RestTransportClient

logger = logging.getLogger(__name__)

# Standard multi-asset instruments supported natively on Yahoo Finance
_DEFAULT_SUPPORTED_SYMBOLS: tuple[str, ...] = (
    "XAU/USD",
    "USD/JPY",
    "EUR/USD",
    "GBP/USD",
    "SPX500",
    "GC=F",
    "SI=F",
    "CL=F",
    "USDJPY=X",
    "EURUSD=X",
    "GBPUSD=X",
    "^GSPC",
    "^NDX",
    "^DJI",
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "TSLA",
    "SPY",
    "QQQ",
    "GLD",
    "IVV",
    "*",
)

# Timeframe mapping to Yahoo Finance chart intervals
_TIMEFRAME_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.H1: "1h",
    Timeframe.H4: "1h",  # Clamped to 1h bars as Yahoo lacks native 4h interval
    Timeframe.D1: "1d",
    Timeframe.W1: "1wk",
}


class YahooFinanceProvider(ExchangeProvider):
    """Production-ready Yahoo Finance data provider extending ExchangeProvider.

    Provides:
      - Real-time and end-of-day market quotes for Gold, Forex, Equities, and Indices
      - Continuous OHLCV historical series with timezone-aware bar parsing
      - Trading rules and precision filters (tick size, lot step size)
      - Network ping and diagnostic health checks
    """

    def __init__(
        self,
        transport: TransportClient | None = None,
        base_url: str = "https://query1.finance.yahoo.com",
        timeout: TimeoutConfig | tuple[float, float] | float = (5.0, 10.0),
    ) -> None:
        self._transport = transport if transport is not None else RestTransportClient(timeout=timeout)
        self._base_url = base_url.rstrip("/")
        self._capabilities = ProviderCapabilities(
            quote=True,
            ohlcv=True,
            orderbook=False,     # Yahoo does not support L2 order books
            funding_rate=False,  # TradFi spot/futures do not use perpetual funding rates
            news=True,
            historical_data=True,
        )
        self._metadata = ProviderMetadata(
            provider_name="yahoo",
            version="1.0.0",
            is_free_tier=True,
            rate_limit_rpm=360,
            supports_realtime=True,
            supported_asset_classes=("commodity", "forex", "stock", "index"),
            priority=2,
        )

    # ------------------------------------------------------------------
    # ExchangeProvider Contract Properties
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "yahoo"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    @property
    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def get_supported_symbols(self) -> Sequence[str]:
        return _DEFAULT_SUPPORTED_SYMBOLS

    # ------------------------------------------------------------------
    # Health & System Telemetry
    # ------------------------------------------------------------------

    def health_check(self) -> HealthStatusDTO:
        """Probe Yahoo Finance chart API to measure availability and round-trip latency."""
        url = f"{self._base_url}/v8/finance/chart/%5EGSPC"
        params = {"range": "1d", "interval": "1d"}
        try:
            resp = self._transport.get(url, params=params)
            self._check_response(resp, "health_check")
            latency = getattr(resp, "latency_ms", Decimal("0.0"))
            return HealthStatusDTO(
                provider_name=self.provider_name,
                state=HealthState.HEALTHY,
                latency_ms=latency,
                last_successful_query=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning("Yahoo Finance health check failed: %s", exc)
            return HealthStatusDTO(
                provider_name=self.provider_name,
                state=HealthState.UNHEALTHY,
                latency_ms=Decimal("0.0"),
                last_successful_query=None,
                error_message=str(exc),
            )

    def get_server_time(self) -> datetime:
        """Fetch current UTC timestamp representing Yahoo service time."""
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Market Data Ingestion
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str, as_of: datetime | None = None) -> QuoteDTO:
        """Fetch real-time or regular market quote snapshot for an instrument."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        encoded_sym = urllib.parse.quote(vendor_sym, safe="")
        url = f"{self._base_url}/v7/finance/quote"
        resp = self._transport.get(url, params={"symbols": vendor_sym})
        data = self._parse_json(resp, f"get_quote({symbol})")

        result_list = data.get("quoteResponse", {}).get("result", [])
        if not result_list:
            # Fallback to chart endpoint if quote endpoint returns empty
            return self._get_quote_from_chart(canonical, vendor_sym)

        item = result_list[0]
        try:
            raw_price = item.get("regularMarketPrice")
            if raw_price is None:
                return self._get_quote_from_chart(canonical, vendor_sym)

            price = Decimal(str(raw_price))
            # Bid/ask handling for OTC and TradFi assets
            bid_val = item.get("bid")
            ask_val = item.get("ask")

            bid = Decimal(str(bid_val)) if bid_val is not None and float(bid_val) > 0 else price
            ask = Decimal(str(ask_val)) if ask_val is not None and float(ask_val) > 0 else price

            # Maintain financial invariant: bid cannot exceed ask
            if bid > ask:
                bid, ask = ask, bid

            bid_size = Decimal(str(item.get("bidSize", 0)))
            ask_size = Decimal(str(item.get("askSize", 0)))
            vol_val = item.get("regularMarketVolume", 0)
            volume_24h = Decimal(str(vol_val if vol_val is not None else 0))

            mkt_time_sec = item.get("regularMarketTime", 0)
            timestamp = (
                datetime.fromtimestamp(mkt_time_sec, tz=timezone.utc)
                if mkt_time_sec
                else datetime.now(timezone.utc)
            )

            return QuoteDTO(
                symbol=canonical.canonical_id,
                price=price,
                bid=bid,
                ask=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                volume_24h=volume_24h,
                timestamp=timestamp,
                provider=self.provider_name,
            )
        except (KeyError, ValueError, InvalidOperation, DTOValidationError) as exc:
            raise VendorError(f"Failed to parse Yahoo quote response for {symbol}: {exc}") from exc

    def _get_quote_from_chart(self, canonical: CanonicalSymbol, vendor_sym: str) -> QuoteDTO:
        """Secondary fallback for quotes derived from the chart endpoint meta block."""
        encoded_sym = urllib.parse.quote(vendor_sym, safe="")
        url = f"{self._base_url}/v8/finance/chart/{encoded_sym}"
        resp = self._transport.get(url, params={"interval": "1d", "range": "1d"})
        data = self._parse_json(resp, f"get_quote_chart_fallback({canonical.canonical_id})")

        results = data.get("chart", {}).get("result", [])
        if not results:
            raise NoMarketDataError(f"No market quote available on Yahoo Finance for {canonical.canonical_id}")

        meta = results[0].get("meta", {})
        raw_price = meta.get("regularMarketPrice")
        if raw_price is None:
            raise NoMarketDataError(f"No regular market price for {canonical.canonical_id}")

        price = Decimal(str(raw_price))
        mkt_time_sec = meta.get("regularMarketTime", 0)
        timestamp = (
            datetime.fromtimestamp(mkt_time_sec, tz=timezone.utc)
            if mkt_time_sec
            else datetime.now(timezone.utc)
        )

        return QuoteDTO(
            symbol=canonical.canonical_id,
            price=price,
            bid=price,
            ask=price,
            bid_size=Decimal("0"),
            ask_size=Decimal("0"),
            volume_24h=Decimal(str(meta.get("regularMarketVolume", 0) or 0)),
            timestamp=timestamp,
            provider=self.provider_name,
        )

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_date: datetime,
        end_date: datetime,
    ) -> OHLCVSeriesDTO:
        """Fetch historical candlesticks from Yahoo Finance chart v8 API."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        interval = _TIMEFRAME_MAP.get(timeframe)
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        period1 = int(start_date.timestamp())
        period2 = int(end_date.timestamp())

        encoded_sym = urllib.parse.quote(vendor_sym, safe="")
        url = f"{self._base_url}/v8/finance/chart/{encoded_sym}"
        params = {
            "interval": interval,
            "period1": period1,
            "period2": period2,
            "includePrePost": "false",
            "events": "div,splits",
        }
        resp = self._transport.get(url, params=params)
        data = self._parse_json(resp, f"get_ohlcv({symbol})")

        chart_block = data.get("chart", {})
        if chart_block.get("error"):
            err_desc = chart_block["error"].get("description", "Unknown error")
            raise NoMarketDataError(f"Yahoo chart error for {symbol}: {err_desc}")

        results = chart_block.get("result", [])
        if not results:
            raise NoMarketDataError(f"No OHLCV candle data returned for {symbol}")

        series_data = results[0]
        timestamps = series_data.get("timestamp", [])
        indicators = series_data.get("indicators", {}).get("quote", [{}])[0]

        opens = indicators.get("open", [])
        highs = indicators.get("high", [])
        lows = indicators.get("low", [])
        closes = indicators.get("close", [])
        volumes = indicators.get("volume", [])

        candles: list[CandleDTO] = []
        for i, ts_sec in enumerate(timestamps):
            try:
                # Discard null bars (e.g. trading holidays or incomplete market intervals)
                if (
                    opens[i] is None
                    or highs[i] is None
                    or lows[i] is None
                    or closes[i] is None
                ):
                    continue

                ts = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
                o = Decimal(str(opens[i]))
                h = Decimal(str(highs[i]))
                l = Decimal(str(lows[i]))
                c = Decimal(str(closes[i]))
                v = Decimal(str(volumes[i] if volumes[i] is not None else 0))

                # Sanity adjustment for float rounding artifacts where open/close exceeds high/low by negligible epsilon
                h = max(h, o, c)
                l = min(l, o, c)

                candles.append(
                    CandleDTO(
                        timestamp=ts,
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=v,
                    )
                )
            except (IndexError, ValueError, InvalidOperation, DTOValidationError) as exc:
                logger.debug("Skipping malformed candle at index %d: %s", i, exc)

        return OHLCVSeriesDTO(
            symbol=canonical.canonical_id,
            timeframe=timeframe,
            candles=tuple(candles),
            provider=self.provider_name,
        )

    def get_orderbook(
        self, symbol: str, depth: int = 20, as_of: datetime | None = None
    ) -> OrderBookDTO:
        """L2 depth is not offered on public Yahoo Finance feeds."""
        raise NotImplementedError(f"Provider {self.provider_name!r} does not support L2 order books")

    # ------------------------------------------------------------------
    # Exchange Metadata & Trading Rules
    # ------------------------------------------------------------------

    def get_symbol_filters(self, symbol: str) -> SymbolFilterDTO:
        """Retrieve instrument tick size, step size, and precision rules."""
        canonical, vendor_sym = self._resolve_symbol(symbol)

        # TradFi instrument rules based on asset classification
        if canonical.asset_class == AssetClass.COMMODITY:
            # Gold (GC=F) & COMEX metals
            tick_size = Decimal("0.10")
            step_size = Decimal("0.01")
            price_prec = 2
            qty_prec = 2
            min_notional = Decimal("100.0")
        elif canonical.asset_class == AssetClass.FOREX:
            # Spot currencies
            is_jpy = "JPY" in canonical.canonical_id
            tick_size = Decimal("0.001") if is_jpy else Decimal("0.0001")
            step_size = Decimal("1000.0")  # Standard micro lot
            price_prec = 3 if is_jpy else 5
            qty_prec = 0
            min_notional = Decimal("100.0")
        else:
            # Equities, ETFs, Indices
            tick_size = Decimal("0.01")
            step_size = Decimal("1.0")
            price_prec = 2
            qty_prec = 0
            min_notional = Decimal("1.0")

        return SymbolFilterDTO(
            symbol=canonical.canonical_id,
            base_asset=canonical.base_asset,
            quote_asset=canonical.quote_currency,
            price_precision=price_prec,
            quantity_precision=qty_prec,
            tick_size=tick_size,
            step_size=step_size,
            min_quantity=step_size,
            max_quantity=Decimal("10000000.0"),
            min_notional=min_notional,
            exchange=self.provider_name,
        )

    def get_exchange_info(self) -> ExchangeInfoDTO:
        """Construct exchange info catalog for standard TradFi assets."""
        symbols_catalog = [
            self.get_symbol_filters("XAU/USD"),
            self.get_symbol_filters("USD/JPY"),
            self.get_symbol_filters("EUR/USD"),
            self.get_symbol_filters("SPX500"),
            self.get_symbol_filters("AAPL"),
        ]
        return ExchangeInfoDTO(
            exchange=self.provider_name,
            server_time=datetime.now(timezone.utc),
            symbols=tuple(symbols_catalog),
        )

    # ------------------------------------------------------------------
    # Internal Helpers & Error Handling
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_symbol(symbol: str) -> tuple[CanonicalSymbol, str]:
        """Delegate symbol normalization strictly to SymbolResolver."""
        try:
            canonical = SymbolResolver.resolve(symbol)
            vendor_sym = SymbolResolver.to_vendor_symbol(canonical, "yahoo")
            return canonical, vendor_sym
        except Exception as exc:
            raise NoMarketDataError(f"Symbol {symbol!r} cannot be resolved for Yahoo Finance: {exc}") from exc

    def _check_response(self, resp: Any, operation: str) -> None:
        """Inspect HTTP status code and translate vendor error semantics."""
        status = getattr(resp, "status_code", 200)

        if status == 404:
            raise NoMarketDataError(f"Yahoo Finance endpoint 404 Not Found during {operation}")
        if status == 429:
            raise VendorRateLimitError(f"Yahoo Finance rate limit (HTTP 429) during {operation}")
        if status >= 500:
            raise VendorUnavailableError(
                f"Yahoo Finance service unavailable (HTTP {status}) during {operation}"
            )
        if status >= 400:
            raise VendorError(f"Yahoo Finance client error (HTTP {status}) during {operation}")

    def _parse_json(self, resp: Any, operation: str) -> Any:
        """Verify response code and deserialize JSON body."""
        self._check_response(resp, operation)
        data = getattr(resp, "data", None)
        if isinstance(data, (dict, list)):
            return data
        if isinstance(data, str):
            try:
                return json.loads(data)
            except Exception as exc:
                raise VendorError(f"Failed to decode JSON from Yahoo Finance {operation}: {exc}") from exc
        raise VendorError(f"Unexpected data type from Yahoo Finance {operation}: {type(data)}")
