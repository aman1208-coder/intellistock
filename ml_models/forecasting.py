"""Daily demand forecasting with a regularized regression model."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge


MIN_TRAINING_DAYS = 28


def _feature_row(
    history: list[float],
    index: int,
    weekday: int,
    normalization_length: int,
) -> list[float]:
    window_7 = history[-7:]
    window_28 = history[-28:]
    angle = 2 * math.pi * weekday / 7
    return [
        index / max(normalization_length - 1, 1),
        math.sin(angle),
        math.cos(angle),
        history[-1],
        history[-7],
        history[-14],
        float(np.mean(window_7)),
        float(np.mean(window_28)),
    ]


def forecast_daily_demand(
    daily_sales: pd.Series,
    horizon_days: int = 14,
) -> list[float]:
    """Forecast nonnegative daily demand for the requested future horizon.

    ``daily_sales`` should be a complete, chronologically ordered daily series;
    missing sale dates should already be represented as zeroes.
    """
    if not 1 <= horizon_days <= 30:
        raise ValueError("horizon_days must be between 1 and 30.")

    sales = pd.to_numeric(daily_sales, errors="coerce").fillna(0).clip(lower=0)
    if sales.empty:
        return [0.0] * horizon_days

    history = sales.astype(float).tolist()
    if len(history) <= MIN_TRAINING_DAYS:
        average = float(np.mean(history))
        return [max(0.0, average)] * horizon_days

    dates = pd.DatetimeIndex(pd.to_datetime(sales.index))
    training_features: list[list[float]] = []
    training_targets: list[float] = []
    for index in range(MIN_TRAINING_DAYS, len(history)):
        training_features.append(
            _feature_row(
                history[:index],
                index,
                dates[index].dayofweek,
                len(history),
            )
        )
        training_targets.append(history[index])

    model = Ridge(alpha=1.0)
    model.fit(np.asarray(training_features), np.asarray(training_targets))

    predictions: list[float] = []
    for offset in range(horizon_days):
        next_index = len(history)
        weekday = (dates[-1].dayofweek + offset + 1) % 7
        features = _feature_row(history, next_index, weekday, len(sales))
        prediction = max(0.0, float(model.predict([features])[0]))
        predictions.append(prediction)
        history.append(prediction)

    return predictions