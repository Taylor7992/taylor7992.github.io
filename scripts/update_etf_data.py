import json
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yaml


# ============================================================
# 基本配置
# ============================================================

WATCHLIST_FILE = "_data/etf_watchlist.yml"
OUTPUT_FILE = "assets/data/etf_data.json"

# 获取最近 3 年历史数据
HISTORY_DAYS = 3 * 365

# 东方财富 K 线接口
EASTMONEY_KLINE_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get"
)

# 东方财富实时行情接口
EASTMONEY_QUOTE_URL = (
    "https://push2.eastmoney.com/api/qt/stock/get"
)

# LOF 基金
LOF_CODES = {
    "162719",
    "161226",
}


# ============================================================
# HTTP Session
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
})


# ============================================================
# 读取自选 ETF
# ============================================================

def load_watchlist():

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    codes = config.get("codes", [])

    # 去重，同时保持原来的顺序
    result = []

    for code in codes:

        code = str(code).strip()

        if code and code not in result:
            result.append(code)

    return result


# ============================================================
# 判断交易所
# ============================================================

def get_secid(code):

    code = str(code)

    # 上海
    if code.startswith(("51", "52", "56", "58")):
        return f"1.{code}"

    # 深圳
    return f"0.{code}"


# ============================================================
# 获取实时行情
# ============================================================

