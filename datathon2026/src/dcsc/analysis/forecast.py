"""Weekly forecasting of conflict pressure on maritime corridors.

The operational question is not "how much violence was there" but "what should a
routing or convoy decision assume for the next quarter". That requires a forecast
with an honest error bar, and an honest error bar requires a backtest against
benchmarks that are hard to beat.

Four models compete on one-step-ahead, expanding-window backtests over the last
``SETTINGS.backtest_weeks`` weeks:

``naive``        last week repeated - the benchmark any model must beat;
``ma4``          mean of the last four weeks - beats naive whenever the series is noisy;
``sarimax``      SARIMAX(2,1,1), a linear state-space model on the differenced series;
``gbm``          gradient boosting on lag, trend and calendar features.

Whichever wins on MAE is refitted on the full history and used for the forward
forecast. Intervals come from the empirical distribution of that model's own
backtest errors, which is more honest than a parametric interval on a series
that is plainly not Gaussian.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from ..config import SETTINGS
from ..io_utils import get_logger, save_table

LOG = get_logger("dcsc.analysis.forecast")

LAGS = (1, 2, 3, 4, 8, 12, 26, 52)


def _lag_frame(y: pd.Series) -> pd.DataFrame:
    """Supervised-learning design matrix from a weekly series."""
    df = pd.DataFrame({"y": y})
    for lag in LAGS:
        df[f"lag_{lag}"] = y.shift(lag)
    df["roll4"] = y.shift(1).rolling(4).mean()
    df["roll12"] = y.shift(1).rolling(12).mean()
    df["trend"] = np.arange(len(df))
    df["week_of_year"] = y.index.isocalendar().week.to_numpy()
    return df


def _fit_predict_gbm(train: pd.DataFrame, test_row: pd.Series) -> float:
    features = [c for c in train.columns if c != "y"]
    model = GradientBoostingRegressor(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.9,
        random_state=SETTINGS.random_state,
    )
    model.fit(train[features], train["y"])
    return float(model.predict(test_row[features].to_frame().T)[0])


def _fit_predict_sarimax(history: pd.Series) -> float:
    import statsmodels.api as sm

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = sm.tsa.SARIMAX(
            history.astype(float),
            order=(2, 1, 1),
            trend="c",
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False)
        return float(model.forecast(1).iloc[0])


def backtest(y: pd.Series, horizon_weeks: int | None = None) -> pd.DataFrame:
    """One-step-ahead expanding-window backtest of all four models."""
    horizon_weeks = horizon_weeks or SETTINGS.backtest_weeks
    design = _lag_frame(y).dropna()
    if len(design) <= horizon_weeks + 20:
        raise ValueError("series too short to backtest")

    rows = []
    split_points = design.index[-horizon_weeks:]
    for ts in split_points:
        pos = design.index.get_loc(ts)
        train = design.iloc[:pos]
        test_row = design.iloc[pos]
        history = y.loc[: design.index[pos - 1]]
        actual = float(test_row["y"])

        preds = {
            "naive": float(history.iloc[-1]),
            "ma4": float(history.iloc[-4:].mean()),
            "gbm": _fit_predict_gbm(train, test_row),
        }
        try:
            preds["sarimax"] = _fit_predict_sarimax(history)
        except Exception as exc:  # pragma: no cover - solver instability
            LOG.debug("sarimax failed at %s: %s", ts, exc)
            preds["sarimax"] = np.nan

        for model, pred in preds.items():
            rows.append({"week": ts, "model": model, "actual": actual, "predicted": pred})
    return pd.DataFrame(rows)


def score(bt: pd.DataFrame) -> pd.DataFrame:
    """MAE, RMSE and MAPE per model, plus skill against the naive benchmark."""
    bt = bt.dropna(subset=["predicted"]).copy()
    bt["err"] = bt["predicted"] - bt["actual"]
    out = (
        bt.groupby("model")
        .apply(
            lambda g: pd.Series(
                {
                    "mae": g["err"].abs().mean(),
                    "rmse": np.sqrt((g["err"] ** 2).mean()),
                    "mape": (g["err"].abs() / g["actual"].replace(0, np.nan)).mean() * 100,
                    "bias": g["err"].mean(),
                    "n": len(g),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    naive_mae = float(out.loc[out["model"] == "naive", "mae"].iloc[0])
    out["skill_vs_naive_pct"] = (1 - out["mae"] / naive_mae) * 100
    return out.sort_values("mae").reset_index(drop=True)


def forecast_forward(
    y: pd.Series, model_name: str, errors: np.ndarray, steps: int | None = None
) -> pd.DataFrame:
    """Recursive multi-step forecast with empirical prediction intervals."""
    steps = steps or SETTINGS.forecast_horizon_weeks
    history = y.copy()
    preds = []

    if model_name == "sarimax":
        import statsmodels.api as sm

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = sm.tsa.SARIMAX(
                history.astype(float),
                order=(2, 1, 1),
                trend="c",
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False)
        preds = list(fitted.forecast(steps))
    else:
        for _ in range(steps):
            design = _lag_frame(history).dropna()
            features = [c for c in design.columns if c != "y"]
            if model_name == "gbm":
                model = GradientBoostingRegressor(
                    n_estimators=300,
                    max_depth=3,
                    learning_rate=0.05,
                    subsample=0.9,
                    random_state=SETTINGS.random_state,
                )
                model.fit(design[features], design["y"])
                next_index = history.index[-1] + pd.Timedelta(weeks=1)
                extended = pd.concat([history, pd.Series([np.nan], index=[next_index])])
                row = _lag_frame(extended).iloc[-1]
                value = float(model.predict(row[features].to_frame().T)[0])
            elif model_name == "ma4":
                value = float(history.iloc[-4:].mean())
            else:
                value = float(history.iloc[-1])
            next_index = history.index[-1] + pd.Timedelta(weeks=1)
            history = pd.concat([history, pd.Series([value], index=[next_index])])
            preds.append(value)

    lo_q, hi_q = np.percentile(errors, [10, 90])
    index = pd.date_range(y.index[-1] + pd.Timedelta(weeks=1), periods=steps, freq="W-SAT")
    # Uncertainty widens with horizon: sqrt(h) is the random-walk scaling and is
    # the conservative default when the backtest only measures one-step error.
    widen = np.sqrt(np.arange(1, steps + 1))
    return pd.DataFrame(
        {
            "week": index,
            "forecast": np.clip(preds, 0, None),
            "lower": np.clip(np.array(preds) + lo_q * widen, 0, None),
            "upper": np.array(preds) + hi_q * widen,
            "model": model_name,
        }
    )


def run(pressure: pd.DataFrame, corridors: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Backtest and forecast weekly conflict pressure for the named corridors."""
    scores, forecasts = [], []
    for cid in corridors:
        series = (
            pressure[pressure["chokepoint_id"] == cid]
            .set_index("week")["events_within"]
            .asfreq("W-SAT")
            .fillna(0.0)
        )
        if len(series) < 120:
            LOG.warning("skipping %s: only %d weeks of history", cid, len(series))
            continue
        bt = backtest(series)
        sc = score(bt)
        sc.insert(0, "chokepoint_id", cid)
        scores.append(sc)

        best = sc.iloc[0]["model"]
        errs = (
            bt[bt["model"] == best]
            .assign(err=lambda d: d["predicted"] - d["actual"])["err"]
            .to_numpy()
        )
        fc = forecast_forward(series, best, errs)
        fc.insert(0, "chokepoint_id", cid)
        forecasts.append(fc)
        LOG.info(
            "%-18s best=%-8s MAE=%.1f (naive %.1f)  next-12w mean=%.0f events/wk",
            cid,
            best,
            sc.iloc[0]["mae"],
            float(sc.loc[sc["model"] == "naive", "mae"].iloc[0]),
            fc["forecast"].mean(),
        )

    scores_df = pd.concat(scores, ignore_index=True)
    fc_df = pd.concat(forecasts, ignore_index=True)
    save_table(scores_df, "forecast_backtest_scores")
    save_table(fc_df, "forecast_corridor_12w")
    return {"scores": scores_df, "forecasts": fc_df}
