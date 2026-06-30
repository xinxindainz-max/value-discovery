#!/usr/bin/env python3
"""
signal_engine.py — Top 10 Signal Filter Engine
规格冻结版 v1.0 · 按 ChatGPT 修正后的 5 项 Spec Lock 实现

功能：
1. 快照基础设施（首日自动生成）
2. 5因子打分系统（growth / acceleration / multi_source / novelty）
3. 噪音过滤器 + percentile_rank 门禁
4. 冷启动/过渡/正常三模式自动切换
5. Top 10 筛选 + JSON 输出
"""
import json
import math
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / ".workbuddy" / "pipeline" / "data"
SNAPSHOT_DIR = ROOT / ".workbuddy" / "pipeline" / "snapshots"

# ── 关键词聚类（与 card_updater.py 保持一致）──
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
}
SEASONAL_PATTERNS = {
    "高考":  ["高考", "志愿", "查分", "录取"],
    "618/促销": ["618", "促销", "大促", "双11"],
}
ENTERTAINMENT_PATTERNS = {
    "足球": ["世界杯", "足球", "英超", "欧冠", "欧洲杯"],
    "游戏": ["原神", "王者", "黑神话", "Steam"],
}

# ── 平台权重表（冻结版）──
PLATFORM_TIERS = {
    # early_social (3.0)
    "X/Twitter Trending": ("early_social", 3.0),
    "Reddit World News":  ("early_social", 3.0),
    # search_trends (2.5)
    "Google Trends":      ("search_trends", 2.5),
    # consumer_discussion (2.0)
    "豆瓣":                ("consumer_discussion", 2.0),
    "小红书":              ("consumer_discussion", 2.0),
    "什么值得买":          ("consumer_discussion", 2.0),
    "虎扑":                ("consumer_discussion", 2.0),
    "YouTube Trending":   ("consumer_discussion", 2.0),
    # general_content (1.5)
    "B站全站日榜":         ("general_content", 1.5),
    "抖音总榜":            ("general_content", 1.5),
    "快手":                ("general_content", 1.5),
    "知乎热榜":            ("general_content", 1.5),
    "百度贴吧":            ("general_content", 1.5),
    # tech_verticals (1.5)
    "36氪":                ("tech_verticals", 1.5),
    "IT之家":              ("tech_verticals", 1.5),
    # lag_media (1.0)
    "微博热搜":            ("lag_media", 1.0),
    "新浪热榜":            ("lag_media", 1.0),
    "百度热搜":            ("lag_media", 1.0),
    "今日头条":            ("lag_media", 1.0),
    "腾讯新闻":            ("lag_media", 1.0),
    "网易新闻":            ("lag_media", 1.0),
    "澎湃新闻":            ("lag_media", 1.0),
    "微信热文":            ("lag_media", 1.0),
}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_latest():
    path = DATA_DIR / "latest.json"
    if not path.exists():
        return None
    return load_json(path)


def load_yesterday_snapshot():
    """加载昨天的快照"""
    yesterday = (datetime.now(CST) - timedelta(days=1)).strftime("%Y-%m-%d")
    path = SNAPSHOT_DIR / f"{yesterday}.json"
    if path.exists():
        return load_json(path)
    return None


def load_day_before_snapshot():
    """加载前天的快照（用于加速度计算）"""
    day_before = (datetime.now(CST) - timedelta(days=2)).strftime("%Y-%m-%d")
    path = SNAPSHOT_DIR / f"{day_before}.json"
    if path.exists():
        return load_json(path)
    return None


def count_snapshot_days():
    """统计已有快照天数，决定模式"""
    if not SNAPSHOT_DIR.exists():
        return 0
    return len(list(SNAPSHOT_DIR.glob("*.json")))


