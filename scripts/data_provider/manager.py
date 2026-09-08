"""
ETF 数据源管理器

职责：
1. 统一管理 ETF 数据源
2. 按优先级尝试不同 Provider
3. Provider 失败时自动切换下一个
4. 对外提供统一的 get_history / get_realtime 接口
5. 后续新增数据源时，不需要修改 ETF 计算逻辑
"""

from . import tencent_provider
from .base import standardize_history


# ============================================================
# 数据源配置
# ============================================================

# 历史数据优先级
HISTORY_PROVIDERS = [
    tencent_provider,
]

# 实时数据优先级
REALTIME_PROVIDERS = [
    tencent_provider,
]


# ============================================================
# 历史数据
# ============================================================

def get_history(code, count=1095):
    """
    按优先级获取 ETF 历史数据。

    返回：
        DataFrame 或 None
    """

    for provider in HISTORY_PROVIDERS:

        provider_name = provider.__name__.split(".")[-1]

        try:
            print(
                f"  → 尝试历史数据源：{provider_name}"
            )

            df = provider.get_history(
                code,
                count=count
            )

            if df is None:
                print(
                    f"  × {provider_name} 未返回数据"
                )
                continue

            df = standardize_history(df)

            if df is None or df.empty:
                print(
                    f"  × {provider_name} 数据无效"
                )
                continue

            print(
                f"  ✓ 历史数据源：{provider_name}"
            )

            return df

        except Exception as e:

            print(
                f"  × {provider_name} 失败：{e}"
            )

    print(
        f"  × 所有历史数据源均失败：{code}"
    )

    return None


# ============================================================
# 实时数据
# ============================================================

def get_realtime(code):
    """
    按优先级获取 ETF 实时数据。

    返回：
        dict 或 None
    """

    for provider in REALTIME_PROVIDERS:

        provider_name = provider.__name__.split(".")[-1]

        try:
            print(
                f"  → 尝试实时数据源：{provider_name}"
            )

            data = provider.get_realtime(code)

            if data is None:
                print(
                    f"  × {provider_name} 未返回数据"
                )
                continue

            print(
                f"  ✓ 实时数据源：{provider_name}"
            )

            return data

        except Exception as e:

            print(
                f"  × {provider_name} 失败：{e}"
            )

    print(
        f"  × 所有实时数据源均失败：{code}"
    )

    return None