"""Production-ready Binance public REST data provider.

Uses unauthenticated public REST endpoints exclusively:
  - Spot API: https://api.binance.com
  - USD-M Futures API: https://fapi.binance.com
Adheres strictly to the MarketDataProvider contract and returns frozen domain DTOs.
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
from tradingagents.dataflows.contracts.provider import ExchangeProvider, MarketDataProvider
from tradingagents.dataflows.contracts.transport import TimeoutConfig, TransportClient
from tradingagents.dataflows.dto.market_data import (
    CandleDTO,
    ExchangeInfoDTO,
    FundingRateDTO,
    MarkPriceDTO,
    OHLCVSeriesDTO,
    OpenInterestDTO,
    OrderBookDTO,
    OrderBookLevelDTO,
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
from tradingagents.dataflows.symbols import CanonicalSymbol, SymbolResolver
from tradingagents.dataflows.transport import RestTransportClient

logger = logging.getLogger(__name__)

# Standard institutional symbols supported natively on Binance Spot & Futures
_DEFAULT_SUPPORTED_SYMBOLS: tuple[str, ...] = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "DOGE/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "LTC/USDT",
    "BTC/USD",
)

# Timeframe mapping to Binance Kline intervals
_TIMEFRAME_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1w",
}


class BinanceProvider(ExchangeProvider):
    """Universal Binance data provider interfacing with public unauthenticated REST APIs.

    Provides:
      - Spot market quotes, OHLCV, and L2 order books
      - Futures perpetual funding rates, open interest, and mark/index prices
      - Exchange information, tick size, step size, and precision rules
      - Server time and ping health checks
    """

    def __init__(
        self,
        transport: TransportClient | None = None,
        spot_base_url: str = "https://api.binance.com",
        futures_base_url: str = "https://fapi.binance.com",
        timeout: TimeoutConfig | tuple[float, float] | float = (3.0, 5.0),
    ) -> None:
        self._transport = transport if transport is not None else RestTransportClient(timeout=timeout)
        self._spot_base_url = spot_base_url.rstrip("/")
        self._futures_base_url = futures_base_url.rstrip("/")
        self._capabilities = ProviderCapabilities(
            quote=True,
            ohlcv=True,
            orderbook=True,
            funding_rate=True,
            open_interest=True,
            historical_data=True,
        )
        self._metadata = ProviderMetadata(
            provider_name="binance",
            version="1.0.0",
            is_free_tier=True,
            rate_limit_rpm=1200,
            supports_realtime=True,
            supported_asset_classes=("crypto",),
            priority=1,
        )

    # ------------------------------------------------------------------
    # MarketDataProvider Contract Properties
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "binance"

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
        """Ping the Binance spot API to measure network availability and round-trip latency."""
        url = f"{self._spot_base_url}/api/v3/ping"
        try:
            resp = self._transport.get(url)
            self._check_response(resp, "ping")
            latency = getattr(resp, "latency_ms", Decimal("0.0"))
            return HealthStatusDTO(
                provider_name=self.provider_name,
                state=HealthState.HEALTHY,
                latency_ms=latency,
                last_successful_query=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning("Binance health check failed: %s", exc)
            return HealthStatusDTO(
                provider_name=self.provider_name,
                state=HealthState.UNHEALTHY,
                latency_ms=Decimal("0.0"),
                last_successful_query=None,
                error_message=str(exc),
            )

    def get_server_time(self) -> datetime:
        """Fetch the official Binance server time."""
        url = f"{self._spot_base_url}/api/v3/time"
        resp = self._transport.get(url)
        data = self._parse_json(resp, "get_server_time")
        server_ms = data.get("serverTime")
        if not isinstance(server_ms, (int, float)):
            raise VendorError("Binance server time response missing 'serverTime'")
        return datetime.fromtimestamp(server_ms / 1000.0, tz=timezone.utc)

    # ------------------------------------------------------------------
    # Spot Market Data Ingestion
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str, as_of: datetime | None = None) -> QuoteDTO:
        """Fetch real-time 24hr ticker quote containing price, spread, and volume."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        url = f"{self._spot_base_url}/api/v3/ticker/24hr"
        resp = self._transport.get(url, params={"symbol": vendor_sym})
        data = self._parse_json(resp, f"get_quote({symbol})")

        try:
            price = Decimal(str(data["lastPrice"]))
            bid = Decimal(str(data["bidPrice"]))
            ask = Decimal(str(data["askPrice"]))
            bid_size = Decimal(str(data["bidQty"]))
            ask_size = Decimal(str(data["askQty"]))
            volume_24h = Decimal(str(data["volume"]))
            close_time_ms = data.get("closeTime", 0)
            timestamp = (
                datetime.fromtimestamp(close_time_ms / 1000.0, tz=timezone.utc)
                if close_time_ms
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
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise VendorError(f"Failed to parse Binance quote response for {symbol}: {exc}") from exc

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_date: datetime,
        end_date: datetime,
    ) -> OHLCVSeriesDTO:
        """Fetch historical candlestick bars from Binance Spot klines."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        interval = _TIMEFRAME_MAP.get(timeframe)
        if interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        url = f"{self._spot_base_url}/api/v3/klines"
        candles_by_ts: dict[datetime, CandleDTO] = {}
        curr_start_ms = start_ms

        # Transparent pagination loop: fetch all kline pages up to end_ms without caller intervention
        while curr_start_ms < end_ms:
            params = {
                "symbol": vendor_sym,
                "interval": interval,
                "startTime": curr_start_ms,
                "endTime": end_ms,
                "limit": 1000,
            }
            resp = self._transport.get(url, params=params)
            raw_klines = self._parse_json(resp, f"get_ohlcv({symbol})")

            if not isinstance(raw_klines, list):
                raise VendorError(f"Expected list of klines from Binance, got {type(raw_klines).__name__}")
            if not raw_klines:
                break

            last_open_ms = curr_start_ms
            page_added = 0
            for row in raw_klines:
                try:
                    open_ms = row[0]
                    last_open_ms = max(last_open_ms, open_ms)
                    ts = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)
                    if ts not in candles_by_ts:
                        candles_by_ts[ts] = CandleDTO(
                            timestamp=ts,
                            open=Decimal(str(row[1])),
                            high=Decimal(str(row[2])),
                            low=Decimal(str(row[3])),
                            close=Decimal(str(row[4])),
                            volume=Decimal(str(row[5])),
                        )
                        page_added += 1
                except (IndexError, ValueError, InvalidOperation, DTOValidationError) as exc:
                    logger.debug("Skipping malformed candle row %s: %s", row, exc)

            if len(raw_klines) < 1000 or page_added == 0:
                break

            curr_start_ms = last_open_ms + 1

        sorted_candles = tuple(candles_by_ts[ts] for ts in sorted(candles_by_ts.keys()))

        return OHLCVSeriesDTO(
            symbol=canonical.canonical_id,
            timeframe=timeframe,
            candles=sorted_candles,
            provider=self.provider_name,
        )

    def get_orderbook(
        self, symbol: str, depth: int = 20, as_of: datetime | None = None
    ) -> OrderBookDTO:
        """Fetch L2 top-of-book depth snapshot from Binance Spot."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        valid_depths = (5, 10, 20, 50, 100, 500, 1000)
        limit = next((d for d in valid_depths if d >= depth), 1000)

        url = f"{self._spot_base_url}/api/v3/depth"
        resp = self._transport.get(url, params={"symbol": vendor_sym, "limit": limit})
        data = self._parse_json(resp, f"get_orderbook({symbol})")

        try:
            bids_list: list[OrderBookLevelDTO] = []
            for item in data.get("bids", []):
                bids_list.append(
                    OrderBookLevelDTO(
                        price=Decimal(str(item[0])),
                        quantity=Decimal(str(item[1])),
                    )
                )

            asks_list: list[OrderBookLevelDTO] = []
            for item in data.get("asks", []):
                asks_list.append(
                    OrderBookLevelDTO(
                        price=Decimal(str(item[0])),
                        quantity=Decimal(str(item[1])),
                    )
                )

            bids = tuple(bids_list)
            asks = tuple(asks_list)

            # Calculate spread in basis points
            spread_bps = Decimal("0")
            if bids and asks:
                best_bid = bids[0].price
                best_ask = asks[0].price
                if best_ask > Decimal("0"):
                    spread_bps = ((best_ask - best_bid) / best_ask) * Decimal("10000")
                    if spread_bps < Decimal("0"):
                        spread_bps = Decimal("0")

            return OrderBookDTO(
                symbol=canonical.canonical_id,
                timestamp=datetime.now(timezone.utc),
                bids=bids,
                asks=asks,
                spread_bps=spread_bps,
                provider=self.provider_name,
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise VendorError(f"Failed to parse Binance depth response: {exc}") from exc

    # ------------------------------------------------------------------
    # Futures Market Data Ingestion
    # ------------------------------------------------------------------

    def get_funding_rate(
        self, symbol: str, as_of: datetime | None = None
    ) -> FundingRateDTO:
        """Fetch current perpetual funding rate and mark price from Binance USD-M Futures."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        url = f"{self._futures_base_url}/fapi/v1/premiumIndex"
        resp = self._transport.get(url, params={"symbol": vendor_sym})
        data = self._parse_json(resp, f"get_funding_rate({symbol})")

        try:
            rate = Decimal(str(data["lastFundingRate"]))
            # 8-hour rate annualized: rate * 3 * 365
            annualized = rate * Decimal("3") * Decimal("365")
            mark = Decimal(str(data["markPrice"])) if data.get("markPrice") else None
            next_funding_ms = data.get("nextFundingTime", 0)
            funding_time = (
                datetime.fromtimestamp(next_funding_ms / 1000.0, tz=timezone.utc)
                if next_funding_ms
                else datetime.now(timezone.utc)
            )

            return FundingRateDTO(
                symbol=canonical.canonical_id,
                funding_rate=rate,
                annualized_rate=annualized,
                funding_time=funding_time,
                mark_price=mark,
                exchange=self.provider_name,
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise VendorError(f"Failed to parse Binance funding rate for {symbol}: {exc}") from exc

    def get_open_interest(self, symbol: str) -> OpenInterestDTO:
        """Fetch current open interest for a derivative instrument on Binance Futures."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        url = f"{self._futures_base_url}/fapi/v1/openInterest"
        resp = self._transport.get(url, params={"symbol": vendor_sym})
        data = self._parse_json(resp, f"get_open_interest({symbol})")

        try:
            oi = Decimal(str(data["openInterest"]))
            time_ms = data.get("time", 0)
            ts = (
                datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc)
                if time_ms
                else datetime.now(timezone.utc)
            )
            return OpenInterestDTO(
                symbol=canonical.canonical_id,
                open_interest=oi,
                open_interest_usd=None,
                timestamp=ts,
                exchange=self.provider_name,
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise VendorError(f"Failed to parse Binance open interest for {symbol}: {exc}") from exc

    def get_mark_price(self, symbol: str) -> MarkPriceDTO:
        """Fetch real-time mark and index price metrics from Binance Futures."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        url = f"{self._futures_base_url}/fapi/v1/premiumIndex"
        resp = self._transport.get(url, params={"symbol": vendor_sym})
        data = self._parse_json(resp, f"get_mark_price({symbol})")

        try:
            mark = Decimal(str(data["markPrice"]))
            index = Decimal(str(data["indexPrice"]))
            settle = (
                Decimal(str(data["estimatedSettlePrice"]))
                if data.get("estimatedSettlePrice")
                else None
            )
            last_fr = (
                Decimal(str(data["lastFundingRate"]))
                if data.get("lastFundingRate") is not None
                else None
            )
            next_fr_ms = data.get("nextFundingTime")
            next_fr_time = (
                datetime.fromtimestamp(next_fr_ms / 1000.0, tz=timezone.utc)
                if next_fr_ms
                else None
            )
            time_ms = data.get("time", 0)
            ts = (
                datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc)
                if time_ms
                else datetime.now(timezone.utc)
            )

            return MarkPriceDTO(
                symbol=canonical.canonical_id,
                mark_price=mark,
                index_price=index,
                estimated_settle_price=settle,
                last_funding_rate=last_fr,
                next_funding_time=next_fr_time,
                timestamp=ts,
                exchange=self.provider_name,
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise VendorError(f"Failed to parse Binance mark price for {symbol}: {exc}") from exc

    # ------------------------------------------------------------------
    # Exchange Metadata & Trading Rules
    # ------------------------------------------------------------------

    def get_symbol_filters(self, symbol: str) -> SymbolFilterDTO:
        """Fetch tick size, lot step size, and precision rules for a trading pair."""
        canonical, vendor_sym = self._resolve_symbol(symbol)
        url = f"{self._spot_base_url}/api/v3/exchangeInfo"
        resp = self._transport.get(url, params={"symbol": vendor_sym})
        data = self._parse_json(resp, f"get_symbol_filters({symbol})")

        symbols_list = data.get("symbols", [])
        if not symbols_list:
            raise NoMarketDataError(f"Symbol {symbol!r} not found in Binance exchangeInfo")

        sym_data = symbols_list[0]
        return self._parse_single_symbol_filter(sym_data, canonical.canonical_id)

    def get_exchange_info(self) -> ExchangeInfoDTO:
        """Fetch venue exchange info and active symbol filter catalog."""
        url = f"{self._spot_base_url}/api/v3/exchangeInfo"
        resp = self._transport.get(url)
        data = self._parse_json(resp, "get_exchange_info")

        server_ms = data.get("serverTime", 0)
        server_time = (
            datetime.fromtimestamp(server_ms / 1000.0, tz=timezone.utc)
            if server_ms
            else datetime.now(timezone.utc)
        )

        parsed_filters: list[SymbolFilterDTO] = []
        for s in data.get("symbols", []):
            try:
                raw_sym = s.get("symbol", "")
                parsed_filters.append(self._parse_single_symbol_filter(s, raw_sym))
            except Exception:
                continue

        return ExchangeInfoDTO(
            exchange=self.provider_name,
            server_time=server_time,
            symbols=tuple(parsed_filters),
        )

    # ------------------------------------------------------------------
    # Internal Helpers & Error Handling
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_symbol(symbol: str) -> tuple[CanonicalSymbol, str]:
        """Delegate symbol normalization strictly to SymbolResolver."""
        try:
            canonical = SymbolResolver.resolve(symbol)
            vendor_sym = SymbolResolver.to_vendor_symbol(canonical, "binance")
            return canonical, vendor_sym
        except Exception as exc:
            raise NoMarketDataError(f"Symbol {symbol!r} cannot be resolved for Binance: {exc}") from exc

    def _check_response(self, resp: Any, operation: str) -> None:
        """Inspect HTTP status code and translate vendor error semantics."""
        status = getattr(resp, "status_code", 200)

        if status == 404:
            raise NoMarketDataError(f"Binance endpoint 404 Not Found during {operation}")
        if status == 429:
            raise VendorRateLimitError(f"Binance rate limit (HTTP 429) during {operation}")
        if status >= 500:
            raise VendorUnavailableError(
                f"Binance service unavailable (HTTP {status}) during {operation}"
            )
        if status >= 400:
            # Check for Binance structured error format: {"code": -1121, "msg": "Invalid symbol."}
            data = getattr(resp, "data", None)
            if isinstance(data, dict):
                code = data.get("code")
                msg = data.get("msg", "")
                if code == -1121 or "Invalid symbol" in msg:
                    raise NoMarketDataError(f"Binance rejected symbol: {msg}")
                raise VendorError(f"Binance API error (HTTP {status}, code {code}): {msg}")
            if isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict):
                        code = parsed.get("code")
                        msg = parsed.get("msg", "")
                        if code == -1121 or "Invalid symbol" in msg:
                            raise NoMarketDataError(f"Binance rejected symbol: {msg}")
                        raise VendorError(f"Binance API error (HTTP {status}, code {code}): {msg}")
                except Exception:
                    pass
            raise VendorError(f"Binance client error (HTTP {status}) during {operation}")

    def _parse_json(self, resp: Any, operation: str) -> Any:
        """Verify response code and return parsed JSON data."""
        self._check_response(resp, operation)
        data = getattr(resp, "data", None)
        if isinstance(data, (dict, list)):
            return data
        if isinstance(data, str):
            try:
                return json.loads(data)
            except Exception as exc:
                raise VendorError(f"Failed to decode JSON from Binance {operation}: {exc}") from exc
        raise VendorError(f"Unexpected data type from Binance {operation}: {type(data)}")

    def _parse_single_symbol_filter(
        self, sym_data: dict[str, Any], canonical_id: str
    ) -> SymbolFilterDTO:
        """Parse raw exchangeInfo symbol entry into a SymbolFilterDTO."""
        base = sym_data.get("baseAsset", "")
        quote = sym_data.get("quoteAsset", "")
        price_prec = int(sym_data.get("quotePrecision", 2))
        qty_prec = int(sym_data.get("baseAssetPrecision", 6))

        tick_size = Decimal("0.01")
        step_size = Decimal("0.00001")
        min_qty = Decimal("0.00001")
        max_qty = Decimal("9000.0")
        min_notional = Decimal("5.0")

        for f in sym_data.get("filters", []):
            f_type = f.get("filterType")
            if f_type == "PRICE_FILTER":
                if f.get("tickSize"):
                    tick_size = Decimal(str(f["tickSize"]))
            elif f_type == "LOT_SIZE":
                if f.get("stepSize"):
                    step_size = Decimal(str(f["stepSize"]))
                if f.get("minQty"):
                    min_qty = Decimal(str(f["minQty"]))
                if f.get("maxQty"):
                    max_qty = Decimal(str(f["maxQty"]))
            elif f_type in ("NOTIONAL", "MIN_NOTIONAL"):
                if f.get("minNotional"):
                    min_notional = Decimal(str(f["minNotional"]))

        return SymbolFilterDTO(
            symbol=canonical_id,
            base_asset=base,
            quote_asset=quote,
            price_precision=price_prec,
            quantity_precision=qty_prec,
            tick_size=tick_size,
            step_size=step_size,
            min_quantity=min_qty,
            max_quantity=max_qty,
            min_notional=min_notional,
            exchange=self.provider_name,
        )