def extract_topic_data(latest_data):
    """从 latest.json 提取所有话题在各平台的提及数"""
    sources = latest_data.get("sources", {})
    all_items = []
    for key, src in sources.items():
        if src.get("status") != "ok":
            continue
        label = src.get("label", key)
        src_data = src.get("data", {})
        entries = src_data.get("list", []) if isinstance(src_data, dict) else []
        for i, item in enumerate(entries):
            if isinstance(item, dict):
                title = item.get("title") or item.get("word") or ""
                rank = i + 1
                if title:
                    all_items.append({"source": label, "title": title, "rank": rank})

    # 聚类
    all_patterns = {}
    all_patterns.update(SIGNAL_PATTERNS)
    all_patterns.update(SEASONAL_PATTERNS)
    all_patterns.update(ENTERTAINMENT_PATTERNS)

    topics = {}
    for sig_name, keywords in all_patterns.items():
        platforms = {}
        total_mentions = 0
        platform_set = set()
        sample_titles = []
        best_rank = 999

        for item in all_items:
            title_lower = item["title"].lower()
            matched = False
            for kw in keywords:
                if kw.lower() in title_lower:
                    matched = True
                    break
            if not matched:
                continue

            src = item["source"]
            platforms[src] = platforms.get(src, 0) + 1
            platform_set.add(src)
            total_mentions += 1
            if len(sample_titles) < 5:
                sample_titles.append(item["title"])
            if item["rank"] < best_rank:
                best_rank = item["rank"]

        if total_mentions > 0:
            is_seasonal = sig_name in SEASONAL_PATTERNS
            is_entertainment = sig_name in ENTERTAINMENT_PATTERNS
            is_signal = sig_name in SIGNAL_PATTERNS

            topics[sig_name] = {
                "total_mentions": total_mentions,
                "platform_count": len(platform_set),
                "platform_names": sorted(platform_set),
                "per_platform": platforms,
                "sample_titles": sample_titles[:3],
                "best_rank": best_rank,
                "is_seasonal": is_seasonal,
                "is_entertainment": is_entertainment,
                "is_signal": is_signal,
            }

    return topics, len(all_items)


def apply_noise_filter(topics, total_items):
    """噪音过滤器 + percentile_rank 门禁"""
    filtered = {}
    for name, t in topics.items():
        # 季节性 → 排除
        if t["is_seasonal"]:
            continue
        # 消遣 → 排除
        if t["is_entertainment"]:
            continue
        # 单平台且 total_mentions < 3 → 排除（单平台有增长才保留，由模式判断）
        if t["platform_count"] == 1 and t["total_mentions"] < 3:
            continue
        # percentile_rank 门禁：热度进全平台 top 10% 且 platform_count ≥ 5 → 排除
        rank_pct = (t["best_rank"] / max(total_items, 1)) * 100
        if rank_pct <= 10 and t["platform_count"] >= 5:
            # 已扩散至主流 → 信息差消失
            t["_excluded_reason"] = f"top {rank_pct:.0f}% · 已扩散"
            continue
        filtered[name] = t
    return filtered


def calc_growth_score(today_mentions, yesterday_mentions):
    """growth_score (0-100) · 24h 增长率，含平滑和门槛"""
    if today_mentions < 3 and yesterday_mentions < 2:
        return 0.0
    raw_rate = (today_mentions - yesterday_mentions) / max(yesterday_mentions, 1)
    score = math.log2(1 + raw_rate) * 25 if raw_rate > -0.5 else 0
    return clamp(score, 0, 100)


def calc_acceleration_score(today, yesterday, day_before):
    """acceleration_score (0-100) · 今日增速 vs 昨日增速"""
    yg = (yesterday - day_before) / max(day_before, 1)
    tg = (today - yesterday) / max(yesterday, 1)
    accel = tg - yg
    return clamp(50 + accel * 20, 0, 100)


def calc_multi_source_score(platform_names):
    """multi_source_score (0-100) · 平台加权求和后归一化"""
    if not platform_names:
        return 0.0
    weights = [PLATFORM_TIERS.get(p, ("unknown", 1.0))[1] for p in platform_names]
    raw = sum(weights)
    # 归一化：理论上限 ~3.0*2 + 2.5 + 2.0*5 + 1.5*5 + 1.0*10 ≈ 38
    return clamp(raw / 30.0 * 100, 0, 100)


