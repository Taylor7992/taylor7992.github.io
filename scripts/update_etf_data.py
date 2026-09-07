import json
import time
import random
from datetime import datetime, timedelta

import pandas as pd
import requests
import yaml


# ============================================================
# 配置
# ============================================================

WATCHLIST_FILE = "_data/etf_watchlist.yml"
OUTPUT_FILE = "assets/data/etf_data.json"

HISTORY_DAYS = 3 * 365

# 新浪财经历史行情接口
SINA_KLINE_URL = "https://quotes.sina.cn/cn/api/jsonp_v2.php"

# 新浪实时行情接口
SINA_QUOTE_URL = "https://hq.sinajs.cn/list"


# ============================================================
# Session
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Connection": "keep-alive",
})


# ============================================================
# ETF / LOF
# ============================================================

LOF_CODES = {
    "162719",
    "161226",
}


# ============================================================
# 读取 ETF 列表
# ============================================================

def load_watchlist():

    with open(
        WATCHLIST_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        config = yaml.safe_load(f)

    codes = config.get("codes", [])

    result = []

    for code in codes:

        code = str(code).strip()

        if code and code not in result:
            result.append(code)

    return result


# ============================================================
# 新浪代码
# ============================================================

def get_sina_symbol(code):

    code = str(code)

    if code.startswith(("51", "52", "56", "58")):
        return "sh" + code

    return "sz" + code


# ============================================================
# 请求重试
# ============================================================

def request_with_retry(
    method,
    url,
    params=None,
    timeout=20,
    retries=3
):

    last_error = None

    for attempt in range(1, retries + 1):

        try:

            response = session.request(
                method=method,
                url=url,
                params=params,
                timeout=timeout
            )

            response.raise_for_status()

            return response

        except Exception as e:

            last_error = e

            print(
                f"请求失败，第 {attempt}/{retries} 次：{e}"
            )

            if attempt < retries:

                time.sleep(
                    2 + random.uniform(0.5, 2)
                )

    raise last_error


# ============================================================
# 新浪实时行情
# ============================================================

def get_realtime_quote(code):

    symbol = get_sina_symbol(code)

    url = SINA_QUOTE_URL + "/" + symbol

    response = request_with_retry(
        "GET",
        url,
        timeout=15,
        retries=3
    )

    text = response.text

    # 新浪返回：
    #
    # var hq_str_sz159865="养殖ETF,..."
    #

    if '="' not in text:

        raise RuntimeError(
            "新浪实时接口返回格式异常"
        )

    data = text.split('="', 1)[1]

    data = data.rsplit('"', 1)[0]

    fields = data.split(",")

    if len(fields) < 4:

        raise RuntimeError(
            "新浪实时数据字段不足"
        )

    name = fields[0]

    # 新浪股票行情格式：
    #
    # 0 名称
    # 1 开盘
    # 2 昨收
    # 3 最高
    # 4 最低
    # 5 当前价格
    #

    previous_close = safe_float(fields[2])
    current_price = safe_float(fields[3])

    if len(fields) >= 4:
        current_price = safe_float(fields[3])

    # 对于 ETF，新浪部分接口字段可能不同。
    # 如果价格字段异常，后续会使用历史数据。

    return {
        "name": name,
        "price": current_price,
        "previous_close": previous_close,
    }


# ============================================================
# 新浪历史行情
# ============================================================

def get_history(code):

    symbol = get_sina_symbol(code)

    end_date = datetime.now()

    start_date = (
        end_date -
        timedelta(days=HISTORY_DAYS)
    )

    params = {
        "symbol": symbol,
        "scale": "240",
        "ma": "no",
        "datalen": "1000",
    }

    response = request_with_retry(
        "GET",
        SINA_KLINE_URL,
        params=params,
        timeout=20,
        retries=3
    )

    text = response.text.strip()

    if not text:

        raise RuntimeError(
            "新浪历史接口返回为空"
        )

    # 尝试解析 JSONP
    #
    # var data = {...}
    #

    json_start = text.find("{")
    json_end = text.rfind("}")

    if json_start == -1 or json_end == -1:

        raise RuntimeError(
            "新浪历史接口返回格式无法解析"
        )

    json_text = text[
        json_start:
        json_end + 1
    ]

    try:

        data = json.loads(json_text)

    except Exception:

        raise RuntimeError(
            "新浪历史数据 JSON 解析失败"
        )

    # 尝试寻找数据
    records = None

    if isinstance(data, dict):

        for key in (
            "data",
            "result",
            "day",
            "items"
        ):

            if key in data:

                records = data[key]
                break

    if records is None:

        raise RuntimeError(
            "新浪历史数据中没有找到 K 线"
        )

    if not isinstance(records, list):

        raise RuntimeError(
            "新浪历史 K 线格式异常"
        )

    rows = []

    for item in records:

        if not isinstance(item, dict):
            continue

        date = (
            item.get("day")
            or item.get("date")
            or item.get("d")
        )

        close = (
            item.get("close")
            or item.get("c")
        )

        high = (
            item.get("high")
            or item.get("h")
        )

        low = (
            item.get("low")
            or item.get("l")
        )

        if date is None or close is None:
            continue

        rows.append({
            "date": date,
            "close": safe_float(close),
            "high": safe_float(high),
            "low": safe_float(low),
        })

    if not rows:

        raise RuntimeError(
            "新浪历史 K 线解析后为空"
        )

    df = pd.DataFrame(rows)

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce"
    )

    df["close"] = pd.to_numeric(
        df["close"],
        errors="coerce"
    )

    df["high"] = pd.to_numeric(
        df["high"],
        errors="coerce"
    )

    df["low"] = pd.to_numeric(
        df["low"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["date", "close"]
    )

    df = df.sort_values(
        "date"
    ).reset_index(drop=True)

    return df


# ============================================================
# 数值转换
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
# 区间涨跌
# ============================================================

def calculate_return(df, days):

    if len(df) < 2:
        return None

    latest = float(
        df.iloc[-1]["close"]
    )

    index = max(
        0,
        len(df) - 1 - days
    )

    old = float(
        df.iloc[index]["close"]
    )

    if old == 0:
        return None

    return (
        latest / old - 1
    ) * 100


# ============================================================
# 最大回撤
# ============================================================

def calculate_max_drawdown(df):

    prices = df["close"].astype(float)

    running_max = prices.cummax()

    drawdown = (
        prices /
        running_max -
        1
    )

    return float(
        drawdown.min() * 100
    )


# ============================================================
# 当前回撤
# ============================================================

def calculate_current_drawdown(
    df,
    current_price
):

    if current_price is None:
        return None

    historical_high = float(
        df["close"].max()
    )

    if historical_high == 0:
        return None

    return (
        current_price /
        historical_high -
        1
    ) * 100


# ============================================================
# 平均回撤
# ============================================================

def calculate_average_drawdown(df):

    prices = (
        df["close"]
        .astype(float)
        .tolist()
    )

    if len(prices) < 2:
        return None

    running_high = prices[0]

    drawdowns = []

    current_drawdown = 0

    for price in prices[1:]:

        if price >= running_high:

            if current_drawdown < 0:

                drawdowns.append(
                    current_drawdown
                )

            running_high = price
            current_drawdown = 0

        else:

            drawdown = (
                price /
                running_high -
                1
            )

            if drawdown < current_drawdown:

                current_drawdown = drawdown

    if current_drawdown < 0:

        drawdowns.append(
            current_drawdown
        )

    if not drawdowns:
        return 0

    return float(
        sum(drawdowns) /
        len(drawdowns) *
        100
    )


# ============================================================
# 处理单个 ETF
# ============================================================

def process_etf(code):

    print("=" * 50)

    print(
        f"正在处理 {code}"
    )

    try:

        # ----------------------------------------------------
        # 历史数据
        # ----------------------------------------------------

        print(
            f"{code}：获取历史数据..."
        )

        df = get_history(code)

        print(
            f"{code}：历史数据 {len(df)} 条"
        )

        if df.empty:

            raise RuntimeError(
                "历史数据为空"
            )

        # ----------------------------------------------------
        # 实时行情
        # ----------------------------------------------------

        quote = None

        try:

            print(
                f"{code}：获取实时行情..."
            )

            quote = get_realtime_quote(
                code
            )

        except Exception as e:

            print(
                f"{code}：实时行情失败：{e}"
            )

        # ----------------------------------------------------
        # 名称
        # ----------------------------------------------------

        if quote and quote.get("name"):

            name = quote["name"]

        else:

            name = code

        # ----------------------------------------------------
        # 最新价格
        # ----------------------------------------------------

        realtime_price = None

        if quote:

            realtime_price = safe_float(
                quote.get("price")
            )

        if (
            realtime_price is not None
            and realtime_price > 0
        ):

            latest_price = realtime_price

        else:

            latest_price = safe_float(
                df.iloc[-1]["close"]
            )

        # ----------------------------------------------------
        # 今日涨跌幅
        # ----------------------------------------------------

        if (
            quote
            and quote.get("previous_close")
            and realtime_price
        ):

            previous_close = safe_float(
                quote["previous_close"]
            )

            if (
                previous_close
                and previous_close != 0
            ):

                return_1d = (
                    realtime_price /
                    previous_close -
                    1
                ) * 100

            else:

                return_1d = None

        elif len(df) >= 2:

            previous_close = float(
                df.iloc[-2]["close"]
            )

            today_close = float(
                df.iloc[-1]["close"]
            )

            if previous_close != 0:

                return_1d = (
                    today_close /
                    previous_close -
                    1
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

        max_drawdown = (
            calculate_max_drawdown(df)
        )

        # ----------------------------------------------------
        # 平均回撤
        # ----------------------------------------------------

        avg_drawdown = (
            calculate_average_drawdown(df)
        )

        # ----------------------------------------------------
        # 当前回撤
        # ----------------------------------------------------

        current_drawdown = (
            calculate_current_drawdown(
                df,
                latest_price
            )
        )

        print(
            f"{code}：成功"
        )

        print(
            f"价格={latest_price}"
        )

        print(
            f"今日={return_1d}"
        )

        print(
            f"1周={return_1w}"
        )

        print(
            f"1月={return_1m}"
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

        error_message = (
            type(e).__name__ +
            ": " +
            str(e)
        )

        print(
            f"{code}：处理失败："
            f"{error_message}"
        )

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
            "error_message": error_message,
        }


# ============================================================
# 主程序
# ============================================================

def main():

    print("=" * 60)

    print(
        "ETF 数据更新程序"
    )

    print(
        "数据源：新浪财经"
    )

    print("=" * 60)

    codes = load_watchlist()

    print(
        f"读取到 {len(codes)} 个 ETF"
    )

    results = []

    for code in codes:

        result = process_etf(code)

        results.append(result)

        # 随机等待
        time.sleep(
            random.uniform(1, 2)
        )

    # --------------------------------------------------------
    # 输出
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
        1
        for item in results
        if not item["error"]
    )

    print("=" * 60)

    print(
        f"更新完成："
        f"{success_count}/"
        f"{len(results)} 成功"
    )

    print("=" * 60)


if __name__ == "__main__":

    main()