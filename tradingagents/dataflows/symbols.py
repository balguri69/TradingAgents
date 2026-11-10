"""Symbol normalization for vendor calls, and ticker values safe to use in a path.

Yahoo Finance (the default vendor) uses specific ticker conventions that
differ from the broker / TradingView / MT5 style symbols users often type:

    user types        Yahoo wants       why
    ---------------   ---------------   -----------------------------------
    XAUUSD, XAUUSD+   GC=F              gold has no forex pair on Yahoo;
                                        it is quoted as a COMEX future
    EURUSD, USDJPY    EURUSD=X          spot forex pairs take a ``=X`` suffix
    BTC, BTCUSD       BTC-USD           crypto pairs use a ``-`` separator
    SPX500, US500     ^GSPC             index CFDs map to Yahoo index symbols
    09992.HK, 700.HK  9992.HK, 0700.HK  HK codes are zero-padded to 4 digits
    600519.SH         600519.SS         Yahoo spells Shanghai ``.SS``

Follows the Open/Closed Principle: the canonical normalization registry
can be extended for new instruments and aliases without modifying call sites.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AssetClass(str, Enum):
    """The four primary asset classes supported by the platform."""

    CRYPTO = "crypto"
    COMMODITY = "commodity"
    FOREX = "forex"
    STOCK = "stock"


# ISO-4217 codes common in retail and institutional spot forex pairs.
# A bare six-letter symbol whose halves are BOTH in this set is treated as a
# spot forex pair and given Yahoo's ``=X`` suffix.
_FOREX_CURRENCIES = frozenset(
    {
        "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
        "CNY", "CNH", "HKD", "SGD", "SEK", "NOK", "DKK", "PLN",
        "MXN", "ZAR", "TRY", "INR", "KRW", "BRL", "RUB", "THB",
    }
)

# Crypto bases that brokers quote against USD without a separator.
# Includes ISO-4217 XBT as an alias for BTC.
_CRYPTO_BASES = frozenset(
    {
        "BTC", "XBT", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH",
        "DOT", "AVAX", "LINK",
    }
)

# Explicit aliases for instruments whose broker symbol does not map to a
# Yahoo symbol by rule. Preserves all legacy mappings while registering
# approved target assets for institutional multi-asset workflows:
# BTC (BTC-USD), XBT (BTC-USD), XAUUSD (GC=F), GOLD (GC=F), USDJPY (USDJPY=X).
_ALIASES: dict[str, str] = {
    # Feature 1.1 Target: Bitcoin & ISO aliases
    "BTC": "BTC-USD",
    "BTCUSD": "BTC-USD",
    "BTCUSDT": "BTC-USD",
    "BTCUSDC": "BTC-USD",
    "XBT": "BTC-USD",
    "XBTUSD": "BTC-USD",
    "XBTUSDT": "BTC-USD",

    # Feature 1.1 Target: Gold / Precious metals (spot names -> COMEX futures)
    "XAUUSD": "GC=F",
    "XAU": "GC=F",
    "GOLD": "GC=F",

    # Existing Legacy Metals & Energy (preserved for 100% backward compatibility)
    "XAGUSD": "SI=F",
    "XAG": "SI=F",
    "XPTUSD": "PL=F",
    "XPDUSD": "PA=F",
    "WTICOUSD": "CL=F",
    "USOIL": "CL=F",
    "WTI": "CL=F",
    "BCOUSD": "BZ=F",
    "UKOIL": "BZ=F",
    "BRENT": "BZ=F",
    "NATGAS": "NG=F",
    "XNGUSD": "NG=F",
    "COPPER": "HG=F",
    "XCUUSD": "HG=F",

    # Existing Legacy Index CFDs -> Yahoo index symbols
    "SPX500": "^GSPC",
    "US500": "^GSPC",
    "SPX": "^GSPC",
    "NAS100": "^NDX",
    "US100": "^NDX",
    "USTEC": "^NDX",
    "US30": "^DJI",
    "DJI30": "^DJI",
    "WS30": "^DJI",
    "GER40": "^GDAXI",
    "GER30": "^GDAXI",
    "DE40": "^GDAXI",
    "UK100": "^FTSE",
    "JP225": "^N225",
    "JPN225": "^N225",
    "FRA40": "^FCHI",
    "EU50": "^STOXX50E",
    "HK50": "^HSI",
}

# Known commodity symbols and canonical futures codes for classification
_COMMODITY_SYMBOLS = frozenset(
    {
        "GC=F", "XAUUSD", "XAU", "GOLD",
        "SI=F", "XAGUSD", "XAG",
        "PL=F", "XPTUSD", "PA=F", "XPDUSD",
        "CL=F", "WTICOUSD", "USOIL", "WTI",
        "BZ=F", "BCOUSD", "UKOIL", "BRENT",
        "NG=F", "NATGAS", "XNGUSD",
        "HG=F", "COPPER", "XCUUSD",
    }
)

# HKEX codes as Yahoo spells them: the number zero-padded to 4 digits (#957).
_HK_CODE = re.compile(r"^(\d{1,5})\.HK$")
_SHANGHAI_SH = re.compile(r"^(\d{6})\.SH$")

# Crypto quote currencies that all map to Yahoo's USD pair. Longest first.
_CRYPTO_QUOTES = ("USDT", "USDC", "USD")


@dataclass(frozen=True)
class AssetIdentity:
    """Canonical representation of an instrument across analytical and vendor layers."""

    raw_symbol: str
    canonical_symbol: str
    asset_class: AssetClass
    yahoo_symbol: str
    ccxt_symbol: str | None = None
    display_name: str = ""


def _clean_input(raw: str) -> str:
    """Strip whitespace, trailing broker CFD qualifier ('+'), and slashes."""
    if not isinstance(raw, str):
        return ""
    s = raw.strip().upper().rstrip("+")
    return s.replace("/", "").replace(" ", "")


def crypto_base(raw: str) -> str | None:
    """Return the normalized crypto base (e.g. ``BTC``) for any crypto symbol variant.

    Recognizes:
      - Bare bases: ``BTC``, ``XBT`` (normalized to ``BTC``), ``ETH``, ``SOL``
      - Pairs: ``BTC-USD``, ``BTCUSD``, ``BTCUSDT``, ``BTC/USD``, ``XBT/USD``
    Returns None for non-crypto symbols. Purely syntactic.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    compact = _clean_input(raw).replace("-", "")

    # Direct match on known bases
    if compact in _CRYPTO_BASES:
        return "BTC" if compact == "XBT" else compact

    for quote in _CRYPTO_QUOTES:
        if compact.endswith(quote):
            base = compact[: -len(quote)]
            if base in _CRYPTO_BASES:
                return "BTC" if base == "XBT" else base
    return None