def calc_novelty_score(days_since_first_seen):
    """novelty_score (0-100) · 首次出现天数"""
    if days_since_first_seen is None:
        return 50  # 冷启动估计值
    if days_since_first_seen <= 1:
        return 100
    elif days_since_first_seen <= 3:
        return 80
    elif days_since_first_seen <= 7:
        return 50
    elif days_since_first_seen <= 14:
        return 20
    return 0


def get_platform_tier(platform_names):
    """返回出现平台中最高权重的层级"""
    best_tier = "lag_media"
    best_weight = 0
    for p in platform_names:
        tier, w = PLATFORM_TIERS.get(p, ("unknown", 0.5))
        if w > best_weight:
            best_weight = w
            best_tier = tier
    return best_tier


def generate_signal_reason(name, growth, multi, novelty, platforms, is_new, percentile):
    """模板生成 signal_reason，≤80 字"""
    parts = []
    if growth > 50:
        pct = int((2 ** (growth / 25) - 1) * 100)
        parts.append(f"24h涨{pct}%")
    if len(platforms) >= 3:
        parts.append(f"跨{len(platforms)}平台共振")
    elif len(platforms) == 2:
        parts.append("双平台萌芽")
    if is_new:
        parts.append("首次出现")
    if novelty >= 80:
        parts.append("≤48h新话题")
    tier = get_platform_tier(platforms)
    if tier in ("early_social", "consumer_discussion"):
        parts.append("消费平台首发")
    # 判断是否未入主流
    has_mainstream = any(
        PLATFORM_TIERS.get(p, ("", 0))[1] <= 1.0 for p in platforms
    )
    if not has_mainstream and len(platforms) >= 2:
        parts.append("未入主流媒体")

    return " · ".join(parts[:4]) if parts else "跨平台检测"


def generate_why_appears(name, platforms, growth):
    """模板生成 why_this_appears，≤120 字"""
    tier = get_platform_tier(platforms)
    tier_labels = {
        "early_social": "海外社交平台",
        "search_trends": "搜索趋势",
        "consumer_discussion": "消费讨论社区",
        "general_content": "泛内容平台",
        "tech_verticals": "科技垂直媒体",
        "lag_media": "主流媒体",
    }
    tier_cn = tier_labels.get(tier, "多平台")
    trend_desc = "爆发式增长" if growth > 60 else "持续升温" if growth > 30 else "早期萌芽"
    source_names = ", ".join(platforms[:3])

    return f"{source_names} {name}相关讨论{trend_desc}"


def compute_tags(platforms, days_since_first_seen):
    """计算 tags · 仅 NEW 和 MULTI"""
    tags = []
    if days_since_first_seen is not None and days_since_first_seen <= 2:
        tags.append("NEW")
    if len(platforms) >= 2:
        tags.append("MULTI")
    return tags


