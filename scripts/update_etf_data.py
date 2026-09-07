# -*- coding: utf-8 -*-

"""
ETF Dashboard 数据更新程序

功能：
1. 自动获取 ETF / LOF 名称
2. 自动获取最新价格
3. 计算今日、近1周、近1月涨跌幅
4. 计算最近最高点、最近最低点
5. 计算历史最大回撤
6. 计算历史平均回撤
7. 计算当前回撤
8. 输出 JSON 给网页使用

数据来源：
AKShare -> 东方财富公开行情数据
"""

import json
import os
import time
from datetime import datetime

import akshare as ak
import pandas as pd
import yaml


# ============================================================
# 配置
# ============================================================

WATCHLIST_FILE = "_data/etf_watchlist.yml"
OUTPUT_FILE = "assets/data/etf_data.json"

# 用最近 3 年的数据作为分析区间
HISTORY_START = (
    datetime.now().replace(
        year=datetime.now().year - 3
    ).strftime("%Y%m%d")
)

# 目前列表中明确属于 LOF 的基金
LOF_CODES = {
    "162719",
    "161226",
}


# ============================================================
# 读取 ETF 列表
# ============================================================

def load_watchlist():

    if not os.path.exists(WATCHLIST_FILE):
        raise FileNotFoundError(
            f"找不到 {WATCHLIST_FILE}"
        )

    with open(
        WATCHLIST_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = yaml.safe_load(f)

    if isinstance(data, dict):
        codes = data.get("codes", [])
    elif isinstance(data, list):
        codes = data
    else:
        codes = []

    codes = [
        str(code).strip()
        for code in codes
        if str(code).strip()
    ]

    # 去重，同时保持原顺序
    codes = list(dict.fromkeys(codes))

    if not codes:
        raise ValueError(
            "ETF 自选列表为空"
        )

    return codes


# ============================================================
# 判断类型
# ============================================================

def is_lof(code):

    return code in LOF_CODES


# ============================================================
# 获取实时行情
# ============================================================

def get_realtime_data():

    result = {}

    # -----------------------------
    # ETF
    # -----------------------------

    try:

        print("正在获取 ETF 实时行情...")

        df = ak.fund_etf_spot_em()

        if df is not None and not df.empty:

            for _, row in df.iterrows():

                code = str(
                    row.get("代码", "")
                ).strip()

                if not code:
                    continue

                name = str(
                    row.get("名称", "")
                ).strip()

                try:
                    price = float(
                        row.get("最新价")
                    )
                except Exception:
                    price = None

                try:
                    change_pct = float(
                        row.get("涨跌幅")
                    )
                except Exception:
                    change_pct = None

                result[code] = {
                    "name": name,
                    "price": price,
                    "change_pct": change_pct,
                }

    except Exception as e:

        print(
            f"ETF 实时行情获取失败：{e}"
        )


    # -----------------------------
    # LOF
    # -----------------------------

    try:

        print("正在获取 LOF 实时行情...")

        df = ak.fund_lof_spot_em()

        if df is not None and not df.empty:

            for _, row in df.iterrows():

                code = str(
                    row.get("代码", "")
                ).strip()

                if not code:
                    continue

                name = str(
                    row.get("名称", "")
                ).strip()

                try:
                    price = float(
                        row.get("最新价")
                    )
                except Exception:
                    price = None

                try:
                    change_pct = float(
                        row.get("涨跌幅")
                    )
                except Exception:
                    change_pct = None

                result[code] = {
                    "name": name,
                    "price": price,
                    "change_pct": change_pct,
                }

    except Exception as e:

        print(
            f"LOF 实时行情获取失败：{e}"
        )

    return result


# ============================================================
# 获取历史行情
# ============================================================

def get_history(code):

    today = datetime.now().strftime(
        "%Y%m%d"
    )

    print(
        f"正在获取 {code} 历史数据..."
    )

    try:

        # -----------------------------
        # LOF
        # -----------------------------

        if is_lof(code):

            df = ak.fund_lof_hist_em(
                symbol=code,
                period="daily",
                start_date=HISTORY_START,
                end_date=today,
                adjust=""
            )

        # -----------------------------
        # ETF
        # -----------------------------

        else:

            df = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=HISTORY_START,
                end_date=today,
                adjust=""
            )

    except Exception as e:

        print(
            f"{code} 历史数据获取失败：{e}"
        )

        return None


    if df is None or df.empty:

        print(
            f"{code} 没有历史数据"
        )

        return None


    # ========================================================
    # 标准化字段
    # ========================================================

    date_column = None
    close_column = None

    for column in [
        "日期",
        "date",
        "Date"
    ]:

        if column in df.columns:
            date_column = column
            break

    for column in [
        "收盘",
        "收盘价",
        "close",
        "Close"
    ]:

        if column in df.columns:
            close_column = column
            break

    if date_column is None:
        print(
            f"{code} 找不到日期字段"
        )
        return None

    if close_column is None:
        print(
            f"{code} 找不到收盘价字段"
        )
        return None


    result = pd.DataFrame({

        "date": pd.to_datetime(
            df[date_column],
            errors="coerce"
        ),

        "close": pd.to_numeric(
            df[close_column],
            errors="coerce"
        ),

    })


    result = result.dropna()

    result = result.sort_values(
        "date"
    )

    result = result.drop_duplicates(
        "date"
    )

    return result


