import json
import os

import pandas as pd
import yaml

from scripts.data_provider.manager import (
    get_history,
    get_realtime,
)


# ============================================================
# 文件位置
# ============================================================

WATCHLIST_FILE = "_data/etf_watchlist.yml"

OUTPUT_FILE = "assets/data/etf_data.json"


# ============================================================
# 读取 ETF 自选列表
# ============================================================

def load_watchlist():

    if not os.path.exists(WATCHLIST_FILE):
        raise FileNotFoundError(
            f"找不到自选列表：{WATCHLIST_FILE}"
        )

    with open(
        WATCHLIST_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = yaml.safe_load(f)

    if not data:
        raise ValueError(
            "ETF 自选列表为空"
        )

    # 兼容不同 YAML 写法
    if isinstance(data, dict):

        if "etfs" in data:
            items = data["etfs"]

        elif "watchlist" in data:
            items = data["watchlist"]

        else:
            items = data.values()

    else:
        items = data

    codes = []

    for item in items:

        if isinstance(item, dict):

            code = (
                item.get("code")
                or item.get("symbol")
            )

        else:
            code = item

        if code is None:
            continue

        code = str(code).strip().zfill(6)

        if code not in codes:
            codes.append(code)

    if not codes:
        raise ValueError(
            "没有读取到任何 ETF 代码"
        )

    return codes


# ============================================================
# 计算区间涨跌幅
# ============================================================

def calculate_return(df, days):
    """
    days：
    5  = 近 1 周
    21 = 近 1 月
    """

    if len(df) <= days:
        return None

    old_price = float(
        df.iloc[-days - 1]["close"]
    )

    latest_price = float(
        df.iloc[-1]["close"]
    )

    if old_price == 0:
        return None

    return (
        (latest_price - old_price)
        / old_price
        * 100
    )


# ============================================================
# 计算当前回撤
# ============================================================

def calculate_current_drawdown(df):

    closes = df["close"].astype(float)

    latest = float(closes.iloc[-1])

    highest = float(closes.max())

    if highest <= 0:
        return None

    return (
        (latest - highest)
        / highest
        * 100
    )


# ============================================================
# 计算最大回撤
# ============================================================

def calculate_max_drawdown(df):

    closes = df["close"].astype(float)

    running_max = closes.cummax()

    drawdown = (
        (closes - running_max)
        / running_max
        * 100
    )

    return float(drawdown.min())


# ============================================================
# 计算平均回撤
# ============================================================

def calculate_average_drawdown(df):

    closes = df["close"].astype(float)

    running_max = closes.cummax()

    drawdown = (
        (closes - running_max)
        / running_max
        * 100
    )

    return float(drawdown.mean())


# ============================================================
# 处理单个 ETF
# ============================================================

def process_etf(code):

    print(f"\n正在处理：{code}")

    # --------------------------------------------------------
    # 获取历史数据
    # --------------------------------------------------------

    df = get_history(code)

    if df is None or df.empty:
        raise RuntimeError(
            f"{code} 没有获取到历史数据"
        )

    # --------------------------------------------------------
    # 确保按照日期排序
    # --------------------------------------------------------

    df = df.sort_values("date")

    df = df.reset_index(drop=True)

    # --------------------------------------------------------
    # 最新历史收盘价
    # --------------------------------------------------------

    latest_close = float(
        df.iloc[-1]["close"]
    )

    # --------------------------------------------------------
    # 计算历史成交额
    #
    # amount 是每天估算出来的成交额
    # --------------------------------------------------------

    if "amount" not in df.columns:
        df["amount"] = 0.0

    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce"
    ).fillna(0)

    # --------------------------------------------------------
    # 今日成交额
    # --------------------------------------------------------

    amount_1d = float(
        df.iloc[-1]["amount"]
    )

    # --------------------------------------------------------
    # 最近 5 个交易日成交额
    # --------------------------------------------------------

    amount_1w = float(
        df.tail(5)["amount"].sum()
    )

    # --------------------------------------------------------
    # 最近 21 个交易日成交额
    # --------------------------------------------------------

    amount_1m = float(
        df.tail(21)["amount"].sum()
    )

    # --------------------------------------------------------
    # 获取实时行情
    # --------------------------------------------------------

    realtime = get_realtime(code)

    name = code

    price = latest_close

    change_1d = None

    realtime_amount = None

    if realtime:

        name = realtime.get(
            "name",
            code
        )

        price = float(
            realtime.get(
                "price",
                latest_close
            )
        )

        change_1d = realtime.get(
            "change_pct"
        )

        realtime_amount = realtime.get(
            "amount"
        )

    # --------------------------------------------------------
    # 如果腾讯实时接口成功获取到了当天成交额
    #
    # 使用实时成交额替换历史估算值
    #
    # 同时修正 1 周 / 1 月成交额
    # --------------------------------------------------------

    if (
        realtime_amount is not None
        and realtime_amount >= 0
    ):

        realtime_amount = float(
            realtime_amount
        )

        old_latest_amount = amount_1d

        # 今日
        amount_1d = realtime_amount

        # 最近 5 日
        amount_1w = (
            amount_1w
            - old_latest_amount
            + realtime_amount
        )

        # 最近 21 日
        amount_1m = (
            amount_1m
            - old_latest_amount
            + realtime_amount
        )

    # --------------------------------------------------------
    # 如果实时涨跌幅获取失败
    # 使用历史数据计算今日涨跌幅
    # --------------------------------------------------------

    if change_1d is None:

        if len(df) >= 2:

            yesterday = float(
                df.iloc[-2]["close"]
            )

            today = latest_close

            if yesterday != 0:

                change_1d = (
                    (today - yesterday)
                    / yesterday
                    * 100
                )

    # --------------------------------------------------------
    # 计算其他指标
    # --------------------------------------------------------

    change_1w = calculate_return(
        df,
        5
    )

    change_1m = calculate_return(
        df,
        21
    )

    current_drawdown = (
        calculate_current_drawdown(df)
    )

    max_drawdown = (
        calculate_max_drawdown(df)
    )

    average_drawdown = (
        calculate_average_drawdown(df)
    )

    recent_high = float(
        df["high"].tail(252).max()
    )

    recent_low = float(
        df["low"].tail(252).min()
    )

    # --------------------------------------------------------
    # 返回结果
    # --------------------------------------------------------

    result = {

        "code": code,

        "name": name,

        "price": price,

        # 涨跌幅
        "change_1d": change_1d,
        "change_1w": change_1w,
        "change_1m": change_1m,

        # 三个周期的成交额
        "amount_1d": amount_1d,
        "amount_1w": amount_1w,
        "amount_1m": amount_1m,

        # 回撤
        "recent_high": recent_high,
        "recent_low": recent_low,

        "max_drawdown": max_drawdown,

        "average_drawdown": average_drawdown,

        "current_drawdown": current_drawdown,

        # 数据时间范围
        "history_start": (
            df.iloc[0]["date"].strftime("%Y-%m-%d")
        ),

        "history_end": (
            df.iloc[-1]["date"].strftime("%Y-%m-%d")
        ),
    }

    print(
        f"  {code} {name}"
        f"  今日成交额：{amount_1d:,.0f}"
        f"  1周：{amount_1w:,.0f}"
        f"  1月：{amount_1m:,.0f}"
    )

    return result


