#!/usr/bin/env python3
"""
snapshot_recorder.py — 每日快照记录器
每次数据管道跑完后，将 latest.json 的关键数据存入 snapshots/ 目录。
第 2 天起 signal_engine.py 可对比前后两天计算增长率/加速度。

输出：snapshots/YYYY-MM-DD.json
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / ".workbuddy" / "pipeline" / "data"
SNAPSHOT_DIR = ROOT / ".workbuddy" / "pipeline" / "snapshots"

# 从 card_updater 复用关键词表
SIGNAL_PATTERNS = {
    "空调/家电":    ["空调", "格力", "美的", "海尔", "家电", "热浪"],
    "AI/大模型":    ["AI", "大模型", "GPT", "LLM", "人工智能", "DeepSeek", "ChatGPT"],
    "芯片/半导体":  ["芯片", "半导体", "存储", "NAND", "DRAM", "HBM", "光刻"],
    "机器人":      ["机器人", "人形", "宇树", "Figure", "Optimus", "具身智能"],
    "新能源车":    ["电动车", "新能源", "比亚迪", "蔚来", "理想", "宁德", "特斯拉", "TSLA"],
    "手机/消费电子": ["手机", "iPhone", "华为", "小米", "折叠", "鸿蒙"],
    "黄金/贵金属":  ["黄金", "金价", "贵金属", "Gold"],
    "原油/能源":    ["原油", "油价", "石油", "能源"],
    "关税/贸易":    ["关税", "贸易", "出口管制", "制裁", "加税"],
    "降息/利率":    ["降息", "利率", "Fed", "央行", "PBOC", "加息"],
    "高考":         ["高考", "志愿", "查分", "录取"],
    "618/促销":     ["618", "促销", "大促", "双11"],
    "足球":         ["世界杯", "足球", "英超", "欧冠", "欧洲杯"],
    "游戏":         ["原神", "王者", "黑神话", "Steam"],
}
ENTERTAINMENT = {"足球", "游戏"}
SEASONAL = {"高考", "618/促销"}


def load_latest():
    path = DATA_DIR / "latest.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_all_items(data):
    """从 latest.json 提取所有标题，附带来源和热度值"""
    items = []
    sources = data.get("sources", {})
    for key, src in sources.items():
        if src.get("status") != "ok":
            continue
        label = src.get("label", key)
        src_data = src.get("data", {})
        entries = src_data.get("list", []) if isinstance(src_data, dict) else []
        for i, item in enumerate(entries):
            if isinstance(item, dict):
                title = item.get("title") or item.get("word") or ""
                rank = i + 1  # 1-based ranking
                hot_value = item.get("hot_value") or item.get("hot") or item.get("score") or item.get("index") or 0
                if title:
                    items.append({
                        "source": label,
                        "source_key": key,
                        "title": title[:120],
                        "rank": rank,
                        "hot_value": str(hot_value)[:50],
                    })
    return items


def cluster_topics(items):
    """按关键词聚类，输出每个话题在各平台的提及数"""
    topics = {}
    for sig_name, keywords in SIGNAL_PATTERNS.items():
        matches_per_platform = {}
        total = 0
        platforms = set()
        for item in items:
            title_lower = item["title"].lower()
            for kw in keywords:
                if kw.lower() in title_lower:
                    src = item["source"]
                    matches_per_platform[src] = matches_per_platform.get(src, 0) + 1
                    platforms.add(src)
                    total += 1
                    break
        if total > 0:
            topics[sig_name] = {
                "total_mentions": total,
                "platform_count": len(platforms),
                "platforms": sorted(platforms),
                "per_platform": matches_per_platform,
                "is_seasonal": sig_name in SEASONAL,
                "is_entertainment": sig_name in ENTERTAINMENT,
            }
    return topics


def main():
    data = load_latest()
    if not data:
        print("[snapshot] latest.json 不存在，跳过")
        return 1

    items = extract_all_items(data)
    topics = cluster_topics(items)

    now = datetime.now(CST)
    date_str = now.strftime("%Y-%m-%d")

    snapshot = {
        "date": date_str,
        "generated_at": now.isoformat(),
        "day_number": 1,  # 由 engine 根据实际文件数计算
        "source_meta": {
            "total_items": len(items),
            "sources_ok": sum(1 for s in data.get("sources", {}).values() if s.get("status") == "ok"),
            "sources_total": len(data.get("sources", {})),
        },
        "topics": topics,
    }

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"[snapshot] {path} · {len(items)} 条热词 · {len(topics)} 个话题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
