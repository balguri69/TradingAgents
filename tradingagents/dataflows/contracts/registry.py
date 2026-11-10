"""Provider discovery and registration protocol."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from tradingagents.dataflows.contracts.provider import MarketDataProvider


@runtime_checkable
class ProviderRegistry(Protocol):
    """Structural protocol for provider discovery and dynamic registration."""

    def register(self, provider: MarketDataProvider, priority: int = 100) -> None:
        """Register a provider instance with a default priority (lower number = higher priority)."""
        ...

    def get_provider(self, provider_name: str) -> MarketDataProvider | None:
        """Retrieve a registered provider by name."""
        ...

    def get_candidates(
        self, symbol: str, feature_name: str
    ) -> Sequence[MarketDataProvider]:
        """Return candidate providers supporting symbol and feature, ranked by priority."""
        ...

    def list_providers(self) -> Sequence[str]:
        """List all registered provider names."""
        ...
