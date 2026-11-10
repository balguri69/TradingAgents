"""Phase 12: Execution Engine subsystem coordinator."""

from __future__ import annotations

import threading
from collections import OrderedDict
from decimal import Decimal
from typing import Sequence

from tradingagents.dataflows.contracts.features import FeatureStore
from tradingagents.execution.adapters.paper import PaperBrokerAdapter
from tradingagents.execution.config import ExecutionConfig
from tradingagents.execution.dto import (
    ExecutionReportDTO,
    OrderIntentDTO,
    PositionDTO,
)
from tradingagents.execution.enums import OrderType
from tradingagents.execution.planner import ExecutionPlanner
from tradingagents.execution.protocols import BrokerAdapter, ExecutionEngineProtocol
from tradingagents.orchestration.dto import MarketAssessmentDTO
from tradingagents.risk.dto import RiskAssessmentDTO


class ExecutionEngine(ExecutionEngineProtocol):
    """Institutional execution orchestration engine.
    
    Coordinates:
    - ExecutionPlanner: Evaluates safeguards and derives OrderIntentDTO.
    - BrokerAdapter: Routes order intents to execution venues (paper or live).
    - ExecutionTracker: Tracks order lifecycle and positions.
    - FeatureStore: Persists point-in-time ExecutionReportDTOs.
    
    Thread-safe and deterministic.
    """

    def __init__(
        self,
        config: ExecutionConfig | None = None,
        broker: BrokerAdapter | None = None,
        feature_store: FeatureStore | None = None,
    ) -> None:
        self._config = config or ExecutionConfig()
        self._broker = broker or PaperBrokerAdapter(config=self._config)
        self._planner = ExecutionPlanner(config=self._config)
        self._feature_store = feature_store
        self._lock = threading.RLock()
        self._cache: OrderedDict[tuple, OrderIntentDTO] = OrderedDict()

    @property
    def config(self) -> ExecutionConfig:
        return self._config

    @property
    def broker(self) -> BrokerAdapter:
        return self._broker

    @property
    def planner(self) -> ExecutionPlanner:
        return self._planner

    @property
    def feature_store(self) -> FeatureStore | None:
        return self._feature_store

    def plan(
        self,
        assessment: MarketAssessmentDTO,
        risk: RiskAssessmentDTO,
        current_price: Decimal | None = None,
        quantity: Decimal | None = None,
        order_type: OrderType | None = None,
    ) -> OrderIntentDTO:
        """Derive an executable or risk-gated OrderIntentDTO with bounded LRU memoization."""
        cache_key = (
            assessment.symbol,
            assessment.timeframe.value,
            assessment.timestamp.isoformat(),
            str(current_price) if current_price is not None else None,
            str(quantity) if quantity is not None else None,
            order_type.value if order_type is not None else None,
            str(assessment.confidence),
            risk.risk_level.value,
        )

        with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

            intent = self._planner.plan(
                assessment=assessment,
                risk=risk,
                current_price=current_price,
                quantity=quantity,
                order_type=order_type,
            )

            if len(self._cache) >= self._config.max_cache_size:
                self._cache.popitem(last=False)
            self._cache[cache_key] = intent
            return intent

    def execute(
        self,
        intent: OrderIntentDTO,
        store: FeatureStore | None = None,
        store_results: bool = True,
        ttl_seconds: int | None = None,
    ) -> ExecutionReportDTO:
        """Route OrderIntentDTO through broker adapter and optionally persist report to FeatureStore."""
        report = self._broker.submit_order(intent)

        target_store = store or self._feature_store
        if store_results and target_store is not None:
            target_store.store_feature(report, ttl_seconds=ttl_seconds)

        return report

    def assess_and_execute(
        self,
        assessment: MarketAssessmentDTO,
        risk: RiskAssessmentDTO,
        current_price: Decimal | None = None,
        quantity: Decimal | None = None,
        order_type: OrderType | None = None,
        store: FeatureStore | None = None,
        store_results: bool = True,
        ttl_seconds: int | None = None,
    ) -> ExecutionReportDTO:
        """Convenience end-to-end pipeline: plan order intent and execute immediately."""
        intent = self.plan(
            assessment=assessment,
            risk=risk,
            current_price=current_price,
            quantity=quantity,
            order_type=order_type,
        )
        return self.execute(
            intent=intent,
            store=store,
            store_results=store_results,
            ttl_seconds=ttl_seconds,
        )

    def cancel(self, order_id: str) -> ExecutionReportDTO:
        """Cancel an open order on the broker adapter."""
        return self._broker.cancel_order(order_id)

    def get_order(self, order_id: str) -> ExecutionReportDTO | None:
        """Retrieve order status by order ID."""
        return self._broker.get_order_status(order_id)

    def get_open_orders(self, symbol: str | None = None) -> Sequence[ExecutionReportDTO]:
        """Retrieve active open orders."""
        return self._broker.get_open_orders(symbol)

    def get_position(self, symbol: str) -> PositionDTO:
        """Retrieve current position for a given symbol."""
        return self._broker.get_position(symbol)

    def get_balance(self, asset: str) -> Decimal:
        """Retrieve liquid balance for an asset."""
        return self._broker.get_balance(asset)

    def clear_cache(self) -> None:
        """Clear the LRU cache."""
        with self._lock:
            self._cache.clear()