# ============================================================
# 计算涨跌幅
# ============================================================

def calculate_return(
    df,
    days
):

    if len(df) <= days:

        return None

    current = float(
        df["close"].iloc[-1]
    )

    previous = float(
        df["close"].iloc[-1 - days]
    )

    if previous == 0:

        return None

    return round(
        (current / previous - 1) * 100,
        2
    )


# ============================================================
# 计算最大回撤
# ============================================================

def calculate_max_drawdown(df):

    prices = df["close"].astype(float)

    # 历史以来不断更新的最高价
    running_max = prices.cummax()

    # 当前价格相对于历史最高价的跌幅
    drawdown = (
        prices / running_max - 1
    )

    max_drawdown = drawdown.min()

    return round(
        float(max_drawdown) * 100,
        2
    )


# ============================================================
# 计算平均回撤
# ============================================================

def calculate_average_drawdown(df):

    prices = df["close"].astype(float)

    running_max = prices.cummax()

    drawdown = (
        prices / running_max - 1
    )


    # --------------------------------------------------------
    # 识别完整回撤周期
    #
    # 从创新高开始：
    #
    # 高点
    #   ↓
    # 下跌
    #   ↓
    # 最低点
    #   ↓
    # 恢复创新高
    #
    # 算作一次完整回撤
    # --------------------------------------------------------

    drawdowns = []

    current_min = 0.0
    in_drawdown = False

    for value in drawdown:

        value = float(value)

        # 开始进入回撤
        if value < 0:

            in_drawdown = True

            if value < current_min:
                current_min = value

        # 回到新高
        else:

            if in_drawdown:

                drawdowns.append(
                    current_min
                )

                current_min = 0.0

                in_drawdown = False


    # 如果数据最后仍然处于回撤状态
    if in_drawdown:

        drawdowns.append(
            current_min
        )


    if not drawdowns:

        return 0.0


    average = sum(drawdowns) / len(
        drawdowns
    )

    return round(
        average * 100,
        2
    )


# ============================================================
# 计算单个 ETF
# ============================================================

