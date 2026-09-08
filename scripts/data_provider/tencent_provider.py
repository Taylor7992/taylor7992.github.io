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

WATCHLIST_FILE = WATCHLIST_FILE = "_data/etf_watchlist.yml"
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