def _normalize_crypto(s: str) -> str | None:
    """Return ``<BASE>-USD`` for a known USD/USDT/USDC-quoted crypto or bare base."""
    base = crypto_base(s)
    return f"{base}-USD" if base else None


def normalize_symbol(raw: str) -> str:
    """Map any user/broker symbol to its canonical Yahoo Finance symbol.

    Resolution order (first match wins):
      1. Explicit alias table (metals, energy, index CFDs, crypto shortcuts).
      2. Crypto rule: a known crypto base (BTC, XBT...) -> ``BASE-USD``.
      3. Forex rule: six letters that are two ISO currency codes (USDJPY, EURUSD) -> ``PAIR=X``.
      4. HK rule: a numeric ``.HK`` code -> Yahoo's 4-digit padding (0700.HK).
      5. Shanghai rule: ``600519.SH`` -> ``600519.SS``.
      6. Otherwise the upper-cased symbol is returned unchanged (equities, ETFs, native Yahoo symbols).

    100% backward-compatible: preserves all existing equity, index, and commodity mappings.
    """
    if not isinstance(raw, str) or not raw.strip():
        return raw

    raw_clean = raw.strip().upper().rstrip("+")
    clean_s = _clean_input(raw)
    compact_fx = clean_s.replace("-", "")

    # 1. Alias lookup on clean symbol or original upper
    if clean_s in _ALIASES:
        canonical = _ALIASES[clean_s]
    elif raw_clean in _ALIASES:
        canonical = _ALIASES[raw_clean]
    # 2. Crypto base normalization
    elif (crypto := _normalize_crypto(raw_clean)) is not None:
        canonical = crypto
    elif (crypto := _normalize_crypto(clean_s)) is not None:
        canonical = crypto
    # 3. Forex currency pairs (six ISO letters, with optional slash or dash)
    elif len(compact_fx) == 6 and compact_fx[:3] in _FOREX_CURRENCIES and compact_fx[3:] in _FOREX_CURRENCIES:
        canonical = f"{compact_fx}=X"
    # 4. Regional exchange rules
    elif hk := _HK_CODE.match(raw_clean):
        canonical = f"{int(hk.group(1)):04d}.HK"
    elif sh := _SHANGHAI_SH.match(raw_clean):
        canonical = f"{sh.group(1)}.SS"
    else:
        canonical = raw_clean

    if canonical != raw.strip().upper():
        logger.info("Resolved symbol %r to Yahoo symbol %r", raw, canonical)
    return canonical