def process_one(
    code,
    realtime
):

    df = get_history(code)

    if df is None or df.empty:

        return {
            "code": code,
            "name": realtime.get(
                code,
                {}
            ).get(
                "name",
                code
            ),
            "price": None,
            "return_1d": None,
            "return_1w": None,
            "return_1m": None,
            "highest": None,
            "lowest": None,
            "max_drawdown": None,
            "avg_drawdown": None,
            "current_drawdown": None,
            "error": True,
        }


    # ========================================================
    # 当前价格
    # ========================================================

    latest_history_price = float(
        df["close"].iloc[-1]
    )

    realtime_item = realtime.get(
        code,
        {}
    )

    realtime_price = realtime_item.get(
        "price"
    )

    if (
        realtime_price is not None
        and realtime_price > 0
    ):

        current_price = realtime_price

    else:

        current_price = latest_history_price


    # ========================================================
    # 名称
    # ========================================================

    name = realtime_item.get(
        "name"
    ) or code


    # ========================================================
    # 涨跌幅
    # ========================================================

    # 今日涨跌幅优先使用实时数据
    today_change = realtime_item.get(
        "change_pct"
    )

    if today_change is None:

        today_change = calculate_return(
            df,
            1
        )

    else:

        today_change = round(
            float(today_change),
            2
        )


    # 近1周
    week_return = calculate_return(
        df,
        5
    )


    # 近1月
    month_return = calculate_return(
        df,
        21
    )


    # ========================================================
    # 最近最高 / 最低点
    #
    # 使用最近3年历史数据
    # ========================================================

    highest = float(
        df["close"].max()
    )

    lowest = float(
        df["close"].min()
    )


    # ========================================================
    # 当前回撤
    #
    # 当前价格相对于“最近一次历史高点”
    # ========================================================

    running_max = (
        df["close"]
        .astype(float)
        .cummax()
    )

    latest_high = float(
        running_max.iloc[-1]
    )

    if latest_high > 0:

        current_drawdown = (
            current_price / latest_high - 1
        ) * 100

    else:

        current_drawdown = 0.0


    # ========================================================
    # 最大回撤
    # ========================================================

    max_drawdown = calculate_max_drawdown(
        df
    )


    # ========================================================
    # 平均回撤
    # ========================================================

    avg_drawdown = calculate_average_drawdown(
        df
    )


    # ========================================================
    # 返回结果
    # ========================================================

    return {

        "code": code,

        "name": name,

        "price": round(
            current_price,
            4
        ),

        "return_1d": today_change,

        "return_1w": week_return,

        "return_1m": month_return,

        "current_drawdown": round(
            current_drawdown,
            2
        ),

        "highest": round(
            highest,
            4
        ),

        "lowest": round(
            lowest,
            4
        ),

        "max_drawdown": max_drawdown,

        "avg_drawdown": avg_drawdown,

        "error": False,

    }


# ============================================================
# 主程序
# ============================================================

def main():

    print("=" * 60)

    print(
        "ETF Dashboard 数据更新开始"
    )

    print("=" * 60)


    # ========================================================
    # 读取 ETF 列表
    # ========================================================

    codes = load_watchlist()

    print(
        f"共发现 {len(codes)} 个代码"
    )

    print(
        ", ".join(codes)
    )

    print()


    # ========================================================
    # 获取实时行情
    # ========================================================

    realtime = get_realtime_data()

    print()


    # ========================================================
    # 逐个处理
    # ========================================================

    results = []

    for index, code in enumerate(
        codes,
        start=1
    ):

        print(
            f"[{index}/{len(codes)}] {code}"
        )

        try:

            data = process_one(
                code,
                realtime
            )

            results.append(data)

        except Exception as e:

            print(
                f"{code} 处理失败：{e}"
            )

            results.append({

                "code": code,

                "name": code,

                "price": None,

                "return_1d": None,

                "return_1w": None,

                "return_1m": None,

                "current_drawdown": None,

                "highest": None,

                "lowest": None,

                "max_drawdown": None,

                "avg_drawdown": None,

                "error": True,

            })


        # 避免连续请求过快
        time.sleep(1)


    # ========================================================
    # 生成 JSON
    # ========================================================

    output = {

        "updated_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "count": len(results),

        "data": results,

    }


    output_dir = os.path.dirname(
        OUTPUT_FILE
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )


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


    success = sum(
        1
        for item in results
        if not item.get(
            "error",
            False
        )
    )


    print()

    print("=" * 60)

    print(
        "ETF Dashboard 数据更新完成"
    )

    print(
        f"成功：{success}/{len(results)}"
    )

    print(
        f"文件：{OUTPUT_FILE}"
    )

    print("=" * 60)


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":

    main()