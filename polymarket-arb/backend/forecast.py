"""Execution-risk forecasting with TimesFM (google/timesfm-2.5-200m-pytorch).

This is the *one* place a forecasting model fits an arbitrage bot: predicting
whether a detected mispricing will stay open long enough to fill **both** legs.
It is NOT used to predict market outcomes (that would be directional betting,
not arbitrage).

For each opportunity we track the recent series of the combined per-unit cost
(sum of the legs' best asks). The arb is profitable while that series stays
below $1. We forecast its near-term trajectory and turn it into a
`fill_score` in [0, 1] = how much of the current profit cushion is predicted to
survive the next few ticks. The engine can then skip arbs likely to vanish
before they fill (PM_MIN_FILL_SCORE), which is exactly the live fill-rate
problem.

TimesFM is optional and opt-in (PM_USE_TIMESFM=1, needs `pip install timesfm`).
A deterministic trend/volatility heuristic is the always-available fallback and
is what runs by default.
"""
from __future__ import annotations

import statistics
from collections import deque
from typing import Optional

from .config import settings
from .models import Market, Opportunity


class FillForecaster:
    def __init__(self, history: int = 64, horizon: int = 6):
        self.history = history
        self.horizon = horizon
        self._series: dict[str, deque] = {}
        self._model = None
        self._model_tried = False

    # ---- data ----------------------------------------------------------
    def observe(self, markets: list[Market]) -> None:
        """Append the current best ask of every outcome token to its series."""
        for m in markets:
            for o in m.outcomes:
                if o.best_ask is not None:
                    self._series.setdefault(
                        o.token_id, deque(maxlen=self.history)).append(o.best_ask)

    def _spread_series(self, opp: Opportunity) -> Optional[list[float]]:
        """Combined per-unit cost (sum of leg ask series), aligned by length."""
        cols = []
        for leg in opp.legs:
            s = self._series.get(leg.token_id)
            if not s:
                return None
            cols.append(list(s))
        n = min(len(c) for c in cols)
        if n < 4:
            return None
        return [sum(c[-n:][i] for c in cols) for i in range(n)]

    # ---- scoring -------------------------------------------------------
    def score(self, opp: Opportunity) -> float:
        spread = self._spread_series(opp)
        if spread is None:
            return 1.0  # no history yet → don't penalise (neutral/optimistic)
        if settings.use_timesfm:
            sc = self._score_timesfm(spread)
            if sc is not None:
                return sc
        return self._score_heuristic(spread)

    def _score_heuristic(self, spread: list[float]) -> float:
        recent = spread[-8:] if len(spread) >= 8 else spread
        cur = recent[-1]
        margin = 1.0 - cur
        if margin <= 0:
            return 0.0
        trend = recent[-1] - recent[0]
        vol = statistics.pstdev(recent) if len(recent) > 1 else 0.0
        # Project the worst near-term spread: current + rising drift + a vol buffer.
        drift = max(trend, 0.0) * (self.horizon / max(len(recent) - 1, 1))
        projected = cur + drift + vol
        return max(0.0, min(1.0, (1.0 - projected) / margin))

    def _score_timesfm(self, spread: list[float]) -> Optional[float]:
        model = self._load()
        if model is None:
            return None
        try:
            import numpy as np
            _, qf = model.forecast(horizon=self.horizon,
                                   inputs=[np.array(spread, dtype=float)])
            q = np.asarray(qf[0])
            worst = float(q[:, -1].max())  # top quantile = worst-case spread
        except Exception as exc:
            print(f"[forecast] TimesFM forecast failed: {exc}")
            return None
        cur = spread[-1]
        margin = 1.0 - cur
        if margin <= 0:
            return 0.0
        return max(0.0, min(1.0, (1.0 - worst) / margin))

    def _load(self):
        if self._model_tried:
            return self._model
        self._model_tried = True
        try:
            import timesfm
            import torch
            torch.set_float32_matmul_precision("high")
            m = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                "google/timesfm-2.5-200m-pytorch")
            m.compile(timesfm.ForecastConfig(
                max_context=1024, max_horizon=256, normalize_inputs=True,
                use_continuous_quantile_head=True, force_flip_invariance=True,
                infer_is_positive=True, fix_quantile_crossing=True,
            ))
            self._model = m
        except Exception as exc:
            print(f"[forecast] TimesFM unavailable, using heuristic: {exc}")
            self._model = None
        return self._model


def make_forecaster() -> FillForecaster:
    return FillForecaster(horizon=int(settings.forecast_horizon))
