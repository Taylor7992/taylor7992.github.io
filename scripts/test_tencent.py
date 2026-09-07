import json
import random
import requests
import re


def test(code):
    print("=" * 60)
    print(f"测试 ETF：{code}")

    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"

    params = {
        "_var": "kline_dayqfq",
        "param": f"{code},day,,,1095,qfq",
        "r": str(random.random()),
    }

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=20
        )

        print("HTTP状态码：", r.status_code)
        print("请求地址：", r.url)

        text = r.text.strip()

        print("\n腾讯返回数据前500字符：")
        print(text[:500])

        if not text:
            print("\n❌ 返回内容为空")
            return

        # 腾讯接口通常返回：
        # kline_dayqfq={...}
        if "=" in text and not text.startswith("{"):
            text = text.split("=", 1)[1]

        text = text.strip().rstrip(";")

        data = json.loads(text)

        print("\nJSON解析：成功")
        print("顶层字段：", data.keys())

        data_part = data.get("data", {})

        print("data字段：", data_part.keys())

        item = data_part.get(code)

        if not item:
            print(f"\n❌ 没有找到 {code} 的数据")
            print("实际返回：", data_part)
            return

        print("\nETF数据字段：", item.keys())

        bars = (
            item.get("qfqday")
            or item.get("day")
            or item.get("qfqweek")
        )

        if not bars:
            print("\n❌ 没有找到K线数据")
            print("ETF返回内容：", item)
            return

        print(f"\n✅ 成功获取K线：{len(bars)}条")

        print("\n第一条：")
        print(bars[0])

        print("\n最后一条：")
        print(bars[-1])

        print("\n🎉 腾讯接口测试成功！")

    except Exception as e:
        print("\n❌ 测试失败：")
        print(type(e).__name__, e)


# 上海ETF
test("sh513350")

# 深圳ETF
test("sz159985")