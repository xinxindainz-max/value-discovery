#!/usr/bin/env python3
"""
card_updater.py — 机械卡片更新器 v1.0
在 GitHub Actions 中运行，自动刷新卡片元数据和信号扫描区。
纯规则驱动，不需要 AI。

功能：
1. 从 latest.json 读取所有热词
2. 按关键词聚类，检测跨平台共振
3. 更新 HTML 中"今日信号扫描"区（新信号摘要）
4. 更新"数据概览"区的热榜摘要
5. 新鲜度自检：对比今日数据与昨日快照
"""
import json
import re
import hashlib
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / ".workbuddy" / "pipeline" / "data"
HTML_PATH = ROOT / "发现榜.html"


# ── 关键词聚类字典 ──
# keyword → [platform_count, platforms, sample_titles]
# 在 latest.json 的所有热词中搜索这些关键词
SIGNAL_PATTERNS = {
    # 科技/半导体
    "芯片": ["芯片", "半导体", "存储", "NAND", "DRAM", "HBM"],
    "AI/大模型": ["AI", "大模型", "GPT", "LLM", "人工智能", "DeepSeek"],
    "机器人": ["机器人", "人形", "宇树", "Figure", "Optimus"],
    # 消费/零售
    "空调/家电": ["空调", "格力", "美的", "海尔", "家电"],
    "手机/消费电子": ["手机", "iPhone", "华为", "小米", "折叠"],
    # 金融/大宗
    "黄金/贵金属": ["黄金", "金价", "贵金属", "Gold"],
    "原油/能源": ["原油", "油价", "石油", "能源"],
    # 汽车
    "新能源车": ["电动车", "新能源", "比亚迪", "蔚来", "理想", "宁德", "TSLA", "特斯拉"],
    # 宏观
    "关税/贸易": ["关税", "贸易", "出口管制", "制裁"],
    "降息/利率": ["降息", "利率", "Fed", "央行", "PBOC"],
    # 季节性
    "高考": ["高考", "志愿"],
    "618/促销": ["618", "促销", "大促"],
    # 娱乐/消遣（无投资信号，仅标记）
    "足球": ["世界杯", "足球", "英超", "欧冠"],
    "游戏": ["游戏", "原神", "王者", "黑神话"],
}

# 消遣类话题（不产生投资信号）
ENTERTAINMENT_KEYWORDS = {"足球", "游戏"}

