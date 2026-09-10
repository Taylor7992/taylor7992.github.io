import json
import random
import time

import pandas as pd
import requests


# ============================================================
# 腾讯财经接口
# ============================================================

TENCENT_URL = (
    "https://proxy.finance.qq.com/"
    "ifzqgtimg/appstock/app/newfqkline/get"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 "
                  "(Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 "
                  "(KHTML, like Gecko) "
                  "Chrome/131.0 Safari/537.36"
}

# 获取大约 3 年的历史数据
KLINE_COUNT = 1095


# ============================================================
# 判断 ETF 所属市场
# ============================================================

def market_code(code):
    code = str(code).zfill(6)

    if code.startswith("5"):
        return "sh" + code

    if code.startswith("15") or code.startswith("16"):
        return "sz" + code

    raise ValueError(f"无法判断市场：{code}")


# ============================================================
# 获取历史 K 线
# ============================================================

def get_history(code):
    """
    获取 ETF 历史日线数据。

    腾讯历史 K 线主要提供：
    日期、开盘、收盘、最高、最低、成交量

    腾讯历史接口没有稳定提供历史成交额，
    所以这里使用：

        成交量 × 收盘价 × 100

    来估算每日成交额。

    成交量单位为“手”，
    ETF 1 手通常为 100 份。

    后面的 etf_data.py 会使用这些数据
    计算近 1 周、近 1 月成交额。
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
                timeout=20
            )

            response.raise_for_status()

            text = response.text.strip()

            if not text:
                raise RuntimeError("腾讯返回内容为空")

            # 腾讯有时会返回：
            # kline_dayqfq= {...}
            if "=" in text and not text.startswith("{"):
                text = text.split("=", 1)[1]

            text = text.strip().rstrip(";")

            data = json.loads(text)

            if data.get("code") != 0:
                raise RuntimeError(
                    f"腾讯接口返回错误：{data}"
                )

            item = data.get("data", {}).get(symbol)

            if not item:
                raise RuntimeError(
                    f"没有找到 ETF 数据：{symbol}"
                )

            bars = item.get("qfqday") or item.get("day")

            if not bars:
                raise RuntimeError(
                    f"没有找到 K 线：{symbol}"
                )

            rows = []

            for bar in bars:

                if len(bar) < 5:
                    continue

                try:
                    volume = None

                    # 腾讯历史 K 线中的成交量
                    if len(bar) > 5:
                        try:
                            volume = float(bar[5])
                        except (ValueError, TypeError):
                            volume = None

                    open_price = float(bar[1])
                    close_price = float(bar[2])
                    high_price = float(bar[3])
                    low_price = float(bar[4])

                    # ------------------------------------------------
                    # 估算每日成交额
                    #
                    # 成交量单位：手
                    # 1 手 ETF = 100 份
                    #
                    # 成交额 ≈ 成交量 × 收盘价 × 100
                    # ------------------------------------------------
                    amount = None

                    if volume is not None and close_price > 0:
                        amount = (
                            volume
                            * close_price
                            * 100
                        )

                    rows.append({
                        "date": bar[0],
                        "open": open_price,
                        "close": close_price,
                        "high": high_price,
                        "low": low_price,
                        "volume": volume,
                        "amount": amount,
                    })

                except (ValueError, TypeError):
                    continue

            if not rows:
                raise RuntimeError(
                    f"K 线解析后没有有效数据：{symbol}"
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
# 获取实时行情
# ============================================================

def get_realtime(code):
    """
    获取腾讯实时行情。

    除了名称、价格、涨跌幅之外，
    同时获取当天实际成交额。
    """

    symbol = market_code(code)

    url = f"https://qt.gtimg.cn/q={symbol}"

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        text = response.text.strip()

        if "=" not in text:
            raise RuntimeError(
                "实时行情返回格式异常"
            )

        value = (
            text
            .split("=", 1)[1]
            .strip()
            .strip('"')
        )

        fields = value.split("~")

        if len(fields) < 6:
            raise RuntimeError(
                "实时行情字段不足"
            )

        name = fields[1]

        price = float(fields[3])

        prev_close = float(fields[4])

        open_price = float(fields[5])

        # ------------------------------------------------
        # 今日涨跌幅
        # ------------------------------------------------

        if prev_close > 0:
            change_pct = (
                (price - prev_close)
                / prev_close
                * 100
            )
        else:
            change_pct = 0

        # ------------------------------------------------
        # 腾讯实时行情：
        #
        # fields[37] = 成交额
        # 单位：万元
        #
        # 转换为元
        # ------------------------------------------------

        amount = None

        if len(fields) > 37:

            try:
                amount_wan = float(fields[37])

                if amount_wan >= 0:
                    amount = amount_wan * 10000

            except (ValueError, TypeError):
                amount = None

        return {
            "name": name,
            "price": price,
            "prev_close": prev_close,
            "open": open_price,
            "change_pct": change_pct,
            "amount": amount,
        }

    except Exception as e:

        print(
            f"  实时行情获取失败：{code}：{e}"
        )

        return None