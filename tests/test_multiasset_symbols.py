"""Comprehensive unit tests for Multi-Asset Symbol Normalization & Classification.

Strictly covers the Feature 1.1 approved milestone scope:
  - BTC, XBT, and crypto variants
  - XAUUSD, GOLD, and precious metal commodity variants
  - USDJPY and spot forex pairs
  - Extensibility demonstration (Open/Closed Principle)
  - Asset classification (crypto, commodity, forex, stock)
  - Invalid symbols and edge cases
  - Path traversal security via safe_ticker_component
  - 100% backward compatibility regression for equities and regional indices
"""

import unittest

from tradingagents.dataflows.symbols import (
    AssetClass,
    _ALIASES,
    classify_asset,
    crypto_base,
    is_commodity,
    is_crypto,
    is_forex,
    normalize_symbol,
    resolve_asset_identity,
    safe_ticker_component,
)


class TestTargetAssetsNormalization(unittest.TestCase):
    """Specific requirements for BTC, XBT, XAUUSD, GOLD, USDJPY."""

    def test_bitcoin_variants_normalize_to_yahoo_canonical(self):
        for raw in (
            "BTC", "btc", "BTCUSD", "btcusd", "BTC-USD", "btc-usd",
            "BTCUSDT", "btcusdt", "BTC/USDT", "btc/usdt", "BTC/USD", "btc/usd",
            "BTCUSD+", "BTC-USDC",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_symbol(raw), "BTC-USD")
                self.assertEqual(classify_asset(raw), AssetClass.CRYPTO)
                self.assertTrue(is_crypto(raw))

    def test_xbt_iso_variants_normalize_to_bitcoin(self):
        for raw in ("XBT", "xbt", "XBTUSD", "xbtusd", "XBTUSDT", "xbtusdt", "XBT/USD", "XBT/USDT"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_symbol(raw), "BTC-USD")
                self.assertEqual(classify_asset(raw), AssetClass.CRYPTO)
                self.assertTrue(is_crypto(raw))

    def test_gold_variants_normalize_to_comex_futures(self):
        for raw in (
            "XAUUSD", "xauusd", "XAUUSD+", "xauusd+", "XAU", "xau",
            "GOLD", "gold", "XAU/USD", "xau/usd",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_symbol(raw), "GC=F")
                self.assertEqual(classify_asset(raw), AssetClass.COMMODITY)
                self.assertTrue(is_commodity(raw))

    def test_usdjpy_variants_normalize_to_yahoo_forex(self):
        for raw in (
            "USDJPY", "usdjpy", "USDJPY+", "usdjpy+",
            "USD/JPY", "usd/jpy", "USD-JPY", "usd-jpy",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_symbol(raw), "USDJPY=X")
                self.assertEqual(classify_asset(raw), AssetClass.FOREX)
                self.assertTrue(is_forex(raw))


class TestExtensibleRegistryArchitecture(unittest.TestCase):
    """Verify registry extensibility without modifying core resolution logic."""

    def test_runtime_custom_alias_registration(self):
        # Demonstrates Open/Closed Principle: custom or future asset can be added cleanly
        test_alias = "TESTCOIN"
        test_canonical = "TEST-USD"
        _ALIASES[test_alias] = test_canonical
        try:
            self.assertEqual(normalize_symbol(test_alias), test_canonical)
            self.assertEqual(normalize_symbol(test_alias.lower()), test_canonical)
        finally:
            _ALIASES.pop(test_alias, None)


class TestAssetClassification(unittest.TestCase):
    """Test multi-asset classification into crypto, commodity, forex, and stock."""

    def test_crypto_classification(self):
        self.assertEqual(classify_asset("BTC"), AssetClass.CRYPTO)
        self.assertEqual(classify_asset("XBT"), AssetClass.CRYPTO)
        self.assertEqual(classify_asset("BTCUSDT"), AssetClass.CRYPTO)
        self.assertEqual(classify_asset("BTC/USDT"), AssetClass.CRYPTO)
        self.assertTrue(is_crypto("BTC-USD"))

    def test_commodity_classification(self):
        self.assertEqual(classify_asset("XAUUSD"), AssetClass.COMMODITY)
        self.assertEqual(classify_asset("XAU"), AssetClass.COMMODITY)
        self.assertEqual(classify_asset("GOLD"), AssetClass.COMMODITY)
        self.assertEqual(classify_asset("GC=F"), AssetClass.COMMODITY)
        self.assertTrue(is_commodity("XAUUSD"))

    def test_forex_classification(self):
        self.assertEqual(classify_asset("USDJPY"), AssetClass.FOREX)
        self.assertEqual(classify_asset("USD/JPY"), AssetClass.FOREX)
        self.assertEqual(classify_asset("USDJPY=X"), AssetClass.FOREX)
        self.assertTrue(is_forex("USD/JPY"))

    def test_stock_classification(self):
        self.assertEqual(classify_asset("AAPL"), AssetClass.STOCK)
        self.assertEqual(classify_asset("MSFT"), AssetClass.STOCK)
        self.assertEqual(classify_asset("0700.HK"), AssetClass.STOCK)
        self.assertEqual(classify_asset("SPY"), AssetClass.STOCK)
        self.assertFalse(is_crypto("AAPL"))
        self.assertFalse(is_forex("AAPL"))
        self.assertFalse(is_commodity("AAPL"))


