import json
import random
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yaml


# ============================================================
# 基本配置
# ============================================================

WATCHLIST_FILE = "data/etf_watchlist.yml"
OUTPUT_FILE = "assets/data/etf_data.json"

TENCENT_URL = (
    "https://proxy.finance.qq.com/"
    "ifzqgtimg/appstock/app/newfqkline/get"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 "
                  "(Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
}

# 获取约 3 年日线
KLINE_COUNT = 1095


# ============================================================
# ETF代码转换
# ============================================================

def market_code(code):
    """
    根据ETF代码判断上海/深圳市场。

    上海：
        5xxxxx

    深圳：
        15xxxx
        16xxxx
    """

    code = str(code).zfill(6)

    if code.startswith("5"):
        return "sh" + code

    if code.startswith("15") or code.startswith("16"):
        return "sz" + code

    raise ValueError(f"无法判断市场：{code}")


# ============================================================
# 获取腾讯历史K线
# ============================================================

def get_history(code):
    """
    获取ETF历史日线数据。

    腾讯返回格式：

    [
        日期,
        开盘,
        收盘,
        最高,
        最低,
        成交量,
        ...,
        成交额,
        ...
    ]
    """

    symbol = market_code(code)

    params = {
        "_var": "kline_dayqfq",
        "param": f"{symbol},day,,,{KLINE_COUNT},qfq",
        "r": str(random.random()),
    }

    last_error = None

    for attempt in range(3):

        try:

            response = requests.get(
                TENCENT_URL,
                params=params,
                headers=HEADERS,
                timeout=20,
            )

            response.raise_for_status()

            text = response.text.strip()

            if not text:
                raise RuntimeError("腾讯返回内容为空")

            # 腾讯接口通常：
            # kline_dayqfq={...}
            if "=" in text and not text.startswith("{"):
                text = text.split("=", 1)[1]

            text = text.strip().rstrip(";")

            data = json.loads(text)

            if data.get("code") != 0:
                raise RuntimeError(
                    f"腾讯接口返回错误：{data}"
                )

            item = (
                data
                .get("data", {})
                .get(symbol)
            )

            if not item:
                raise RuntimeError(
                    f"没有找到ETF数据：{symbol}"
                )

            bars = item.get("qfqday") or item.get("day")

            if not bars:
                raise RuntimeError(
                    f"没有找到K线：{symbol}"
                )

            rows = []

            for bar in bars:

                if len(bar) < 5:
                    continue

                try:

                    rows.append({
                        "date": bar[0],
                        "open": float(bar[1]),
                        "close": float(bar[2]),
                        "high": float(bar[3]),
                        "low": float(bar[4]),
                    })

                except (ValueError, TypeError):
                    continue

            if not rows:
                raise RuntimeError(
                    f"K线解析后没有有效数据：{symbol}"
                )

            df = pd.DataFrame(rows)

            df["date"] = pd.to_datetime(df["date"])

            df = df.sort_values("date")
            df = df.drop_duplicates("date")

            df = df.reset_index(drop=True)

            return df

        except Exception as e:

            last_error = e

            print(
                f"  第 {attempt + 1}/3 次获取失败：{e}"
            )

            if attempt < 2:
                time.sleep(2)

    raise RuntimeError(
        f"获取历史数据失败：{last_error}"
    )


# ============================================================
# 获取腾讯实时行情
# ============================================================

def get_realtime(code):
    """
    获取腾讯实时行情。

    使用 qt.gtimg.cn。
    """

    symbol = market_code(code)

    url = f"https://qt.gtimg.cn/q={symbol}"

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15,
        )

        response.raise_for_status()

        text = response.text.strip()

        if "=" not in text:
            raise RuntimeError(
                "实时行情返回格式异常"
            )

        value = text.split("=", 1)[1].strip().strip('"')

        fields = value.split("~")

        # 腾讯字段：
        # 0 代码
        # 1 名称
        # 2 代码
        # 3 当前价格
        # 4 昨收
        # 5 今开
        # ...

        if len(fields) < 6:
            raise RuntimeError(
                "实时行情字段不足"
            )

        name = fields[1]

        price = float(fields[3])

        prev_close = float(fields[4])

        open_price = float(fields[5])

        if prev_close > 0:
            change_pct = (
                (price - prev_close)
                / prev_close
                * 100
            )
        else:
            change_pct = 0

        return {
            "name": name,
            "price": price,
            "prev_close": prev_close,
            "open": open_price,
            "change_pct": change_pct,
        }

    except Exception as e:

        print(
            f"  实时行情获取失败：{code}：{e}"
        )

        return None


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

    例如：

    历史最高 2.00
    当前价格 1.80

    回撤：

    (1.80 / 2.00 - 1) × 100
    = -10%
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
    3年历史区间内最高价格。
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
    3年历史区间内最低价格。
    """

    if df.empty:
        return None

    return round(
        float(df["low"].min()),
        4
    )


# ============================================================
# 单个ETF处理
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
    # 最新历史收盘价
    # --------------------------------------------------------

    latest_close = float(
        df.iloc[-1]["close"]
    )

    # --------------------------------------------------------
    # 实时行情
    # --------------------------------------------------------

    realtime = get_realtime(code)

    if realtime:

        name = realtime["name"]

        latest_price = realtime["price"]

        daily_change = realtime["change_pct"]

        print(
            f"实时价格：{latest_price}"
        )

        print(
            f"今日涨跌：{daily_change:.2f}%"
        )

    else:

        # 如果实时接口失败
        # 使用历史最后收盘价作为备用

        name = ""

        latest_price = latest_close

        daily_change = None

        print(
            "实时行情失败，使用历史收盘价"
        )

    # --------------------------------------------------------
    # 计算指标
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
    # 如果腾讯实时名称为空
    # 尝试使用代码名称
    # --------------------------------------------------------

    if not name:
        name = code

    # --------------------------------------------------------
    # 输出
    # --------------------------------------------------------

    result = {
        "code": code,
        "name": name,

        "price": round(
            latest_price,
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
# 读取ETF列表
# ============================================================

def load_watchlist():

    with open(
        WATCHLIST_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = yaml.safe_load(f)

    codes = data.get("codes", [])

    # 去重，同时保持原顺序

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
    print("数据源：腾讯财经")
    print("=" * 60)

    codes = load_watchlist()

    print(
        f"读取到 {len(codes)} 个 ETF"
    )

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

            # 即使单个ETF失败
            # 也继续处理其他ETF

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

        # 避免请求过于密集

        time.sleep(0.5)

    # ========================================================
    # 输出JSON
    # ========================================================

    output = {
        "updated_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "source": "Tencent Finance",

        "count": len(results),

        "success": success,

        "failed": failed,

        "data": results,
    }

    # 确保目录存在

    import os

    os.makedirs(
        os.path.dirname(OUTPUT_FILE),
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


if __name__ == "__main__":
    main()