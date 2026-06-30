#!/usr/bin/env python3
"""
价值发现 · page_meta.json 生成器 v3.0
不再修改 HTML，输出 data/page_meta.json 供 JS 客户端加载。
彻底消除自动管道与人工编辑的 git 冲突。
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CST = timezone(timedelta(hours=8))
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_DIR, ".workbuddy", "pipeline", "data")


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_source_status(latest_data):
    """构建数据源状态映射 source_key → {label, ok, count}"""
    if not latest_data or "sources" not in latest_data:
        return {}
    sources = {}
    for key, src in latest_data["sources"].items():
        ok = src.get("status") == "ok"
        count = 0
        data = src.get("data", {})
        if isinstance(data, dict):
            items = data.get("list", data.get("items", []))
            if isinstance(items, list):
                count = len(items)
        sources[key] = {
            "label": src.get("label", key),
            "ok": ok,
            "count": count,
        }
    return sources


def build_stock_snapshot(stocks_data):
    """构建股票快照 {code: {name, price, pe, pb, chg_5d, chg_20d, chg_60d}}"""
    if not stocks_data or "stocks" not in stocks_data:
        return {}
    snap = {}
    for code, s in stocks_data["stocks"].items():
        snap[code] = {
            "name": s.get("name", ""),
            "price": s.get("price"),
            "pe": s.get("pe_ratio"),
            "pb": s.get("pb_ratio"),
            "chg_5d": s.get("change_5d"),
            "chg_20d": s.get("change_20d"),
            "chg_60d": s.get("change_60d"),
            "market": s.get("market", ""),
        }
    return snap


def main():
    now = datetime.now(CST)
    ts_str = now.strftime("%Y-%m-%d %H:%M CST")
    print(f"page_meta 生成器 v3.0 · {ts_str}")

    latest = load_json(os.path.join(DATA_DIR, "latest.json"))
    stocks = load_json(os.path.join(DATA_DIR, "stocks.json"))

    ok_count = 0
    total = 0
    source_status = {}
    if latest:
        source_status = build_source_status(latest)
        total = len(source_status)
        ok_count = sum(1 for s in source_status.values() if s["ok"])

    stock_snapshot = {}
    if stocks:
        stock_snapshot = build_stock_snapshot(stocks)

    meta = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "display_ts": ts_str,
        "sources_ok": ok_count,
        "sources_total": total,
        "source_bar_text": f"{ok_count}/{total} 源可用",
        "sources": source_status,
        "stocks": stock_snapshot,
    }

    meta_path = os.path.join(DATA_DIR, "page_meta.json")
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[✓] page_meta.json · {ok_count}/{total} 源 · {len(stock_snapshot)} 只股票")
    return 0


if __name__ == "__main__":
    sys.exit(main())
