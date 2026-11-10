"""Volume Profile deterministic computer with Value Area and Point of Control (POC)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from tradingagents.dataflows.contracts.features import FeatureComputer
from tradingagents.dataflows.dto.features import VolumeProfileDTO
from tradingagents.dataflows.dto.market_data import CandleDTO, OHLCVSeriesDTO
from tradingagents.dataflows.enums import Timeframe
from tradingagents.dataflows.exceptions import DTOValidationError
from tradingagents.dataflows.features.indicators.base import validate_ohlcv_series


class VolumeProfileComputer(FeatureComputer):
    """Institutional Volume Profile computer calculating POC, VAH, and VAL."""

    def __init__(
        self,
        num_bins: int = 24,
        value_area_pct: Decimal | float = Decimal("0.70"),
        rolling_window: int | None = None,
        custom_name: str | None = None,
    ) -> None:
        if not isinstance(num_bins, int) or num_bins < 2:
            raise DTOValidationError(f"num_bins must be an integer >= 2, got {num_bins}")
        dec_va = Decimal(str(value_area_pct))
        if not (Decimal("0.10") <= dec_va <= Decimal("1.00")):
            raise DTOValidationError(f"value_area_pct must be between 0.10 and 1.00, got {value_area_pct}")
        if rolling_window is not None and (not isinstance(rolling_window, int) or rolling_window <= 0):
            raise DTOValidationError(f"rolling_window must be a positive integer, got {rolling_window}")

        self._num_bins = num_bins
        self._value_area_pct = dec_va
        self._rolling_window = rolling_window
        self._name = custom_name or f"VP_{num_bins}_{int(dec_va * 100)}"

    @property
    def feature_name(self) -> str:
        return self._name

    def _compute_profile_for_window(
        self,
        symbol: str,
        timeframe: Timeframe,
        window: Sequence[CandleDTO],
    ) -> VolumeProfileDTO:
        """Compute VolumeProfileDTO over a fixed window of candles."""
        target_timestamp = window[-1].timestamp
        total_volume = sum(c.volume for c in window)

        min_price = min(c.low for c in window)
        max_price = max(c.high for c in window)

        # Edge case: zero price spread or zero volume
        if min_price == max_price or total_volume == Decimal("0"):
            flat_price = window[-1].close
            return VolumeProfileDTO(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=target_timestamp,
                feature_name=self._name,
                poc=flat_price,
                vah=flat_price,
                val=flat_price,
                total_volume=total_volume,
            )

        # Discretize price space into equal-width bins
        price_spread = max_price - min_price
        bin_width = price_spread / Decimal(self._num_bins)

        bin_lows = [min_price + Decimal(i) * bin_width for i in range(self._num_bins)]
        bin_highs = [bin_lows[i] + bin_width for i in range(self._num_bins)]
        bin_highs[-1] = max_price  # Ensure clean upper bound
        bin_midpoints = [(bin_lows[i] + bin_highs[i]) / Decimal("2") for i in range(self._num_bins)]
        bin_volumes = [Decimal("0") for _ in range(self._num_bins)]

        # Distribute volume proportional to overlap with each bin
        for c in window:
            if c.volume == Decimal("0"):
                continue
            candle_spread = c.high - c.low
            if candle_spread == Decimal("0"):
                # Flat candle: assign all volume to matching bin
                for b_idx in range(self._num_bins):
                    if bin_lows[b_idx] <= c.close <= bin_highs[b_idx]:
                        bin_volumes[b_idx] += c.volume
                        break
                continue

            for b_idx in range(self._num_bins):
                b_low = bin_lows[b_idx]
                b_high = bin_highs[b_idx]
                # Check overlap
                overlap_low = max(c.low, b_low)
                overlap_high = min(c.high, b_high)
                if overlap_low < overlap_high:
                    overlap_fraction = (overlap_high - overlap_low) / candle_spread
                    bin_volumes[b_idx] += (c.volume * overlap_fraction)

        # Point of Control (POC): bin with maximum accumulated volume
        max_vol_idx = 0
        max_vol = bin_volumes[0]
        for b_idx in range(1, self._num_bins):
            if bin_volumes[b_idx] > max_vol:
                max_vol = bin_volumes[b_idx]
                max_vol_idx = b_idx

        poc_price = bin_midpoints[max_vol_idx]

        # Value Area: Greedily expand outward from POC until target volume reached
        target_va_volume = total_volume * self._value_area_pct
        accumulated_va_volume = bin_volumes[max_vol_idx]
        low_idx = max_vol_idx
        high_idx = max_vol_idx

        while accumulated_va_volume < target_va_volume:
            can_expand_down = low_idx > 0
            can_expand_up = high_idx < self._num_bins - 1

            if not can_expand_down and not can_expand_up:
                break

            vol_down = bin_volumes[low_idx - 1] if can_expand_down else Decimal("-1")
            vol_up = bin_volumes[high_idx + 1] if can_expand_up else Decimal("-1")

            if vol_up >= vol_down:
                high_idx += 1
                accumulated_va_volume += bin_volumes[high_idx]
            else:
                low_idx -= 1
                accumulated_va_volume += bin_volumes[low_idx]

        val_price = bin_lows[low_idx]
        vah_price = bin_highs[high_idx]

        # Enforce financial invariants val <= poc <= vah
        if val_price > poc_price:
            val_price = poc_price
        if vah_price < poc_price:
            vah_price = poc_price

        return VolumeProfileDTO(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=target_timestamp,
            feature_name=self._name,
            poc=poc_price,
            vah=vah_price,
            val=val_price,
            total_volume=total_volume,
        )

    def compute(
        self,
        symbol: str,
        timeframe: Timeframe,
        data: OHLCVSeriesDTO,
        **kwargs: Any,
    ) -> Sequence[VolumeProfileDTO]:
        """Compute Volume Profile observations."""
        validate_ohlcv_series(data, min_required=1)
        candles = data.candles

        if self._rolling_window is None:
            # Single observation over the full provided series
            return [self._compute_profile_for_window(symbol, timeframe, candles)]

        # Rolling window observations
        if len(candles) < self._rolling_window:
            raise DTOValidationError(
                f"Insufficient candles for rolling volume profile: required {self._rolling_window}, got {len(candles)}"
            )

        results: list[VolumeProfileDTO] = []
        for idx in range(self._rolling_window - 1, len(candles)):
            window = candles[idx - self._rolling_window + 1 : idx + 1]
            results.append(self._compute_profile_for_window(symbol, timeframe, window))

        return results
