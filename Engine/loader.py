import datetime as dt
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

_MARKET_ROOT = Path(__file__).parents[2] / "Market"

_FREQ_DIR = {
    "d":  "daily",
    "1m": "minute/1m",
    "2m": "minute/2m",
    "3m": "minute/3m",
    "5m": "minute/5m",
    "1h": "hour/1h",
}

DateLike = str | dt.date | dt.datetime | pd.Timestamp


def _to_timestamp(d: DateLike) -> pd.Timestamp:
    return pd.Timestamp(d)


def _normalize_tickers(tickers: str | list[str]) -> list[str]:
    if isinstance(tickers, str):
        tickers = [tickers]
    return [t.upper() for t in tickers]


class DataLoader:
    def __init__(self, market_root: str | Path = _MARKET_ROOT):
        self.root = Path(market_root)

    def load_price(
        self,
        tickers: str | list[str],
        start: DateLike,
        end: DateLike,
        prices: list[str] | None = None,
        freq: str = "d",
        group: str = "ticker",
    ) -> dict[str, pd.DataFrame]:
        """
        group='ticker' (default) → dict[ticker, DataFrame(date × prices)]
        group='prices'           → dict[price,  DataFrame(date × ticker)]
        """
        group = group.lower()
        if freq not in _FREQ_DIR:
            raise ValueError(f"不支持的 freq '{freq}'，可选: {list(_FREQ_DIR)}")

        tickers  = _normalize_tickers(tickers)
        start_dt = _to_timestamp(start)
        end_dt   = _to_timestamp(end)
        freq_dir = _FREQ_DIR[freq]

        frames: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            path = self.root / freq_dir / "price" / f"{ticker}.parquet"
            if not path.exists():
                continue
            cols = ["date"] + (prices if prices else
                               ["open", "high", "low", "close", "adjusted_close", "volume"])
            df = pq.read_table(path, columns=cols).to_pandas()
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]
            frames[ticker] = df.set_index("date")

        if not frames:
            return {}

        if group == "prices":
            all_prices = prices if prices else ["open", "high", "low", "close", "adjusted_close", "volume"]
            return {
                p: pd.DataFrame({t: frames[t][p] for t in frames if p in frames[t].columns})
                for p in all_prices
            }

        return {ticker: frames[ticker] for ticker in frames}


    def load_event(
        self,
        tickers: str | list[str],
        start: DateLike,
        end: DateLike,
        event: str,
    ) -> dict[str, pd.DataFrame]:
        """
        event='dividend' | 'split'
        返回 dict[ticker, DataFrame]，date 列已过滤到 [start, end]
        """
        event = event.lower()
        tickers  = _normalize_tickers(tickers)
        start_dt = _to_timestamp(start)
        end_dt   = _to_timestamp(end)

        frames: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            path = self.root / "daily" / "events" / event / f"{ticker}.parquet"
            if not path.exists():
                continue
            df = pd.read_parquet(path)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)].reset_index(drop=True)
            if not df.empty:
                frames[ticker] = df

        return frames

    def load_universe(
        self,
        index: str | list[str],
        start: DateLike,
        end: DateLike = None,
    ) -> dict[str, list[str] | pd.DataFrame]:
        """
        end=None  → 返回 start 当天（或之前最近交易日）的成分股 list[str]
        end 有值  → 返回 [start, end] 区间每个交易日的成分股 DataFrame(date, tickers)
        """
        if isinstance(index, str):
            index = [index]
        result = {}
        for idx in index:
            idx = idx.upper()
            cache_key = (self.root, idx)
            if cache_key not in _universe_cache:
                path = self.root / "daily" / "universe" / f"{idx}.parquet"
                if not path.exists():
                    raise FileNotFoundError(f"找不到 universe 文件: {path}")
                df = pd.read_parquet(path)
                df["date"] = pd.to_datetime(df["date"])
                _universe_cache[cache_key] = df.sort_values("date").reset_index(drop=True)
            df = _universe_cache[cache_key]
            start_dt = _to_timestamp(start)
            if end is None:
                result[idx] = df[df["date"] <= start_dt].iloc[-1]["tickers"].split(",")
            else:
                end_dt = _to_timestamp(end)
                mask = (df["date"] >= start_dt) & (df["date"] <= end_dt)
                result[idx] = df[mask].reset_index(drop=True)
        return result


_universe_cache: dict[tuple, pd.DataFrame] = {}

# ── 模块级默认实例，直接调用无需实例化 ──────────────────────────
_default_loader = DataLoader()


def load_price(
    tickers: str | list[str],
    start: DateLike,
    end: DateLike,
    prices: list[str] | None = None,
    freq: str = "d",
    group: str = "ticker",
) -> dict[str, pd.DataFrame]:
    return _default_loader.load_price(tickers, start, end, prices=prices, freq=freq, group=group)


def load_event(
    tickers: str | list[str],
    start: DateLike,
    end: DateLike,
    event: str,
) -> dict[str, pd.DataFrame]:
    return _default_loader.load_event(tickers, start, end, event=event)


def load_universe(
    index: str | list[str],
    start: DateLike,
    end: DateLike = None,
) -> dict[str, list[str] | pd.DataFrame]:
    return _default_loader.load_universe(index, start, end)
