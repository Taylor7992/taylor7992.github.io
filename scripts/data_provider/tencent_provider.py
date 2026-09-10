import json
import random
import time

import pandas as pd
import requests


# ============================================================
# 基本配置
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

    腾讯历史K线主要提供：

    bar[0] 日期
    bar[1] 开盘
    bar[2] 收盘
    bar[3] 最高
    bar[4] 最低
    bar[5] 成交量

    注意：
    历史K线这里不再猜测成交额字段。
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

            # 腾讯接口可能返回：
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

                if len(bar) < 6:
                    continue

                try:

                    volume = None

                    try:
                        volume = float(bar[5])
                    except (ValueError, TypeError):
                        pass

                    rows.append({
                        "date": bar[0],
                        "open": float(bar[1]),
                        "close": float(bar[2]),
                        "high": float(bar[3]),
                        "low": float(bar[4]),
                        "volume": volume,
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

    这里除了价格和涨跌幅之外，
    重点读取当天成交额。

    腾讯字段：

    fields[1]  = 名称
    fields[3]  = 当前价格
    fields[4]  = 昨收
    fields[5]  = 今开
    fields[6]  = 成交量（手）
    fields[30] = 时间
    fields[31] = 涨跌额
    fields[32] = 涨跌幅
    fields[33] = 最高
    fields[34] = 最低
    fields[36] = 成交量（手）
    fields[37] = 成交额（万元）
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

        # 腾讯实时接口通常使用 GBK
        response.encoding = "gbk"

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
            .strip(";")
        )

        fields = value.split("~")

        if len(fields) < 38:
            raise RuntimeError(
                f"实时行情字段不足：{len(fields)}"
            )

        name = fields[1]

        price = float(fields[3])

        prev_close = float(fields[4])

        open_price = float(fields[5])

        # ----------------------------------------------------
        # 今日涨跌幅
        # ----------------------------------------------------

        if prev_close > 0:

            change_pct = (
                (price - prev_close)
                / prev_close
                * 100
            )

        else:

            change_pct = 0

        # ----------------------------------------------------
        # 成交量
        # ----------------------------------------------------

        volume = None

        try:
            volume = float(fields[36])
        except (ValueError, TypeError):
            pass

        # ----------------------------------------------------
        # 成交额
        #
        # 腾讯 fields[37] 的单位是：
        # 万元
        #
        # 页面热力图使用元，
        # 所以这里 × 10000
        # ----------------------------------------------------

        amount = None

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
            "volume": volume,
            "amount": amount,
        }

    except Exception as e:

        print(
            f"  实时行情获取失败：{code}：{e}"
        )

        return None