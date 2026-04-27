import datetime as dt
import pandas as pd
from pathlib import Path

_INDEX_ROOT = Path(__file__).parents[2] / "Market" / "daily" / "universe"

DateLike = str | dt.date | dt.datetime | pd.Timestamp


def _to_timestamp(d: DateLike) -> pd.Timestamp:
    return pd.Timestamp(d)


class Universe:
    def __init__(self, index: str, index_root: str | Path = _INDEX_ROOT):
        path = Path(index_root) / f"{index}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"找不到 universe 文件: {path}")
        self._df = pd.read_parquet(path)
        self._df["date"] = pd.to_datetime(self._df["date"])
        self._df = self._df.sort_values("date").reset_index(drop=True)

    def get(self, start: DateLike, end: DateLike = None) -> list[str] | pd.DataFrame:
        """
        end=None  → 返回 start 当天（或之前最近交易日）的成分股 list[str]
        end 有值  → 返回 [start, end] 区间每个交易日的成分股 DataFrame(date, tickers)
        """
        start_dt = _to_timestamp(start)

        if end is None:
            row = self._df[self._df["date"] <= start_dt].iloc[-1]
            return row["tickers"].split(",")

        end_dt = _to_timestamp(end)
        mask = (self._df["date"] >= start_dt) & (self._df["date"] <= end_dt)
        return self._df[mask].reset_index(drop=True)


# ── 每个 universe 只加载一次，缓存复用 ───────────────────────────
_cache: dict[str, Universe] = {}


def _get_one(index: str, start: DateLike, end: DateLike):
    index = index.upper()
    if index not in _cache:
        _cache[index] = Universe(index)
    return _cache[index].get(start, end)


def get_universe(
    index: str | list[str],
    start: DateLike,
    end: DateLike = None,
) -> dict:
    """
    返回 dict[universe, list[str] | DataFrame]
    """
    if isinstance(index, str):
        index = [index]
    return {idx.upper(): _get_one(idx, start, end) for idx in index}
