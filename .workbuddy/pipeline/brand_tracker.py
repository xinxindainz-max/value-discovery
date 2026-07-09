#!/usr/bin/env python3
"""
品牌追踪引擎 v6.0 — 极简版
15个品牌 × Google Trends + 5个国内平台提及
无评分、无等级、无估值。只显示数据。
"""
import json
import sys
import os
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / ".workbuddy" / "pipeline" / "data"

sys.path.insert(0, str(ROOT / ".workbuddy" / "pipeline"))
from brand_config import BRANDS
from trends_fetcher import get_google_growth, get_usage_summary
from history_manager import append_history, calculate_changes, save_snapshot, cleanup_old_data, get_history_summary

DOMESTIC_PLATFORMS = ["抖音总榜", "小红书热榜", "微博热搜", "知乎热榜", "百度热搜"]
DISCOVERY_PLATFORMS = ["抖音总榜", "小红书热榜"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_entries(src_data):
    """从数据源提取条目列表"""
    entries = src_data.get("list", []) if isinstance(src_data, dict) else []
    body = src_data.get("body", "") if isinstance(src_data, dict) else ""
    if body and not entries:
        try:
            parsed = json.loads(body)
            raw_data = parsed.get("data", [])
            if raw_data:
                entries = []
                for item in raw_data:
                    if isinstance(item, list) and len(item) >= 2:
                        entries.append({"title": str(item[1]), "rank": item[0]})
                    elif isinstance(item, dict):
                        entries.append(item)
        except (json.JSONDecodeError, KeyError):
            pass
    return entries


def count_brand_mentions(latest_data, keywords):
    """在5个国内平台中统计品牌提及"""
    result = {}
    sources = latest_data.get("sources", {})
    for key, src in sources.items():
        label = src.get("label", key)
        if label not in DOMESTIC_PLATFORMS or src.get("status") != "ok":
            continue
        entries = extract_entries(src.get("data", {}))
        count = 0
        titles = []
        for item in entries:
            title = ""
            if isinstance(item, dict):
                title = item.get("title", "") or item.get("word", "")
            elif isinstance(item, str):
                title = item
            if not title:
                continue
            for kw in keywords:
                if kw.lower() in title.lower():
                    count += 1
                    if len(titles) < 3:
                        titles.append(title[:50])
                    break
        result[label] = {"count": count, "titles": titles}
    return result


def get_discovery_list(latest_data):
    """获取发现层raw热搜（抖音+小红书）"""
    discovery = {}
    sources = latest_data.get("sources", {})
    for key, src in sources.items():
        label = src.get("label", key)
        if label not in DISCOVERY_PLATFORMS or src.get("status") != "ok":
            continue
        entries = extract_entries(src.get("data", {}))
        items = []
        for i, item in enumerate(entries[:10]):
            title = ""
            if isinstance(item, dict):
                title = item.get("title", "") or item.get("word", "")
            elif isinstance(item, str):
                title = item
            if title:
                items.append({"rank": i + 1, "title": title[:80]})
        discovery[label] = items
    return discovery


def get_cached_google(prev_results, brand_name, google_keyword):
    """从上次结果获取Google缓存"""
    prev = prev_results.get(brand_name, {})
    # v6格式
    prev_g = prev.get("google", {})
    if prev_g and prev_g.get("growth_1m") is not None:
        return prev_g
    # v5格式
    prev_gs = prev.get("dimensions", {}).get("google_search", {})
    if prev_gs.get("growth_1m") is not None:
        return prev_gs
    prev_gs2 = prev.get("details", {}).get("google_search", {})
    if prev_gs2.get("growth_1m") is not None:
        return prev_gs2
    return None


def run_tracker():
    latest_path = DATA_DIR / "latest.json"
    output_path = DATA_DIR / "discovery_board.json"

    latest_data = load_json(latest_path) if latest_path.exists() else {}

    prev_results = {}
    if output_path.exists():
        try:
            prev_data = load_json(output_path)
            for b in prev_data.get("brands", []):
                prev_results[b["name"]] = b
        except Exception:
            pass

    print(f"[tracker] 开始追踪 {len(BRANDS)} 个品牌")
    print(f"[tracker] 国内数据: {'已加载' if latest_data else '未找到'}")
    print(f"[tracker] 缓存: {len(prev_results)}个品牌")

    results = []

    for i, brand in enumerate(BRANDS, 1):
        name = brand["name"]
        print(f"\n[{i}/{len(BRANDS)}] {name} ({brand['code']}.{brand['market']})")

        # Google Trends
        google = None
        cached = get_cached_google(prev_results, name, brand["google_keyword"])
        if cached:
            google = cached
            print(f"  Google: (缓存) 1M={google['growth_1m']}% 3M={google.get('growth_3m', 0)}%")
        else:
            fb_path = DATA_DIR / "google_cache.json"
            fb = None
            if fb_path.exists():
                fb_data = load_json(fb_path)
                fb = fb_data.get(brand["google_keyword"])
            if fb:
                google = fb
                print(f"  Google: (fallback) 1M={fb['growth_1m']}% 3M={fb['growth_3m']}%")
            else:
                raw = get_google_growth(brand["google_keyword"])
                if raw:
                    g1m = raw.get("1M", {}).get("growth", 0)
                    g3m = raw.get("3M", {}).get("growth", 0)
                    gval = raw.get("1M", {}).get("recent_value", 0)
                    google = {"growth_1m": round(g1m, 1), "growth_3m": round(g3m, 1), "recent_value": gval}
                    print(f"  Google: 1M={g1m}% 3M={g3m}%")
                else:
                    print(f"  Google: 无数据")

        # 国内5平台提及
        platforms = count_brand_mentions(latest_data, brand["domestic_keywords"])
        platform_count = sum(1 for p in platforms.values() if p["count"] > 0)
        for pname, pinfo in platforms.items():
            if pinfo["count"] > 0:
                print(f"  {pname}: {pinfo['count']}条")
        print(f"  → {platform_count}/5平台提及")

        # 存历史
        if google:
            append_history(name, "google_growth_1m", google.get("growth_1m", 0))
            append_history(name, "google_growth_3m", google.get("growth_3m", 0))
            append_history(name, "google_value", google.get("recent_value", 0))
        for pname in DOMESTIC_PLATFORMS:
            pinfo = platforms.get(pname, {"count": 0})
            short_name = pname.replace("总榜", "").replace("热榜", "").replace("热搜", "")
            append_history(name, f"{short_name}_mentions", pinfo["count"])

        # 计算历史趋势（7/30天变化）
        trends = {}
        if google:
            trends["google_1m"] = google.get("growth_1m")
            trends["google_3m"] = google.get("growth_3m")
        for pname in DOMESTIC_PLATFORMS:
            short_name = pname.replace("总榜", "").replace("热榜", "").replace("热搜", "")
            current = platforms.get(pname, {"count": 0})["count"]
            changes = calculate_changes(name, f"{short_name}_mentions", current)
            trends[f"{short_name}_7d"] = changes.get("change_7d")
            trends[f"{short_name}_30d"] = changes.get("change_30d")
            trends[f"{short_name}_days"] = changes.get("history_days", 0)

        # 品牌结果
        result = {
            "name": name,
            "code": brand["code"],
            "market": brand["market"],
            "industry": brand["industry"],
            "google": google,
            "platforms": platforms,
            "platform_count": platform_count,
            "trends": trends,
        }
        results.append(result)

    # 按平台提及数排序（多的在前）
    results.sort(key=lambda x: x["platform_count"], reverse=True)

    # 发现层
    discovery = get_discovery_list(latest_data)

    # 清理旧数据
    cleanup_old_data(90)

    # 输出
    now = datetime.now(CST)
    hist = get_history_summary()
    output = {
        "generated_at": now.isoformat(),
        "system": "中国上市公司消费者行为雷达 v6.0",
        "brand_count": len(BRANDS),
        "brands": results,
        "discovery": discovery,
        "meta": {
            "data_time": now.strftime("%Y-%m-%d %H:%M") + " CST",
            "platforms": DOMESTIC_PLATFORMS,
            "history": hist,
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    save_snapshot(output)

    dist_dir = ROOT / "dist" / "data"
    dist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_path, dist_dir / "discovery_board.json")

    public_dir = ROOT / "data"
    public_dir.mkdir(exist_ok=True)
    shutil.copy2(output_path, public_dir / "discovery_board.json")

    print(f"\n[tracker] ===== 完成 =====")
    print(f"[tracker] 已写入 {output_path}")
    print(f"\n[tracker] ===== API额度 =====")
    get_usage_summary()

    # 打印有提及的品牌
    mentioned = [b for b in results if b["platform_count"] > 0]
    if mentioned:
        print(f"\n[tracker] 有国内平台提及的品牌:")
        for b in mentioned:
            print(f"  {b['name']}({b['code']}) — {b['platform_count']}/5平台")
    else:
        print(f"\n[tracker] 今日无品牌在国内平台被提及")

    return output


if __name__ == "__main__":
    run_tracker()
