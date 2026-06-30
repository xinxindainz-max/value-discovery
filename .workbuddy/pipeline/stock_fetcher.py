#!/usr/bin/env python3
"""
价值发现 · 股票行情抓取 v1.0
使用腾讯自选股公开API获取A股实时行情，无依赖。
API: https://qt.gtimg.cn/q=<codes>
输出与 westock-data 相同格式的字段。
"""

import json
import os
import sys
import time
import re
from datetime import datetime, timezone, timedelta

# GitHub Actions 环境强制 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import requests
except ImportError:
    print("[FATAL] requests 库未安装")
    sys.exit(1)

CST = timezone(timedelta(hours=8))

# 腾讯自选股API字段映射 (基于实际测试)
# 格式: v_CODE="field0~field1~field2~..."
FIELD_MAP = {
    "name": 1,            # 股票名称
    "code": 2,            # 代码(纯数字)
    "price": 3,           # 最新价
    "prev_close": 4,      # 昨收
    "open": 5,            # 今开
    "high": 33,           # 最高
    "low": 34,            # 最低
    "volume": 6,          # 成交量(手)
    "amount": 37,         # 成交额(万)
    "pe_ratio": 39,       # PE(TTM)
    "pb_ratio": 46,       # PB
    "total_market_cap": 45,# 总市值(亿)
    "circulating_market_cap": 44, # 流通市值(亿)
    "high_52week": 41,    # 52周最高
    "low_52week": 42,     # 52周最低
    "chg_5d": None,       # 需要从别处获取或计算
    "chg_20d": None,
    "chg_60d": None,
    "chg_ytd": None,
}

def normalize_code(code):
    """标准化股票代码: 000333 → sz000333, 600988 → sh600988"""
    code = code.strip()
    if code.startswith(("sh", "sz", "bj", "hk")):
        return code
    if code.startswith(("6", "5")):
        return f"sh{code}"
    if code.startswith(("0", "3", "2")):
        return f"sz{code}"
    if code.startswith("4") or code.startswith("8"):
        return f"bj{code}"
    return code


def parse_tencent_line(line):
    """解析腾讯自选股返回的一行数据"""
    # 格式: v_sz000333="51~美的集团~000333~77.27~..."
    match = re.search(r'v_(\w+)="(.+)"', line)
    if not match:
        return None

    raw_code = match.group(1)
    fields = match.group(2).split("~")

    if len(fields) < 50:
        return None

    try:
        result = {
            "code": raw_code,
            "name": fields[1],
            "price": float(fields[3]) if fields[3] else None,
            "prev_close": float(fields[4]) if fields[4] else None,
            "open": float(fields[5]) if fields[5] else None,
            "high": float(fields[33]) if fields[33] else None,
            "low": float(fields[34]) if fields[34] else None,
            "volume": int(fields[6]) if fields[6] else 0,
            "amount": float(fields[37]) if fields[37] else 0,
            "pe_ratio": float(fields[39]) if fields[39] and fields[39] != "0" else None,
            "pb_ratio": float(fields[46]) if fields[46] else None,
            "total_market_cap": float(fields[45]) if fields[45] else None,
            "circulating_market_cap": float(fields[44]) if fields[44] else None,
            "high_52week": float(fields[41]) if fields[41] else None,
            "low_52week": float(fields[42]) if fields[42] else None,
            "change_pct": float(fields[32]) if fields[32] else None,
        }
        return result
    except (ValueError, IndexError) as e:
        return None


def fetch_stocks(codes, timeout=10):
    """
    批量获取股票行情
    codes: ["sz000333", "sh600988", ...]
    返回: {code: {fields}}
    """
    if not codes:
        return {}

    # 腾讯API每次最多约20只
    results = {}
    batch_size = 20

    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        url_codes = ",".join(batch)
        url = f"https://qt.gtimg.cn/q={url_codes}"

        try:
            resp = requests.get(url, timeout=timeout,
                               headers={"User-Agent": "Mozilla/5.0"})
            resp.encoding = "gbk"
            if resp.status_code != 200:
                print(f"[STOCK] HTTP {resp.status_code} for {url_codes}")
                continue

            for line in resp.text.strip().split("\n"):
                if not line.strip() or "=" not in line:
                    continue
                parsed = parse_tencent_line(line)
                if parsed:
                    results[parsed["code"]] = parsed

        except Exception as e:
            print(f"[STOCK] 抓取失败 {url_codes}: {e}")

    return results


# 当前发现榜关注的股票池
WATCHLIST_CODES = [
    "sz000333",  # 美的集团
    "sz000651",  # 格力电器
    "sh600690",  # 海尔智家
    "sh603128",  # 华贸物流
    "sz300729",  # 乐歌股份
    "sh600988",  # 赤峰黄金
    "sh688981",  # 中芯国际
    "sh603019",  # 中科曙光
    "sz300750",  # 宁德时代
    "sh600519",  # 贵州茅台
    "sh600036",  # 招商银行
    "sz000858",  # 五粮液
    "sz002475",  # 立讯精密
    "sz300274",  # 阳光电源
]


def main():
    print("价值发现 · 股票行情抓取 v1.0")
    print(f"时间: {datetime.now(CST).isoformat()}")

    results = fetch_stocks(WATCHLIST_CODES)

    # 保存到JSON
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "data", "stocks.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    output = {
        "fetched_at": datetime.now(CST).isoformat(),
        "fetched_at_unix": int(time.time()),
        "stocks": results,
        "count": len(results),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    for code, s in results.items():
        pe_str = f"PE:{s['pe_ratio']:.2f}" if s['pe_ratio'] else "PE:N/A"
        print(f"  {s['name']:8s} {code}  {s['price']:.2f}  {pe_str}  "
              f"chg:{s['change_pct']:+.2f}%")
    print(f"\n共 {len(results)}/{len(WATCHLIST_CODES)} 只股票获取成功")
    print(f"已保存到 {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
