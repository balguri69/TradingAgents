"""Abstract base class and shared utilities for specialized analytical agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Type, TypeVar

from tradingagents.dataflows.dto.features import BaseFeatureDTO
from tradingagents.dataflows.dto.validation import validate_utc_datetime
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.orchestration.enums import AgentRole

T = TypeVar("T", bound=BaseFeatureDTO)


class BaseMarketAgent(ABC):
    """Abstract base class for all deterministic specialized analytical agents."""

    @property
    @abstractmethod
    def role(self) -> AgentRole:
        """The specialized single-responsibility role of this agent."""
        ...

    @abstractmethod
    def analyze(
        self,
        symbol: str,
        timeframe: Timeframe,
        features: Mapping[str, BaseFeatureDTO],
        current_price: Decimal | None = None,
        as_of: datetime | None = None,
    ) -> Any:
        """Execute deterministic analysis over provided point-in-time features."""
        ...

    @staticmethod
    def _validate_inputs(
        symbol: str,
        timeframe: Timeframe,
        as_of: datetime | None = None,
    ) -> None:
        """Validate agent inputs."""
        if not symbol or not isinstance(symbol, str):
            raise DTOValidationError("symbol must be a non-empty string")
        if not isinstance(timeframe, Timeframe):
            raise DTOValidationError(f"timeframe must be an instance of Timeframe, got {type(timeframe)}")
        if as_of is not None:
            validate_utc_datetime(as_of, "as_of")

    @staticmethod
    def _find_feature(
        features: Mapping[str, BaseFeatureDTO],
        expected_type: Type[T],
        *aliases: str,
    ) -> T | None:
        """Case-insensitively locate a feature matching expected type or alias names."""
        for alias in aliases:
            direct = features.get(alias)
            if isinstance(direct, expected_type):
                return direct

        lower_aliases = {a.lower() for a in aliases}
        for k, v in features.items():
            if (k.lower() in lower_aliases or getattr(v, "feature_name", "").lower() in lower_aliases) and isinstance(
                v, expected_type
            ):
                return v

        for v in features.values():
            if isinstance(v, expected_type):
                return v

        return None