def classify_asset(raw: str) -> AssetClass:
    """Classify an instrument into crypto, commodity, forex, or stock.

    Deterministic and syntactic:
      - AssetClass.CRYPTO: BTC, XBT, or symbols ending in crypto quotes
      - AssetClass.COMMODITY: Precious metals (XAUUSD, GOLD, GC=F), energies (CL=F, WTI)
      - AssetClass.FOREX: Spot currency pairs (USDJPY, USD/JPY, EURUSD, USDJPY=X)
      - AssetClass.STOCK: Equities, ETFs, regional equity indices
    """
    if not isinstance(raw, str) or not raw.strip():
        return AssetClass.STOCK

    clean_s = _clean_input(raw)

    # 1. Crypto check
    if crypto_base(raw) is not None or clean_s.endswith(("-USD", "-USDT", "-USDC", "-BTC", "-ETH")):
        return AssetClass.CRYPTO

    # 2. Commodity check
    canonical = normalize_symbol(raw)
    clean_canonical = canonical.replace("/", "")
    if (
        clean_canonical in _COMMODITY_SYMBOLS
        or clean_s in _COMMODITY_SYMBOLS
        or canonical.endswith("=F")
    ):
        return AssetClass.COMMODITY

    # 3. Forex check
    if canonical.endswith("=X") or (
        len(clean_s) == 6 and clean_s[:3] in _FOREX_CURRENCIES and clean_s[3:] in _FOREX_CURRENCIES
    ):
        return AssetClass.FOREX

    return AssetClass.STOCK


def is_crypto(raw: str) -> bool:
    """Whether ``raw`` is a cryptocurrency instrument."""
    return classify_asset(raw) == AssetClass.CRYPTO


def is_commodity(raw: str) -> bool:
    """Whether ``raw`` is a commodity or precious metal instrument."""
    return classify_asset(raw) == AssetClass.COMMODITY


def is_forex(raw: str) -> bool:
    """Whether ``raw`` is a foreign exchange currency pair."""
    return classify_asset(raw) == AssetClass.FOREX


def resolve_asset_identity(raw: str) -> AssetIdentity:
    """Return canonical institutional identity and vendor mappings for an instrument.

    Strictly supports Feature 1.1 approved assets:
      - BTC / XBT (Crypto)
      - XAUUSD / GOLD (Commodity)
      - USDJPY (Forex)
    Plus standard equity / stock passthrough.
    """
    asset_cls = classify_asset(raw)
    yahoo_sym = normalize_symbol(raw)

    ccxt_sym: str | None = None
    if asset_cls == AssetClass.CRYPTO:
        base = crypto_base(raw) or "BTC"
        ccxt_sym = f"{base}/USDT"

    display_name = raw.strip().upper()
    if asset_cls == AssetClass.COMMODITY and (yahoo_sym == "GC=F" or "XAU" in yahoo_sym or "GOLD" in yahoo_sym):
        display_name = "Gold Spot / COMEX Futures"
    elif asset_cls == AssetClass.FOREX and "USDJPY" in yahoo_sym:
        display_name = "USD/JPY Spot Forex"
    elif asset_cls == AssetClass.CRYPTO and ("BTC" in yahoo_sym or "XBT" in yahoo_sym):
        display_name = "Bitcoin (BTC)"

    return AssetIdentity(
        raw_symbol=raw,
        canonical_symbol=yahoo_sym,
        asset_class=asset_cls,
        yahoo_symbol=yahoo_sym,
        ccxt_symbol=ccxt_sym,
        display_name=display_name,
    )


@dataclass(frozen=True)
class CanonicalSymbol:
    """Universal internal representation of a financial instrument across asset classes."""

    canonical_id: str
    asset_class: AssetClass
    base_asset: str
    quote_currency: str
    display_name: str
    yahoo_symbol: str
    binance_symbol: str | None = None
    coinbase_symbol: str | None = None


