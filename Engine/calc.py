import warnings
import pandas as pd
from .loader import load_price, DateLike


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