def get_realtime_quote(code):

    secid = get_secid(code)

    params = {
        "secid": secid,
        "fields": (
            "f57,f58,f43,f169,f170,"
            "f46,f60,f44,f45,f47,f48"
        ),
    }

    response = session.get(
        EASTMONEY_QUOTE_URL,
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("data"):
        return None

    item = data["data"]

    return {
        "code": str(item.get("f57") or code),
        "name": item.get("f58") or code,
        "price": item.get("f43"),
        "change": item.get("f169"),
        "change_percent": item.get("f170"),
    }


# ============================================================
# 获取历史 K 线
# ============================================================

def get_history(code):

    secid = get_secid(code)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=HISTORY_DAYS)

    params = {
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
        "beg": start_date.strftime("%Y%m%d"),
        "end": end_date.strftime("%Y%m%d"),
    }

    response = session.get(
        EASTMONEY_KLINE_URL,
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("data"):
        raise RuntimeError("东方财富没有返回历史数据")

    klines = result["data"].get("klines")

    if not klines:
        raise RuntimeError("历史 K 线为空")

    rows = []

    for line in klines:

        parts = line.split(",")

        if len(parts) < 6:
            continue

        rows.append({
            "date": parts[0],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": float(parts[5]),
        })

    if not rows:
        raise RuntimeError("历史数据解析失败")

    df = pd.DataFrame(rows)

    df["date"] = pd.to_datetime(df["date"])

    df = df.sort_values("date").reset_index(drop=True)

    return df


# ============================================================
# 安全数值转换
# ============================================================

def safe_float(value):

    try:

        if value is None:
            return None

        value = float(value)

        if pd.isna(value):
            return None

        return value

    except Exception:

        return None


# ============================================================
# 计算区间涨跌幅
# ============================================================

def calculate_return(df, days):

    if len(df) < 2:
        return None

    latest_price = float(df.iloc[-1]["close"])

    index = max(0, len(df) - 1 - days)

    old_price = float(df.iloc[index]["close"])

    if old_price == 0:
        return None

    return (latest_price / old_price - 1) * 100


# ============================================================
# 计算最大回撤
# ============================================================

def calculate_max_drawdown(df):

    prices = df["close"].astype(float)

    running_max = prices.cummax()

    drawdown = prices / running_max - 1

    return float(drawdown.min() * 100)


# ============================================================
# 计算当前回撤
# ============================================================

def calculate_current_drawdown(df, current_price):

    if current_price is None:
        return None

    prices = df["close"].astype(float)

    historical_high = float(prices.max())

    if historical_high == 0:
        return None

    return (current_price / historical_high - 1) * 100


# ============================================================
# 计算平均回撤
# ============================================================

def calculate_average_drawdown(df):

    prices = df["close"].astype(float).tolist()

    if len(prices) < 2:
        return None

    running_high = prices[0]

    drawdowns = []

    current_drawdown = 0

    for price in prices[1:]:

        # 创新高
        if price >= running_high:

            # 如果之前存在完整回撤周期
            if current_drawdown < 0:
                drawdowns.append(current_drawdown)

            running_high = price
            current_drawdown = 0

        else:

            drawdown = price / running_high - 1

            if drawdown < current_drawdown:
                current_drawdown = drawdown

    # 最后一个尚未恢复的回撤周期
    if current_drawdown < 0:
        drawdowns.append(current_drawdown)

    if not drawdowns:
        return 0

    return float(sum(drawdowns) / len(drawdowns) * 100)


# ============================================================
# 计算 ETF 数据
# ============================================================

def process_etf(code):

    print(f"正在处理 {code}")

    try:

        # ----------------------------------------------------
        # 历史数据
        # ----------------------------------------------------

        df = get_history(code)

        if df.empty:
            raise RuntimeError("历史数据为空")

        # ----------------------------------------------------
        # 实时数据
        # ----------------------------------------------------

        quote = None

        try:

            quote = get_realtime_quote(code)

        except Exception as e:

            print(f"实时行情获取失败 {code}: {e}")

        # ----------------------------------------------------
        # 基础信息
        # ----------------------------------------------------

        if quote:

            name = quote["name"]

            realtime_price = safe_float(
                quote["price"]
            )

            realtime_change_percent = safe_float(
                quote["change_percent"]
            )

        else:

            name = code
            realtime_price = None
            realtime_change_percent = None

        # ----------------------------------------------------
        # 最新价格
        # ----------------------------------------------------

        if realtime_price is not None and realtime_price > 0:

            latest_price = realtime_price

        else:

            latest_price = safe_float(
                df.iloc[-1]["close"]
            )

        # ----------------------------------------------------
        # 今日涨跌幅
        # ----------------------------------------------------

        if realtime_change_percent is not None:

            return_1d = realtime_change_percent

        else:

            if len(df) >= 2:

                previous_close = float(
                    df.iloc[-2]["close"]
                )

                today_close = float(
                    df.iloc[-1]["close"]
                )

                if previous_close != 0:

                    return_1d = (
                        today_close / previous_close - 1
                    ) * 100

                else:

                    return_1d = None

            else:

                return_1d = None

        # ----------------------------------------------------
        # 近 1 周
        # ----------------------------------------------------

        return_1w = calculate_return(
            df,
            5
        )

        # ----------------------------------------------------
        # 近 1 月
        # ----------------------------------------------------

        return_1m = calculate_return(
            df,
            21
        )

        # ----------------------------------------------------
        # 最近最高点
        # ----------------------------------------------------

        highest = float(
            df["close"].max()
        )

        # ----------------------------------------------------
        # 最近最低点
        # ----------------------------------------------------

        lowest = float(
            df["close"].min()
        )

        # ----------------------------------------------------
        # 最大回撤
        # ----------------------------------------------------

        max_drawdown = calculate_max_drawdown(
            df
        )

        # ----------------------------------------------------
        # 平均回撤
        # ----------------------------------------------------

        avg_drawdown = calculate_average_drawdown(
            df
        )

        # ----------------------------------------------------
        # 当前回撤
        # ----------------------------------------------------

        current_drawdown = calculate_current_drawdown(
            df,
            latest_price
        )

        return {
            "code": code,
            "name": name,
            "price": latest_price,
            "return_1d": return_1d,
            "return_1w": return_1w,
            "return_1m": return_1m,
            "highest": highest,
            "lowest": lowest,
            "max_drawdown": max_drawdown,
            "avg_drawdown": avg_drawdown,
            "current_drawdown": current_drawdown,
            "error": False,
        }

    except Exception as e:

        print(f"处理 {code} 失败：{e}")

        return {
            "code": code,
            "name": code,
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


# ============================================================
# 主程序
# ============================================================

def main():

    print("=" * 60)
    print("ETF 数据更新程序")
    print("=" * 60)

    codes = load_watchlist()

    print(f"读取到 {len(codes)} 个 ETF")

    results = []

    for code in codes:

        result = process_etf(code)

        results.append(result)

        # 避免请求过快
        time.sleep(0.5)

    # --------------------------------------------------------
    # 输出 JSON
    # --------------------------------------------------------

    output = {
        "updated_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "count": len(results),
        "data": results,
    }

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

    success_count = sum(
        1 for item in results
        if not item["error"]
    )

    print("=" * 60)
    print(
        f"更新完成：{success_count}/{len(results)} 成功"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()