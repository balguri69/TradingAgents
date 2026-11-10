"""Domain market data transfer objects with financial invariant validations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tradingagents.dataflows.dto.validation import (
    validate_non_negative_decimal,
    validate_positive_decimal,
    validate_utc_datetime,
)
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError


@dataclass(frozen=True)
class QuoteDTO:
    """Real-time or point-in-time price snapshot with strict financial validation."""

    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    volume_24h: Decimal
    timestamp: datetime
    provider: str = ""

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        validate_positive_decimal(self.price, "price")
        validate_non_negative_decimal(self.bid, "bid")
        validate_positive_decimal(self.ask, "ask")
        if self.bid > self.ask:
            raise DTOValidationError(f"Crossed quote invalid: bid ({self.bid}) cannot exceed ask ({self.ask})")
        validate_non_negative_decimal(self.bid_size, "bid_size")
        validate_non_negative_decimal(self.ask_size, "ask_size")
        validate_non_negative_decimal(self.volume_24h, "volume_24h")
        validate_utc_datetime(self.timestamp, "timestamp")


@dataclass(frozen=True)
class CandleDTO:
    """Single OHLCV candlestick with strict price bound validations."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        validate_utc_datetime(self.timestamp, "timestamp")
        validate_positive_decimal(self.open, "open")
        validate_positive_decimal(self.high, "high")
        validate_positive_decimal(self.low, "low")
        validate_positive_decimal(self.close, "close")
        validate_non_negative_decimal(self.volume, "volume")

        if self.low > self.high:
            raise DTOValidationError(f"Invalid candle bounds: low ({self.low}) cannot exceed high ({self.high})")
        if not (self.low <= self.open <= self.high):
            raise DTOValidationError(
                f"Invalid candle bounds: open ({self.open}) must be within [low: {self.low}, high: {self.high}]"
            )
        if not (self.low <= self.close <= self.high):
            raise DTOValidationError(
                f"Invalid candle bounds: close ({self.close}) must be within [low: {self.low}, high: {self.high}]"
            )


@dataclass(frozen=True)
class OHLCVSeriesDTO:
    """Ordered sequence of candlesticks."""

    symbol: str
    timeframe: Timeframe
    candles: tuple[CandleDTO, ...]
    provider: str = ""

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(self.timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be an instance of Timeframe enum, got {type(self.timeframe)}")
        if not isinstance(self.candles, tuple):
            raise DTOValidationError(f"candles must be a tuple, got {type(self.candles)}")
        for i, c in enumerate(self.candles):
            if not isinstance(c, CandleDTO):
                raise DTOValidationError(f"Candle at index {i} must be a CandleDTO instance")


@dataclass(frozen=True)
class OrderBookLevelDTO:
    """Single price level in an order book."""

    price: Decimal
    quantity: Decimal

    def __post_init__(self) -> None:
        validate_positive_decimal(self.price, "price")
        validate_non_negative_decimal(self.quantity, "quantity")


@dataclass(frozen=True)
class OrderBookDTO:
    """L2 Top-of-Book market depth with spread validation."""

    symbol: str
    timestamp: datetime
    bids: tuple[OrderBookLevelDTO, ...]
    asks: tuple[OrderBookLevelDTO, ...]
    spread_bps: Decimal
    provider: str = ""

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        validate_utc_datetime(self.timestamp, "timestamp")
        validate_non_negative_decimal(self.spread_bps, "spread_bps")
        if not isinstance(self.bids, tuple):
            raise DTOValidationError("bids must be a tuple")
        if not isinstance(self.asks, tuple):
            raise DTOValidationError("asks must be a tuple")


@dataclass(frozen=True)
class FundingRateDTO:
    """Derivative perpetual swap funding rate and leverage carry cost."""

    symbol: str
    funding_rate: Decimal
    annualized_rate: Decimal
    funding_time: datetime
    mark_price: Decimal | None = None
    predicted_rate: Decimal | None = None
    exchange: str = ""

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(self.funding_rate, Decimal):
            raise DTOValidationError("funding_rate must be a Decimal")
        if not isinstance(self.annualized_rate, Decimal):
            raise DTOValidationError("annualized_rate must be a Decimal")
        validate_utc_datetime(self.funding_time, "funding_time")
        if self.mark_price is not None:
            validate_positive_decimal(self.mark_price, "mark_price")
        if self.predicted_rate is not None and not isinstance(self.predicted_rate, Decimal):
            raise DTOValidationError("predicted_rate must be a Decimal or None")


@dataclass(frozen=True)
class OpenInterestDTO:
    """Futures market open interest snapshot."""

    symbol: str
    open_interest: Decimal
    open_interest_usd: Decimal | None
    timestamp: datetime
    exchange: str = "binance"

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        validate_non_negative_decimal(self.open_interest, "open_interest")
        if self.open_interest_usd is not None:
            validate_non_negative_decimal(self.open_interest_usd, "open_interest_usd")
        validate_utc_datetime(self.timestamp, "timestamp")


@dataclass(frozen=True)
class MarkPriceDTO:
    """Derivative perpetual mark price, index price, and real-time funding metrics."""

    symbol: str
    mark_price: Decimal
    index_price: Decimal
    timestamp: datetime
    estimated_settle_price: Decimal | None = None
    last_funding_rate: Decimal | None = None
    next_funding_time: datetime | None = None
    exchange: str = "binance"

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        validate_positive_decimal(self.mark_price, "mark_price")
        validate_positive_decimal(self.index_price, "index_price")
        validate_utc_datetime(self.timestamp, "timestamp")
        if self.estimated_settle_price is not None:
            validate_positive_decimal(self.estimated_settle_price, "estimated_settle_price")
        if self.last_funding_rate is not None and not isinstance(self.last_funding_rate, Decimal):
            raise DTOValidationError("last_funding_rate must be a Decimal or None")
        if self.next_funding_time is not None:
            validate_utc_datetime(self.next_funding_time, "next_funding_time")


@dataclass(frozen=True)
class SymbolFilterDTO:
    """Venue trading rules and precision limits for an instrument."""

    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    tick_size: Decimal
    step_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal
    exchange: str = "binance"

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not self.base_asset or not isinstance(self.base_asset, str):
            raise DTOValidationError("base_asset must be a non-empty string")
        if not self.quote_asset or not isinstance(self.quote_asset, str):
            raise DTOValidationError("quote_asset must be a non-empty string")
        if self.price_precision < 0 or self.quantity_precision < 0:
            raise DTOValidationError("precision values must be non-negative integers")
        validate_positive_decimal(self.tick_size, "tick_size")
        validate_positive_decimal(self.step_size, "step_size")
        validate_positive_decimal(self.min_quantity, "min_quantity")
        validate_positive_decimal(self.max_quantity, "max_quantity")
        validate_non_negative_decimal(self.min_notional, "min_notional")


@dataclass(frozen=True)
class ExchangeInfoDTO:
    """Venue exchange metadata and active trading symbol filters."""

    exchange: str
    server_time: datetime
    symbols: tuple[SymbolFilterDTO, ...]

    def __post_init__(self) -> None:
        if not self.exchange or not isinstance(self.exchange, str):
            raise DTOValidationError("exchange must be a non-empty string")
        validate_utc_datetime(self.server_time, "server_time")
        if not isinstance(self.symbols, tuple):
            raise DTOValidationError("symbols must be a tuple")
        for s in self.symbols:
            if not isinstance(s, SymbolFilterDTO):
                raise DTOValidationError("All items in symbols must be SymbolFilterDTO instances")
