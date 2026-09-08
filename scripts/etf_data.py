import json
import time
from datetime import datetime

import pandas as pd
import yaml

from data_provider.tencent_provider import (
    get_history,
    get_realtime,
)


# ============================================================
# 基本配置
# ============================================================

WATCHLIST_FILE = "_data/etf_watchlist.yml"
OUTPUT_FILE = "assets/data/etf_data.json"


# ============================================================
# 百分比
# ============================================================

def pct(value):
    if value is None:
        return None

    return round(float(value), 2)


# ============================================================
# 计算涨跌幅
# ============================================================

def calculate_return(df, days):
    """
    days:
        1   = 今日
        5   = 近1周
        22  = 近1月
    """

    if len(df) <= days:
        return None

    latest = df.iloc[-1]["close"]
    previous = df.iloc[-days - 1]["close"]

    if previous == 0:
        return None

    return pct(
        (latest / previous - 1) * 100
    )


# ============================================================
# 计算当前回撤
# ============================================================

def calculate_current_drawdown(df):
    """
    当前价格相对于历史最高点的回撤。
    """

    if df.empty:
        return None

    latest = df.iloc[-1]["close"]

    highest = df["high"].max()

    if highest == 0:
        return None

    return pct(
        (latest / highest - 1) * 100
    )


# ============================================================
# 最大回撤
# ============================================================

def calculate_max_drawdown(df):
    """
    计算整个历史区间最大回撤。
    """

    if df.empty:
        return None

    prices = df["close"]

    running_max = prices.cummax()

    drawdown = (
        prices / running_max - 1
    ) * 100

    return pct(drawdown.min())


# ============================================================
# 平均回撤
# ============================================================

def calculate_average_drawdown(df):
    """
    计算历史平均回撤。

    每一天：

        当前价格 / 截止当天历史最高价格 - 1

    然后求平均。
    """

    if df.empty:
        return None

    prices = df["close"]

    running_max = prices.cummax()

    drawdown = (
        prices / running_max - 1
    ) * 100

    return pct(drawdown.mean())


# ============================================================
# 最近最高点
# ============================================================

def calculate_recent_high(df):
    """
    历史区间内最高价格。
    """

    if df.empty:
        return None

    return round(
        float(df["high"].max()),
        4
    )


# ============================================================
# 最近最低点
# ============================================================

def calculate_recent_low(df):
    """
    历史区间内最低价格。
    """

    if df.empty:
        return None

    return round(
        float(df["low"].min()),
        4
    )


# ============================================================
# 单个 ETF 处理
# ============================================================

def process_etf(code):

    code = str(code).zfill(6)

    print()
    print("=" * 60)
    print(f"正在处理：{code}")

    # --------------------------------------------------------
    # 1. 获取历史数据
    # --------------------------------------------------------

    print("获取历史数据...")

    df = get_history(code)

    if df is None or df.empty:
        raise RuntimeError(
            f"{code} 历史数据为空"
        )

    print(
        f"历史数据：{len(df)} 条"
    )

    print(
        f"历史区间："
        f"{df.iloc[0]['date'].strftime('%Y-%m-%d')}"
        f" ~ "
        f"{df.iloc[-1]['date'].strftime('%Y-%m-%d')}"
    )

    # --------------------------------------------------------
    # 2. 最新历史收盘价
    # --------------------------------------------------------

    latest_close = float(
        df.iloc[-1]["close"]
    )

    # --------------------------------------------------------
    # 3. 获取实时行情
    # --------------------------------------------------------

    realtime = get_realtime(code)

    if realtime:

        name = realtime.get("name", "")

        latest_price = realtime.get(
            "price",
            latest_close
        )

        daily_change = realtime.get(
            "change_pct"
        )

        print(
            f"实时价格：{latest_price}"
        )

        if daily_change is not None:
            print(
                f"今日涨跌：{daily_change:.2f}%"
            )

    else:

        # ----------------------------------------------------
        # 如果实时接口失败
        # 使用历史最后收盘价作为备用
        # ----------------------------------------------------

        name = ""

        latest_price = latest_close

        daily_change = None

        print(
            "实时行情失败，使用历史收盘价"
        )

    # --------------------------------------------------------
    # 4. 计算指标
    # --------------------------------------------------------

    current_drawdown = (
        calculate_current_drawdown(df)
    )

    week_return = (
        calculate_return(df, 5)
    )

    month_return = (
        calculate_return(df, 22)
    )

    max_drawdown = (
        calculate_max_drawdown(df)
    )

    average_drawdown = (
        calculate_average_drawdown(df)
    )

    recent_high = (
        calculate_recent_high(df)
    )

    recent_low = (
        calculate_recent_low(df)
    )

    # --------------------------------------------------------
    # 5. 如果实时名称为空
    # --------------------------------------------------------

    if not name:
        name = code

    # --------------------------------------------------------
    # 6. 生成结果
    # --------------------------------------------------------

    result = {
        "code": code,

        "name": name,

        "price": round(
            float(latest_price),
            4
        ),

        "change_1d": daily_change,

        "change_1w": week_return,

        "change_1m": month_return,

        "current_drawdown": current_drawdown,

        "recent_high": recent_high,

        "recent_low": recent_low,

        "max_drawdown": max_drawdown,

        "average_drawdown": average_drawdown,

        "history_start": (
            df.iloc[0]["date"]
            .strftime("%Y-%m-%d")
        ),

        "history_end": (
            df.iloc[-1]["date"]
            .strftime("%Y-%m-%d")
        ),
    }

    # --------------------------------------------------------
    # 7. 打印计算结果
    # --------------------------------------------------------

    print()
    print("计算结果：")

    print(
        f"名称：{name}"
    )

    print(
        f"价格：{result['price']}"
    )

    print(
        f"今日：{result['change_1d']}"
    )

    print(
        f"1周：{result['change_1w']}"
    )

    print(
        f"1月：{result['change_1m']}"
    )

    print(
        f"当前回撤："
        f"{result['current_drawdown']}"
    )

    print(
        f"最高："
        f"{result['recent_high']}"
    )

    print(
        f"最低："
        f"{result['recent_low']}"
    )

    print(
        f"最大回撤："
        f"{result['max_drawdown']}"
    )

    print(
        f"平均回撤："
        f"{result['average_drawdown']}"
    )

    return result