def run_engine():
    """主引擎"""
    latest = load_latest()
    if not latest:
        print("[engine] latest.json 不存在")
        return None

    topics, total_items = extract_topic_data(latest)

    # 先跑一遍 snapshot recorder（确保冷启动时也有当天快照）
    print("[engine] 记录今日快照...")
    from snapshot_recorder import main as snapshot_main
    snapshot_main()

    # 确定模式
    snapshot_days = count_snapshot_days()
    yesterday = load_yesterday_snapshot()
    day_before = load_day_before_snapshot()

    if snapshot_days <= 1:
        mode = "cold_start"
    elif snapshot_days == 2:
        mode = "transition"
    else:
        mode = "normal"

    print(f"[engine] 模式: {mode} (快照 {snapshot_days} 天)")

    # 噪音过滤
    candidates = apply_noise_filter(topics, total_items)
    print(f"[engine] 候选池: {len(candidates)} 话题 (原始 {len(topics)})")

    # 打分
    scored = []
    for name, t in candidates.items():
        today_mentions = t["total_mentions"]
        yesterday_mentions = 0
        day_before_mentions = 0
        days_since = None

        if yesterday:
            yt = yesterday.get("topics", {}).get(name)
            if yt:
                yesterday_mentions = yt.get("total_mentions", 0)
                days_since = 1  # 至少 1 天前出现过
            else:
                days_since = 0  # 昨天没有，可能是新的
        else:
            days_since = None  # 冷启动

        if day_before:
            dbt = day_before.get("topics", {}).get(name)
            if dbt:
                day_before_mentions = dbt.get("total_mentions", 0)

        growth = calc_growth_score(today_mentions, yesterday_mentions)
        accel = calc_acceleration_score(today_mentions, yesterday_mentions, day_before_mentions)
        multi = calc_multi_source_score(t["platform_names"])
        novelty = calc_novelty_score(days_since)

        # ── 模式权重调整 ──
        if mode == "cold_start":
            final = multi * 0.60 + novelty * 0.40
            growth = 0  # 无历史数据
            accel = 0
        elif mode == "transition":
            final = growth * 0.50 + multi * 0.30 + novelty * 0.20
            accel = 0  # 需要 2 天历史
        else:  # normal
            final = growth * 0.40 + accel * 0.25 + multi * 0.20 + novelty * 0.15

        # early_bias
        if days_since is not None and days_since <= 2:
            final *= 1.2

        final = clamp(final, 0, 100)

        tags = compute_tags(t["platform_names"], days_since)
        signal_reason = generate_signal_reason(
            name, growth, multi, novelty,
            t["platform_names"], days_since == 0, 0
        )
        why = generate_why_appears(name, t["platform_names"], growth)

        scored.append({
            "title": name,
            "final_score": round(final, 1),
            "sub_scores": {
                "growth": round(growth, 1),
                "acceleration": round(accel, 1),
                "multi_source": round(multi, 1),
                "novelty": round(novelty, 1),
            },
            "percentile_rank": round((t["best_rank"] / max(total_items, 1)) * 100, 1),
            "first_seen_time": datetime.now(CST).isoformat() if days_since is None or days_since == 0 else None,
            "days_since_first_seen": days_since,
            "sources": t["platform_names"],
            "source_count": t["platform_count"],
            "platform_tier": get_platform_tier(t["platform_names"]),
            "tags": tags,
            "signal_reason": signal_reason,
            "why_this_appears": why,
            "raw_links": [],
            "sample_titles": t["sample_titles"],
        })

    # 排序 · Top 10
    scored.sort(key=lambda x: -x["final_score"])
    top10 = scored[:10]

    # 输出
    now = datetime.now(CST)
    output = {
        "generated_at": now.isoformat(),
        "mode": mode,
        "day_number": snapshot_days,
        "scan_summary": {
            "total_items": total_items,
            "total_topics": len(topics),
            "candidates_after_filter": len(candidates),
            "output_count": len(top10),
        },
        "signals": [],
    }

    for i, s in enumerate(top10):
        entry = {
            "rank": i + 1,
            "title": s["title"],
            "final_score": s["final_score"],
            "sub_scores": s["sub_scores"],
            "percentile_rank": s["percentile_rank"],
            "first_seen_time": s["first_seen_time"],
            "days_since_first_seen": s["days_since_first_seen"],
            "sources": s["sources"],
            "source_count": s["source_count"],
            "platform_tier": s["platform_tier"],
            "tags": s["tags"],
            "signal_reason": s["signal_reason"],
            "why_this_appears": s["why_this_appears"],
            "raw_links": s["raw_links"],
        }
        output["signals"].append(entry)

    # 写入
    engine_path = DATA_DIR / "top10_signals.json"
    engine_path.parent.mkdir(parents=True, exist_ok=True)
    with open(engine_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 同步到公开目录
    import shutil
    public_dir = ROOT / "data"
    public_dir.mkdir(exist_ok=True)
    shutil.copy2(engine_path, public_dir / "top10_signals.json")

    print(f"[engine] top10_signals.json · mode={mode} · {len(top10)} 条信号")
    for i, s in enumerate(top10[:5]):
        print(f"  #{i+1} {s['title']} · {s['final_score']}分 · {s['signal_reason']}")

    return output


def main():
    output = run_engine()
    if output is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