class SymbolResolver:
    """Universal institutional symbol resolution and vendor translation engine."""

    @classmethod
    def resolve(cls, raw: str | CanonicalSymbol) -> CanonicalSymbol:
        """Resolve any user symbol, alias, or ticket to an immutable CanonicalSymbol."""
        if isinstance(raw, CanonicalSymbol):
            return raw
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"Cannot resolve empty symbol: {raw!r}")

        identity = resolve_asset_identity(raw)
        raw_clean = _clean_input(raw)

        base = ""
        quote = ""
        binance_sym: str | None = None
        coinbase_sym: str | None = None

        if identity.asset_class == AssetClass.CRYPTO:
            base = crypto_base(raw) or "BTC"
            # In institutional spot/derivatives crypto, canonical pairs quote against USDT or USD
            quote = "USDT" if "USDT" in raw_clean else "USD"
            canonical_id = f"{base}/{quote}"
            binance_sym = f"{base}USDT"
            coinbase_sym = f"{base}-USD"
        elif identity.asset_class == AssetClass.COMMODITY:
            base = "XAU" if "XAU" in raw_clean or "GOLD" in raw_clean else raw_clean
            quote = "USD"
            canonical_id = f"{base}/{quote}"
        elif identity.asset_class == AssetClass.FOREX:
            if len(raw_clean) == 6:
                base = raw_clean[:3]
                quote = raw_clean[3:]
                canonical_id = f"{base}/{quote}"
            else:
                base = "USD"
                quote = "JPY"
                canonical_id = "USD/JPY"
        else:
            base = raw_clean
            quote = "USD"
            canonical_id = raw_clean

        return CanonicalSymbol(
            canonical_id=canonical_id,
            asset_class=identity.asset_class,
            base_asset=base,
            quote_currency=quote,
            display_name=identity.display_name or canonical_id,
            yahoo_symbol=identity.yahoo_symbol,
            binance_symbol=binance_sym,
            coinbase_symbol=coinbase_sym,
        )

    @classmethod
    def to_vendor_symbol(cls, symbol: CanonicalSymbol | str, vendor_name: str) -> str:
        """Translate a canonical symbol to vendor-specific wire symbol."""
        canonical = cls.resolve(symbol) if isinstance(symbol, str) else symbol
        vendor = vendor_name.strip().lower()

        if vendor == "binance":
            if canonical.binance_symbol:
                return canonical.binance_symbol
            if canonical.asset_class == AssetClass.CRYPTO:
                return f"{canonical.base_asset}USDT"
            raise ValueError(f"Instrument {canonical.canonical_id!r} is not supported on Binance")
        elif vendor == "yahoo":
            return canonical.yahoo_symbol
        elif vendor == "coinbase":
            if canonical.coinbase_symbol:
                return canonical.coinbase_symbol
            return f"{canonical.base_asset}-USD"
        return canonical.canonical_id


# Tickers can contain letters, digits, dot, dash, underscore, caret
# (index symbols like ^GSPC), equals (futures like GC=F), and plus
# (forex/CFD symbols like XAUUSD+). None of these enable directory
# traversal, so the value never escapes a containing directory when
# interpolated into a path. Anything else is rejected.
_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^=+]+$")


def safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    """Validate ``value`` is safe to interpolate into a filesystem path.

    Tickers come from user CLI input or from LLM tool calls, both of which
    can be influenced by attacker-controlled content (e.g. prompt injection
    embedded in fetched news). Without validation, a value like
    ``"../../../etc/foo"`` flows into ``os.path.join`` / ``Path /`` and
    escapes the configured cache, checkpoint, or results directory.

    Returns ``value`` unchanged when it matches the allowed pattern; raises
    ``ValueError`` otherwise.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"ticker must be a non-empty string, got {value!r}")
    if len(value) > max_len:
        raise ValueError(f"ticker exceeds {max_len} chars: {value!r}")
    if not _TICKER_PATH_RE.fullmatch(value):
        raise ValueError(
            f"ticker contains characters not allowed in a filesystem path: {value!r}"
        )
    # The regex above allows '.', so values like '.', '..', '...' would pass,
    # and as a path component they traverse the parent directory. Reject any
    # value that's only dots.
    if set(value) == {"."}:
        raise ValueError(f"ticker cannot consist solely of dots: {value!r}")
    return value