class TestResolveAssetIdentity(unittest.TestCase):
    """Test full institutional identity metadata resolution for approved scope."""

    def test_resolve_btc_identity(self):
        identity = resolve_asset_identity("BTC/USDT")
        self.assertEqual(identity.canonical_symbol, "BTC-USD")
        self.assertEqual(identity.asset_class, AssetClass.CRYPTO)
        self.assertEqual(identity.ccxt_symbol, "BTC/USDT")
        self.assertEqual(identity.display_name, "Bitcoin (BTC)")

    def test_resolve_xbt_identity(self):
        identity = resolve_asset_identity("XBT")
        self.assertEqual(identity.canonical_symbol, "BTC-USD")
        self.assertEqual(identity.asset_class, AssetClass.CRYPTO)
        self.assertEqual(identity.ccxt_symbol, "BTC/USDT")

    def test_resolve_gold_identity(self):
        identity = resolve_asset_identity("XAUUSD")
        self.assertEqual(identity.canonical_symbol, "GC=F")
        self.assertEqual(identity.asset_class, AssetClass.COMMODITY)
        self.assertEqual(identity.display_name, "Gold Spot / COMEX Futures")

    def test_resolve_usdjpy_identity(self):
        identity = resolve_asset_identity("USD/JPY")
        self.assertEqual(identity.canonical_symbol, "USDJPY=X")
        self.assertEqual(identity.asset_class, AssetClass.FOREX)
        self.assertEqual(identity.display_name, "USD/JPY Spot Forex")

    def test_resolve_stock_identity(self):
        identity = resolve_asset_identity("AAPL")
        self.assertEqual(identity.canonical_symbol, "AAPL")
        self.assertEqual(identity.asset_class, AssetClass.STOCK)
        self.assertIsNone(identity.ccxt_symbol)


class TestInvalidAndEdgeCases(unittest.TestCase):
    """Edge cases, nullish inputs, and security checks."""

    def test_empty_and_null_inputs(self):
        self.assertEqual(normalize_symbol(""), "")
        self.assertIsNone(normalize_symbol(None))
        self.assertEqual(classify_asset(""), AssetClass.STOCK)
        self.assertEqual(classify_asset(None), AssetClass.STOCK)
        self.assertIsNone(crypto_base(None))
        self.assertIsNone(crypto_base(""))

    def test_whitespace_and_mixed_case(self):
        self.assertEqual(normalize_symbol("  btcusd  "), "BTC-USD")
        self.assertEqual(normalize_symbol("  xauusd+ "), "GC=F")
        self.assertEqual(normalize_symbol("  usd/jpy  "), "USDJPY=X")

    def test_six_letter_non_currency_not_mangled_to_forex(self):
        # Plain stock tickers that happen to be 6 letters
        self.assertEqual(normalize_symbol("ABCDEF"), "ABCDEF")
        self.assertEqual(classify_asset("ABCDEF"), AssetClass.STOCK)

    def test_safe_ticker_component_valid(self):
        for valid in ("BTC-USD", "GC=F", "USDJPY=X", "AAPL", "0700.HK", "XAUUSD+"):
            self.assertEqual(safe_ticker_component(valid), valid)

    def test_safe_ticker_component_rejects_path_traversal(self):
        for dangerous in ("../etc/passwd", "..", "...", "foo/bar", "foo\\bar", "", None):
            with self.subTest(dangerous=dangerous):
                with self.assertRaises(ValueError):
                    safe_ticker_component(dangerous)


class TestEquityBackwardCompatibilityRegression(unittest.TestCase):
    """Guarantees 100% backward compatibility for existing equities and indices."""

    def test_plain_equities_unchanged(self):
        for sym in ("AAPL", "MSFT", "TSM", "BRK.B", "0700.HK", "^GSPC", "GC=F"):
            self.assertEqual(normalize_symbol(sym), sym)

    def test_hkex_padding_rules(self):
        self.assertEqual(normalize_symbol("09992.HK"), "9992.HK")
        self.assertEqual(normalize_symbol("700.HK"), "0700.HK")
        self.assertEqual(normalize_symbol("00001.HK"), "0001.HK")

    def test_shanghai_suffix_mapping(self):
        self.assertEqual(normalize_symbol("600519.SH"), "600519.SS")
        self.assertEqual(normalize_symbol("600519.SS"), "600519.SS")


if __name__ == "__main__":
    unittest.main()
