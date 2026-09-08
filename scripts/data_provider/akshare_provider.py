"""
AkShare ETF 数据源

职责：
1. 获取 ETF 历史行情
2. 将 AkShare 数据转换成项目统一格式
3. 失败时由 manager.py 自动切换到其他数据源
"""

from datetime import datetime, timedelta

import akshare as ak

from .base import standardize_history


# ============================================================
# 历史数据
# ============================================================

def get_history(code, count=1095):
    """
    获取 ETF 历史行情

    参数：
        code  : ETF代码，例如 512660
        count : 需要的交易日数量

    返回：
        DataFrame
        columns:
            date
            open
            close
            high
            low
    """

    code = str(code).strip()
    count = int(count)

    # --------------------------------------------------------
    # AkShare 需要日期范围
    # 1095 个交易日约等于 4~5 个自然年
    # 多取一些，最后再截取 count 条
    # --------------------------------------------------------

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (
        datetime.now() - timedelta(days=1600)
    ).strftime("%Y%m%d")

    print(
        f"    AkShare历史数据："
        f"{start_date} → {end_date}"
    )

    try:
        df = ak.fund_etf_hist_em(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
    except Exception as e:
        raise RuntimeError(
            f"AkShare历史数据请求失败：{e}"
        )

    if df is None or df.empty:
        raise RuntimeError(
            f"AkShare未返回历史数据：{code}"
        )

    # --------------------------------------------------------
    # AkShare 原始字段：
    #
    # 日期
    # 开盘
    # 收盘
    # 最高
    # 最低
    #
    # 转换成项目统一字段
    # --------------------------------------------------------

    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
    }

    df = df.rename(columns=rename_map)

    required_columns = [
        "date",
        "open",
        "close",
        "high",
        "low",
    ]

    for column in required_columns:
        if column not in df.columns:
            raise RuntimeError(
                f"AkShare返回数据缺少字段：{column}"
            )

    df = df[required_columns]

    # --------------------------------------------------------
    # 使用项目统一的数据标准化函数
    # --------------------------------------------------------

    df = standardize_history(df)

    if df is None or df.empty:
        raise RuntimeError(
            f"AkShare历史数据标准化失败：{code}"
        )

    # --------------------------------------------------------
    # 只保留最近 count 个交易日
    # --------------------------------------------------------

    if len(df) > count:
        df = df.tail(count).reset_index(drop=True)

    print(
        f"    ✓ AkShare获取成功："
        f"{len(df)} 条历史数据"
    )

    return df


# ============================================================
# 实时数据
# ============================================================

def get_realtime(code):
    """
    获取 ETF 实时行情。

    当前阶段暂时不使用 AkShare 实时接口，
    保留该函数是为了以后可以直接扩展。

    返回：
        {
            "price": float,
            "change": float
        }

    如果暂未实现，则返回 None，
    manager.py 会自动尝试其他实时数据源。
    """

    return None