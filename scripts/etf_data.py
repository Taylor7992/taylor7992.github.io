import json
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import yaml

from scripts.data_provider.manager import (
    get_history,
    get_realtime,
)


# ============================================================
# 配置
# ============================================================

WATCHLIST_FILE = "_data/etf_watchlist.yml"
OUTPUT_FILE = "assets/data/etf_data.json"


# ============================================================
# 北京时间
# ============================================================

BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_time():
    """
    获取当前北京时间（UTC+8）
    """
    return datetime.now(BEIJING_TZ)


# ============================================================
# 基础计算
# ============================================================

def pct(value):
    if value is None:
        return None

    return round(float(value), 2)


def calculate_return(df, days):
    """
    计算指定交易日周期的收益率

    days=5  -> 约1周
    days=22 -> 约1月
    """

    if len(df) <= days:
        return None

    latest = df.iloc[-1]["close"]
    previous = df.iloc[-days - 1]["close"]

    if previous == 0:
        return None

    return pct((latest / previous - 1) * 100)


def calculate_current_drawdown(df):
    """
    当前回撤：

    当前收盘价 / 历史最高价 - 1
    """

    if df.empty:
        return None

    latest = df.iloc[-1]["close"]
    highest = df["high"].max()

    if highest == 0:
        return None

    return pct((latest / highest - 1) * 100)


def calculate_max_drawdown(df):
    """
    历史最大回撤
    """

    if df.empty:
        return None

    prices = df["close"]

    running_max = prices.cummax()

    drawdown = (prices / running_max - 1) * 100

    return pct(drawdown.min())


def calculate_average_drawdown(df):
    """
    历史平均回撤
    """

    if df.empty:
        return None

    prices = df["close"]

    running_max = prices.cummax()

    drawdown = (prices / running_max - 1) * 100

    return pct(drawdown.mean())


def calculate_recent_high(df):
    """
    历史最高价
    """

    if df.empty:
        return None

    return round(float(df["high"].max()), 4)


def calculate_recent_low(df):
    """
    历史最低价
    """

    if df.empty:
        return None

    return round(float(df["low"].min()), 4)


# ============================================================
# ETF 处理
# ============================================================

def process_etf(code):

    code = str(code).zfill(6)

    print()
    print("=" * 60)
    print(f"正在处理：{code}")

    # --------------------------------------------------------
    # 历史数据
    # --------------------------------------------------------

    print("获取历史数据...")

    df = get_history(code)

    if df is None or df.empty:
        raise RuntimeError(f"{code} 历史数据为空")

    print(f"历史数据：{len(df)} 条")

    print(
        f"历史区间："
        f"{df.iloc[0]['date'].strftime('%Y-%m-%d')}"
        f" ~ "
        f"{df.iloc[-1]['date'].strftime('%Y-%m-%d')}"
    )

    latest_close = float(df.iloc[-1]["close"])

    # --------------------------------------------------------
    # 最新成交额
    # --------------------------------------------------------

    latest_amount = None

    # 如果历史数据中有 amount，就取最新交易日成交额
    if "amount" in df.columns:

        value = df.iloc[-1]["amount"]

        if pd.notna(value):

            try:
                latest_amount = float(value)
            except (ValueError, TypeError):
                latest_amount = None

    if latest_amount is not None:
        print(f"最新成交额：{latest_amount:,.2f}")
    else:
        print("最新成交额：暂无数据")

    # --------------------------------------------------------
    # 实时数据
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

        print(f"实时价格：{latest_price}")

        if daily_change is not None:
            print(f"今日涨跌：{daily_change:.2f}%")

    else:

        name = ""

        latest_price = latest_close

        daily_change = None

        print("实时行情失败，使用历史收盘价")

    # --------------------------------------------------------
    # 指标计算
    # --------------------------------------------------------

    current_drawdown = calculate_current_drawdown(
        df
    )

    week_return = calculate_return(
        df,
        5
    )

    month_return = calculate_return(
        df,
        22
    )

    max_drawdown = calculate_max_drawdown(
        df
    )

    average_drawdown = calculate_average_drawdown(
        df
    )

    recent_high = calculate_recent_high(
        df
    )

    recent_low = calculate_recent_low(
        df
    )

    # --------------------------------------------------------
    # 名称兜底
    # --------------------------------------------------------

    if not name:
        name = code

    # --------------------------------------------------------
    # 最终结果
    # --------------------------------------------------------

    result = {

        "code": code,

        "name": name,

        "price": round(
            float(latest_price),
            4
        ),

        "amount": latest_amount,

        "change_1d": daily_change,

        "change_1w": week_return,

        "change_1m": month_return,

        "current_drawdown": current_drawdown,

        "recent_high": recent_high,

        "recent_low": recent_low,

        "max_drawdown": max_drawdown,

        "average_drawdown": average_drawdown,

        "history_start":
            df.iloc[0]["date"].strftime(
                "%Y-%m-%d"
            ),

        "history_end":
            df.iloc[-1]["date"].strftime(
                "%Y-%m-%d"
            ),
    }

    # --------------------------------------------------------
    # 控制台输出
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
        f"成交额：{result['amount']}"
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
        f"当前回撤：{result['current_drawdown']}"
    )

    print(
        f"最高：{result['recent_high']}"
    )

    print(
        f"最低：{result['recent_low']}"
    )

    print(
        f"最大回撤：{result['max_drawdown']}"
    )

    print(
        f"平均回撤：{result['average_drawdown']}"
    )

    return result


# ============================================================
# 自选 ETF
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

    unique_codes = []

    for code in codes:

        code = str(code).zfill(6)

        if code not in unique_codes:

            unique_codes.append(
                code
            )

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
    # 读取自选列表
    # --------------------------------------------------------

    codes = load_watchlist()

    print(
        f"读取到 {len(codes)} 个 ETF"
    )

    results = []

    success = 0

    failed = 0

    # --------------------------------------------------------
    # 逐个处理 ETF
    # --------------------------------------------------------

    for code in codes:

        try:

            result = process_etf(
                code
            )

            results.append(
                result
            )

            success += 1

        except Exception as e:

            failed += 1

            print()

            print(
                f"❌ {code} 处理失败：{e}"
            )

            results.append({

                "code": code,

                "name": code,

                "price": None,

                "amount": None,

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

        time.sleep(
            0.5
        )

    # --------------------------------------------------------
    # 获取北京时间
    # --------------------------------------------------------

    updated_at = get_beijing_time()

    updated_at_text = updated_at.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # --------------------------------------------------------
    # 输出 JSON
    # --------------------------------------------------------

    output = {

        "updated_at":
            updated_at_text,

        "source":
            "Tencent Finance",

        "count":
            len(results),

        "success":
            success,

        "failed":
            failed,

        "data":
            results,
    }

    # --------------------------------------------------------
    # 创建输出目录
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

    # --------------------------------------------------------
    # 完成
    # --------------------------------------------------------

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
        f"更新时间（北京时间）：{updated_at_text}"
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