# ============================================================
# 读取 ETF 列表
# ============================================================

def load_watchlist():

    with open(
        WATCHLIST_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = yaml.safe_load(f)

    if not data:
        return []

    codes = data.get(
        "codes",
        []
    )

    # --------------------------------------------------------
    # 去重，同时保持原顺序
    # --------------------------------------------------------

    unique_codes = []

    for code in codes:

        code = str(code).zfill(6)

        if code not in unique_codes:
            unique_codes.append(code)

    return unique_codes


# ============================================================
# 主程序
# ============================================================

def main():

    print()
    print("=" * 60)
    print("ETF 数据更新程序")
    print("当前数据源：Tencent Finance")
    print("=" * 60)

    # --------------------------------------------------------
    # 读取 ETF 列表
    # --------------------------------------------------------

    codes = load_watchlist()

    print(
        f"读取到 {len(codes)} 个 ETF"
    )

    # --------------------------------------------------------
    # 开始处理
    # --------------------------------------------------------

    results = []

    success = 0
    failed = 0

    for code in codes:

        try:

            result = process_etf(code)

            results.append(result)

            success += 1

        except Exception as e:

            failed += 1

            print()
            print(
                f"❌ {code} 处理失败：{e}"
            )

            # ------------------------------------------------
            # 即使单个 ETF 失败
            # 也继续处理其他 ETF
            # ------------------------------------------------

            results.append({
                "code": code,
                "name": code,

                "price": None,

                "change_1d": None,
                "change_1w": None,
                "change_1m": None,

                "current_drawdown": None,

                "recent_high": None,
                "recent_low": None,

                "max_drawdown": None,
                "average_drawdown": None,

                "history_start": None,
                "history_end": None,

                "error": True,
            })

        # ----------------------------------------------------
        # 避免请求过于密集
        # ----------------------------------------------------

        time.sleep(0.5)

    # ========================================================
    # 输出 JSON
    # ========================================================

    output = {

        "updated_at": (
            datetime.now()
            .strftime("%Y-%m-%d %H:%M:%S")
        ),

        "source": "Tencent Finance",

        "count": len(results),

        "success": success,

        "failed": failed,

        "data": results,
    }

    # --------------------------------------------------------
    # 确保输出目录存在
    # --------------------------------------------------------

    import os

    output_dir = os.path.dirname(
        OUTPUT_FILE
    )

    if output_dir:
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

    # ========================================================
    # 完成
    # ========================================================

    print()
    print("=" * 60)
    print("更新完成")

    print(
        f"成功：{success}/{len(codes)}"
    )

    print(
        f"失败：{failed}/{len(codes)}"
    )

    print(
        f"输出文件：{OUTPUT_FILE}"
    )

    print("=" * 60)


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    main()