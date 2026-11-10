"""Provider capabilities and metadata value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence


@dataclass(frozen=True)
class ProviderCapabilities:
    """Immutable capability matrix declaring supported data streams and features."""

    quote: bool = False
    ohlcv: bool = False
    orderbook: bool = False
    funding_rate: bool = False
    open_interest: bool = False
    liquidations: bool = False
    news: bool = False
    macro: bool = False
    websocket: bool = False
    historical_data: bool = False
    economic_calendar: bool = False
    sentiment: bool = False
    custom_capabilities: tuple[str, ...] = ()

    def supports(self, feature_name: str) -> bool:
        """Query if capability is enabled (case-insensitive)."""
        if not feature_name or not isinstance(feature_name, str):
            return False
        feat = feature_name.strip().lower()
        if hasattr(self, feat):
            val = getattr(self, feat)
            if isinstance(val, bool):
                return val
        return feat in tuple(c.strip().lower() for c in self.custom_capabilities)


@dataclass(frozen=True)
class ProviderMetadata:
    """Metadata describing operational profile and routing parameters."""

    provider_name: str
    version: str = "1.0.0"
    is_free_tier: bool = True
    rate_limit_rpm: int = 1200
    supports_realtime: bool = True
    supported_asset_classes: tuple[str, ...] = ("crypto",)
    priority: int = 100
    # Reserved slots for future routing decisions
    last_known_health: str = "UNKNOWN"
    last_known_latency_ms: Decimal | None = None
    freshness_sla_seconds: int = 5
