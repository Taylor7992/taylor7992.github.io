from typing import Optional
import pandas as pd


# ETF历史数据统一格式
HISTORY_COLUMNS = [
    "date",
    "open",
    "close",
    "high",
    "low",
]


def standardize_history(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    将不同数据源的历史行情统一成：

    date
    open
    close
    high
    low
    """

    if df is None or df.empty:
        return None

    df = df.copy()

    # 检查必要字段
    for column in HISTORY_COLUMNS:
        if column not in df.columns:
            return None

    # 日期转换
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # 数值转换
    for column in ["open", "close", "high", "low"]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # 删除无效数据
    df = df.dropna(
        subset=["date", "open", "close", "high", "low"]
    )

    # 按日期排序
    df = df.sort_values("date")

    # 去除重复日期
    df = df.drop_duplicates(
        subset=["date"],
        keep="last"
    )

    # 只保留统一字段
    df = df[HISTORY_COLUMNS]

    # 重置索引
    df = df.reset_index(drop=True)

    return df