# 季节性话题（标"非信息差"）
SEASONAL_KEYWORDS = {"高考", "618/促销"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def scan_signals(latest_path):
    """扫描 latest.json，检测跨平台共振信号"""
    data = load_json(latest_path)
    sources = data.get("sources", {})

    # 收集所有热词标题
    all_titles = []  # [(platform_label, position, title), ...]
    for key, src in sources.items():
        if src.get("status") != "ok":
            continue
        label = src.get("label", key)
        src_data = src.get("data", {})
        items = src_data.get("list", []) if isinstance(src_data, dict) else []

        for item in items:
            if isinstance(item, dict):
                title = item.get("title") or item.get("word") or ""
                pos = item.get("index") or item.get("rank") or 0
                if title:
                    all_titles.append((label, pos, title[:100]))

    # 按 SIGNAL_PATTERNS 聚类
    signals = {}
    for sig_name, keywords in SIGNAL_PATTERNS.items():
        matches = []
        seen_platforms = set()
        for platform, pos, title in all_titles:
            title_lower = title.lower()
            for kw in keywords:
                if kw.lower() in title_lower:
                    matches.append((platform, pos, title))
                    seen_platforms.add(platform)
                    break

        if matches:
            sorted_matches = sorted(matches, key=lambda x: x[1] if x[1] else 999)

            # 取 Top3 标题示例
            sample_titles = [m[2] for m in sorted_matches[:5]]

            signals[sig_name] = {
                "platform_count": len(seen_platforms),
                "total_mentions": len(matches),
                "platforms": sorted(seen_platforms),
                "top_positions": f"{sorted_matches[0][0]}#{sorted_matches[0][1]}" if sorted_matches else "",
                "sample": sample_titles[:3],
                "is_seasonal": sig_name in SEASONAL_KEYWORDS,
                "is_entertainment": sig_name in ENTERTAINMENT_KEYWORDS,
                "category": (
                    "消遣" if sig_name in ENTERTAINMENT_KEYWORDS
                    else "季节性" if sig_name in SEASONAL_KEYWORDS
                    else "潜在信号"
                ),
            }

    # 按跨平台数排序
    ranked = sorted(signals.items(), key=lambda x: -x[1]["platform_count"])
    return ranked, len(all_titles), sources


def compute_content_hash(html_text):
    """计算 HTML 中卡片内容区的哈希（排除时间戳和价格）"""
    # 移除时间戳行、价格数字
    cleaned = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', 'TIMESTAMP', html_text)
    cleaned = re.sub(r'¥[\d,]+\.\d+', 'PRICE', cleaned)
    cleaned = re.sub(r'PE:[\d.-]+', 'PE:VAL', cleaned)
    return hashlib.sha256(cleaned.encode()).hexdigest()


def update_html(html_path, signals_data, total_titles, source_summary):
    """更新 HTML 中的信号扫描区和数据概览"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    now = datetime.now(CST)
    ts_str = now.strftime("%Y-%m-%d %H:%M")
    date_str = now.strftime("%Y-%m-%d")

    # 1. 更新页面时间戳
    html = re.sub(
        r'<div class="ts">[^<]*</div>',
        f'<div class="ts">数据刷新：{ts_str} CST · 自动化管道（GitHub Actions）· 下次刷新 10:00</div>',
        html,
        count=1,
    )

    # 2. 生成信号扫描 HTML
    scan_html = generate_scan_html(signals_data, total_titles, ts_str)

    # 3. 替换或插入信号扫描区
    scan_marker = '<!-- ══════════════════ 信号扫描 · 自动生成 ══════════════════ -->'
    scan_pattern = re.compile(
        r'<!-- ═+ 信号扫描 · 自动生成 ═+ -->.*?(?=<!-- ═+ ZONE 1)',
        re.DOTALL,
    )

    if scan_pattern.search(html):
        html = scan_pattern.sub(scan_marker + "\n" + scan_html + "\n\n", html, count=1)
    else:
        # 在 ZONE 1 之前插入
        zone1_marker = '<!-- ══════════════════ ZONE 1'
        if zone1_marker in html:
            html = html.replace(
                zone1_marker,
                scan_marker + "\n" + scan_html + "\n\n" + zone1_marker,
                1,
            )
        else:
            # 在 sparse note 之后插入
            sparse_pos = html.rfind('</div>\n\n<!-- ═')
            if sparse_pos > 0:
                insert_pos = html.index('\n', sparse_pos) + 1
                html = (html[:insert_pos]
                        + scan_marker + "\n" + scan_html + "\n\n"
                        + html[insert_pos:])

    # 4. 更新内容哈希（用于后续新鲜度检测）
    content_hash = compute_content_hash(html)
    hash_file = DATA_DIR / ".content_hash.txt"
    hash_file.parent.mkdir(parents=True, exist_ok=True)

    old_hash = ""
    if hash_file.exists():
        old_hash = hash_file.read_text().strip()

    with open(hash_file, "w") as f:
        f.write(content_hash)

    # 5. 写入 HTML
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 返回新鲜度信息
    is_fresh = old_hash != content_hash
    return is_fresh, old_hash, content_hash


def generate_scan_html(signals_data, total_titles, ts_str):
    """生成信号扫描区 HTML"""
    lines = []

    # 分类统计
    potential = [(n, s) for n, s in signals_data if s["category"] == "潜在信号"]
    seasonal = [(n, s) for n, s in signals_data if s["category"] == "季节性"]
    entertainment = [(n, s) for n, s in signals_data if s["category"] == "消遣"]

    lines.append('<div class="scan-section" style="margin:12px 0;padding:14px 18px;'
                 'background:#faf9f6;border:1px solid var(--border);'
                 'border-radius:var(--radius);font-size:13px">')
    lines.append(f'<div style="font-size:14px;font-weight:700;margin-bottom:8px;'
                 f'color:var(--tx)">'
                 f'今日信号扫描 · {ts_str}</div>')
    lines.append(f'<div style="font-size:12px;color:var(--tx3);margin-bottom:10px">'
                 f'全平台热词总数 {total_titles} · '
                 f'跨平台信号 {len(potential)} 组 · '
                 f'季节性 {len(seasonal)} 组 · '
                 f'消遣 {len(entertainment)} 组'
                 f'</div>')

    # 潜在信号
    if potential:
        lines.append('<div style="font-weight:600;font-size:13px;margin:8px 0 4px;'
                     'color:var(--accent)">'
                     '潜在信号</div>')
        lines.append('<div style="display:flex;flex-direction:column;gap:4px">')
        for name, sig in potential:
            pc = sig["platform_count"]
            # 扩散度图标
            if pc >= 3:
                diff = "●●●"
                diff_label = "已扩散"
            elif pc >= 2:
                diff = "●●○"
                diff_label = "扩散中"
            else:
                diff = "●○○"
                diff_label = "早期"

            heat_class = "heat-burst" if pc >= 3 else ("heat-rising" if pc >= 2 else "heat-steady")

            lines.append(
                f'<div style="padding:6px 10px;background:#fff;border-radius:4px;'
                f'border-left:3px solid var(--accent);display:flex;'
                f'align-items:center;gap:8px;flex-wrap:wrap">'
                f'<span style="font-weight:600;min-width:70px">{name}</span>'
                f'<span style="font-size:11px;color:var(--tx3)">'
                f'扩散度 {diff} {diff_label}</span>'
                f'<span class="{heat_class}" style="font-size:11px">'
                f'{pc}平台 · {sig["total_mentions"]}条</span>'
                f'<span style="font-size:11px;color:var(--tx2)">'
                f'Top: {sig["top_positions"]}</span>'
                f'<span style="font-size:11px;color:var(--tx3);flex-basis:100%">'
                f'{"; ".join(sig["sample"][:2])}</span>'
                f'</div>'
            )
        lines.append('</div>')

    # 季节性
    if seasonal:
        lines.append('<div style="font-weight:600;font-size:13px;margin:10px 0 4px;'
                     'color:#c0a050">'
                     '季节性提醒 · 非信息差</div>')
        for name, sig in seasonal:
            lines.append(
                f'<div style="padding:3px 10px;font-size:12px;color:var(--tx2)">'
                f'{name} · {sig["platform_count"]}平台 · '
                f'{"; ".join(sig["sample"][:2])}'
                f'</div>'
            )

    # 消遣
    if entertainment and len(entertainment) > 0:
        lines.append('<details style="margin-top:6px"><summary style="font-size:12px;'
                     'color:var(--tx3);cursor:pointer">消遣资讯（'
                     f'{len(entertainment)} 组 · 无投资信号）</summary>')
        for name, sig in entertainment:
            lines.append(
                f'<div style="padding:2px 10px;font-size:11px;color:var(--tx3)">'
                f'{name} · {sig["platform_count"]}平台 · '
                f'{"; ".join(sig["sample"][:2])}'
                f'</div>'
            )
        lines.append('</details>')

    lines.append('</div>')
    return '\n'.join(lines)


def main():
    latest_path = DATA_DIR / "latest.json"

    if not latest_path.exists():
        print("[card_updater] latest.json 不存在，跳过")
        return 0

    print("[card_updater] 扫描热词信号...")
    signals, total_titles, sources = scan_signals(latest_path)

    # 统计各源
    ok_count = sum(1 for s in sources.values() if s.get("status") == "ok")
    total_sources = len(sources)

    print(f"[card_updater] 热词总数: {total_titles} · 源: {ok_count}/{total_sources}")

    # 生成源摘要
    source_summary = {}
    for key, src in sources.items():
        label = src.get("label", key)
        status = src.get("status", "fail")
        source_summary[label] = status

    # 打印 Top 5 信号
    print("[card_updater] 跨平台信号:")
    for name, sig in signals[:10]:
        cat = sig["category"]
        pc = sig["platform_count"]
        tm = sig["total_mentions"]
        top = sig["top_positions"]
        print(f"  [{cat}] {name} · {pc}平台/{tm}条 · Top: {top}")

    # 更新 HTML
    print("[card_updater] 更新 HTML...")
    is_fresh, old_hash, new_hash = content_update = update_html(
        HTML_PATH, signals, total_titles, source_summary
    )

    # 输出新鲜度
    if is_fresh:
        print("[card_updater] OK - content updated (signal change)")
    else:
        print("[card_updater] WARN - no content change (same as last scan)")

    # 输出 JSON 供 workflow 使用
    report = {
        "scan_time": datetime.now(CST).isoformat(),
        "total_titles": total_titles,
        "sources_ok": ok_count,
        "sources_total": total_sources,
        "signals_top5": [
            {"name": n, "platform_count": s["platform_count"],
             "category": s["category"], "top": s["top_positions"]}
            for n, s in signals[:5]
        ],
        "fresh": is_fresh,
    }
    report_path = DATA_DIR / "signal_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[card_updater] 报告已保存: {report_path}")
    return 0 if is_fresh else 1


if __name__ == "__main__":
    sys.exit(main())