# ============================================================
# 主程序
# ============================================================

def main():

    print("=" * 60)

    print("开始更新 ETF 数据")

    print("=" * 60)

    watchlist = load_watchlist()

    print(
        f"共读取 {len(watchlist)} 个 ETF"
    )

    results = []

    success = 0

    failed = 0

    # --------------------------------------------------------
    # 逐个获取 ETF
    # --------------------------------------------------------

    for code in watchlist:

        try:

            result = process_etf(code)

            results.append(result)

            success += 1

        except Exception as e:

            failed += 1

            print(
                f"  {code} 获取失败：{e}"
            )

    # --------------------------------------------------------
    # 生成最终 JSON
    # --------------------------------------------------------

    output = {

        "updated_at": pd.Timestamp.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "source": "Tencent Finance",

        "count": len(watchlist),

        "success": success,

        "failed": failed,

        "data": results,
    }

    # --------------------------------------------------------
    # 创建目录
    # --------------------------------------------------------

    output_dir = os.path.dirname(
        OUTPUT_FILE
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    # --------------------------------------------------------
    # 写入 JSON
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()

    print("=" * 60)

    print("ETF 数据更新完成")

    print(
        f"成功：{success}"
    )

    print(
        f"失败：{failed}"
    )

    print(
        f"输出文件：{OUTPUT_FILE}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()