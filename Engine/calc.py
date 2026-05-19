import re
import warnings
from datetime import date
from dateutil.relativedelta import relativedelta
import holidays
import numpy as np
import pandas as pd
from .loader import load_price, DateLike

_NYSE_HOLIDAYS = holidays.NYSE()


def _is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _NYSE_HOLIDAYS


def calc_add_date(base_date: DateLike, offset: str) -> date:
    """
    Add or subtract business days (b), calendar months (m), or years (y) from a date.
    Business days ('b') skip weekends and NYSE holidays; 'd'/'m'/'y' use calendar arithmetic.
    Examples: '1b', '-3b', '1d', '1m', '-1m', '2y', '-10y'.
    """
    m = re.fullmatch(r'(-?\d+)([bBdDmMyY])', offset.strip())
    if not m:
        raise ValueError(f"Invalid offset format: '{offset}'. Expected e.g. '1b', '-1m', '2y'.")
    n, unit = int(m.group(1)), m.group(2).lower()

    if isinstance(base_date, str):
        base_date = pd.Timestamp(base_date).date()
    elif isinstance(base_date, pd.Timestamp):
        base_date = base_date.date()

    if unit == 'b':
        if n == 0:
            return base_date
        step = 1 if n > 0 else -1
        current = base_date
        remaining = abs(n)
        while remaining > 0:
            current += relativedelta(days=step)
            if _is_business_day(current):
                remaining -= 1
        return current
    elif unit == 'd':
        return base_date + relativedelta(days=n)
    elif unit == 'm':
        return base_date + relativedelta(months=n)
    elif unit == 'y':
        return base_date + relativedelta(years=n)
    else:
        raise ValueError(f"Unknown unit '{unit}'.")


def calc_business_date(start: DateLike, end: DateLike) -> list:
    all_days = pd.bdate_range(start, end)
    return [ts for ts in all_days if ts.date() not in _NYSE_HOLIDAYS]


def calc_verify_universe(
    start_date: DateLike,
    end_date: DateLike,
    index: str,
    ticker: str | list[str],
) -> pd.DataFrame:
    from .loader import load_universe
    index = index.upper()
    if isinstance(ticker, str):
        ticker = [ticker]
    ticker = [t.upper() for t in ticker]

    raw = load_universe(index, start_date, end_date).get(index, pd.DataFrame())

    biz_dates = calc_business_date(start_date, end_date)
    biz_index = pd.DatetimeIndex([pd.Timestamp(d) for d in biz_dates])

    result = pd.DataFrame(False, index=biz_index, columns=ticker, dtype=bool)

    if raw.empty:
        return result

    raw = raw.set_index("date")
    for d, row in raw.iterrows():
        if d in result.index:
            members = set(t.upper() for t in row["tickers"].split(","))
            for t in ticker:
                result.at[d, t] = t in members

    return result


def calc_return_std(
    tickers: str | list[str],
    start: DateLike,
    end: DateLike,
    returns: str = '1b',
) -> dict[str, float]:
    from .loader import load_return
    raw = load_return(tickers, start, end, returns=returns)
    result = {}
    for ticker, df in raw.items():
        if df.empty or returns not in df.columns:
            result[ticker] = float('nan')
            continue
        r = df[returns].dropna().values
        result[ticker] = float(np.sqrt(np.mean(r * r) * 252))
    return result


def calc_zscore(values: list | np.ndarray) -> list:
    arr = np.asarray(values, dtype=float)
    return ((arr - np.nanmean(arr)) / np.nanstd(arr)).tolist()


def calc_dict2df(dictionary: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if not isinstance(dictionary, dict):
        raise TypeError("Input must be a dict.")
    for ticker, df in dictionary.items():
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"'{ticker}': value must be a DataFrame, got {type(df)}.")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise TypeError(f"'{ticker}': DataFrame index must be DatetimeIndex, got {type(df.index)}.")
        if df.shape[1] != 1:
            raise ValueError(f"'{ticker}': DataFrame must have exactly 1 column, got {df.shape[1]}.")
    return pd.concat(
        {ticker: df.iloc[:, 0] for ticker, df in dictionary.items()}, axis=1
    )


def calc_forward_close(
    tickers: str | list[str],
    start: DateLike,
    end: DateLike,
) -> dict[str, pd.DataFrame]:
    """
    向后复权价格：以 start 日的 close 为基准对 adjusted_close 缩放，
    使序列在 start 日等于当日真实收盘价，后续涨跌幅含分红/拆股调整。
    返回 dict[ticker, DataFrame(date × ['adjusted_close'])]
    """
    raw = load_price(tickers, start, end, prices=["close", "adjusted_close"])
    result = {}
    for ticker, df in raw.items():
        if df.empty:
            warnings.warn(f"calc_forward_close: {ticker} 无价格数据")
            result[ticker] = pd.DataFrame(columns=["adjusted_close"])
            continue
        p = df["adjusted_close"].iloc[0] / df["close"].iloc[0]
        out = (df["adjusted_close"] / p).rename("adjusted_close").to_frame()
        result[ticker] = out
    return result
