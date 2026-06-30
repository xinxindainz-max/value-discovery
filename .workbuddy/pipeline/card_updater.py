#!/usr/bin/env python3
"""
card_updater.py v2.0 — 自动快讯引擎
在 GitHub Actions 中运行，自动识别热点信号并生成推送摘要。
纯规则驱动，不需要 AI，不需要 WorkBuddy。

功能：
1. 从 latest.json 读取全平台热词
2. 按关键词聚类，检测跨平台共振
3. 行业映射 → 候选股票提示
4. 趋势检测：对比上次扫描，判断新信号/增长/稳定/衰退
5. 输出 HTML"自动快讯"区 + signal_report.json
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

# 消遣类 → 无投资信号
ENTERTAINMENT = {"足球", "游戏"}
# 季节性 → 非信息差
SEASONAL = {"高考", "618/促销"}

# ── 行业 → 候选股票映射（静态，仅作提示）──
# 格式: (代码, 名称, 市场, 一句话关联逻辑)
INDUSTRY_STOCKS = {
    "空调/家电": [
        ("sz000651", "格力电器", "A股", "空调龙头·欧洲出口增量"),
        ("sz000333", "美的集团", "A股", "家电龙头·海外占20%"),
        ("sh600690", "海尔智家", "A港股通", "海外营收占比52%"),
    ],
    "AI/大模型": [
        ("sz002230", "科大讯飞", "A股", "星火大模型"),
        ("hk9888", "百度", "港股通", "文心大模型"),
        ("sh688256", "寒武纪", "A股", "AI芯片"),
    ],
    "芯片/半导体": [
        ("hk0981", "中芯国际", "港股通", "晶圆代工龙头"),
        ("sz002371", "北方华创", "A股", "半导体设备"),
        ("sh603501", "韦尔股份", "A股", "CIS芯片"),
    ],
    "机器人": [
        ("sz300124", "汇川技术", "A股", "伺服电机·机器人关节"),
        ("sh688017", "绿的谐波", "A股", "谐波减速器"),
        ("sz002747", "埃斯顿", "A股", "工业机器人"),
    ],
    "新能源车": [
        ("sz002594", "比亚迪", "A港股通", "新能源车龙头"),
        ("sz300750", "宁德时代", "A股", "动力电池龙头"),
    ],
    "黄金/贵金属": [
        ("sh601899", "紫金矿业", "A港股通", "金铜龙头"),
        ("sh600547", "山东黄金", "A港股通", "纯黄金标的"),
    ],
    "手机/消费电子": [
        ("sz002475", "立讯精密", "A股", "苹果链龙头"),
        ("sz002241", "歌尔股份", "A股", "VR/声学"),
    ],
    "原油/能源": [
        ("sh601857", "中国石油", "A股", "上游开采"),
        ("sh600938", "中国海油", "A股", "海上油气"),
    ],
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def scan_signals(latest_path):
    """扫描 latest.json，检测跨平台共振信号"""
    data = load_json(latest_path)
    sources = data.get("sources", {})

    all_titles = []
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
            sample_titles = [m[2] for m in sorted_matches[:5]]
            signals[sig_name] = {
                "platform_count": len(seen_platforms),
                "total_mentions": len(matches),
                "platforms": sorted(seen_platforms),
                "top_positions": f"{sorted_matches[0][0]}#{sorted_matches[0][1]}" if sorted_matches else "",
                "sample": sample_titles[:3],
                "is_seasonal": sig_name in SEASONAL,
                "is_entertainment": sig_name in ENTERTAINMENT,
                "category": (
                    "消遣" if sig_name in ENTERTAINMENT
                    else "季节性" if sig_name in SEASONAL
                    else "潜在信号"
                ),
                "stocks": INDUSTRY_STOCKS.get(sig_name, []),
            }

    ranked = sorted(signals.items(), key=lambda x: -x[1]["platform_count"])
    return ranked, len(all_titles)


def detect_trends(signals_data):
    """对比上次扫描，检测趋势：新信号/增长/稳定/衰退"""
    prev_path = DATA_DIR / ".prev_signals.json"
    prev_signals = {}
    if prev_path.exists():
        prev_signals = load_json(prev_path)

    trends = {}
    now_signals = {name: sig for name, sig in signals_data
                   if sig["category"] == "潜在信号"}

    # 保存当前扫描供下次对比
    slim = {name: {
        "platform_count": sig["platform_count"],
        "total_mentions": sig["total_mentions"],
        "top_positions": sig["top_positions"],
    } for name, sig in signals_data}
    with open(prev_path, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)

    for name, sig in now_signals.items():
        prev = prev_signals.get(name)
        if not prev:
            trends[name] = ("new", "新增异动")
        else:
            old_pc = prev.get("platform_count", 0)
            new_pc = sig["platform_count"]
            if new_pc > old_pc + 1:
                trends[name] = ("up", f"平台 +{new_pc - old_pc} · 加速扩散")
            elif new_pc > old_pc:
                trends[name] = ("up", f"平台 +{new_pc - old_pc}")
            elif new_pc == old_pc:
                trends[name] = ("stable", "持平")
            else:
                trends[name] = ("down", f"平台 -{old_pc - new_pc}")

    return trends


def compute_content_hash(html_text):
    cleaned = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', 'TS', html_text)
    cleaned = re.sub(r'¥[\d,]+\.\d+', 'PRICE', cleaned)
    cleaned = re.sub(r'PE:[\d.-]+', 'PE:VAL', cleaned)
    return hashlib.sha256(cleaned.encode()).hexdigest()


def generate_flash_html(signals_data, total_titles, trends, ts_str):
    """生成自动快讯 HTML — 更像新闻推送"""
    lines = []
    potential = [(n, s) for n, s in signals_data if s["category"] == "潜在信号"]
    seasonal = [(n, s) for n, s in signals_data if s["category"] == "季节性"]
    entertainment = [(n, s) for n, s in signals_data if s["category"] == "消遣"]
    total_platforms = max((s["platform_count"] for _, s in potential), default=0)

    # ── Section header ──
    lines.append('<div class="flash-section" style="margin:10px 0 16px;'
                 'padding:16px 20px;background:linear-gradient(135deg,#f9fafb,#f0f4f8);'
                 'border:1px solid #dfe6e9;border-radius:var(--radius);'
                 'font-size:13px;line-height:1.6">')

    # 标题行
    lines.append('<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">')
    lines.append('<span style="font-size:15px;font-weight:700;color:var(--tx)">'
                 '自动快讯</span>')
    lines.append(f'<span style="font-size:11px;color:var(--tx3);font-weight:400">'
                 f'{ts_str} CST · 全自动采集 · 本次扫描 {total_titles} 条热词</span>')
    lines.append(f'<span style="font-size:11px;color:var(--accent);margin-left:auto">'
                 f'{len(potential)} 组跨平台信号</span>')
    lines.append('</div>')

    # 分类条
    lines.append('<div style="font-size:11px;color:var(--tx3);margin-bottom:12px;'
                 'display:flex;gap:14px;flex-wrap:wrap">')
    for name, sig in potential[:5]:
        trend = trends.get(name, ("stable", ""))
        trend_icon = {"new": "+", "up": "↑", "stable": "→", "down": "↓"}.get(trend[0], "")
        trend_color = {"new": "#c0392b", "up": "#c0392b", "stable": "#636e72",
                       "down": "#1a7a3a"}.get(trend[0], "#636e72")
        lines.append(f'<span style="color:{trend_color}">'
                     f'{trend_icon} {name} · {sig["platform_count"]}平台'
                     f'</span>')
    lines.append('</div>')

    # ── 各信号卡片 ──
    if not potential:
        lines.append('<div style="padding:20px;text-align:center;color:var(--tx3)">'
                     '本次扫描未检测到跨平台消费信号 · 异动稀疏是正常的</div>')
    else:
        for name, sig in potential[:8]:
            pc = sig["platform_count"]
            tm = sig["total_mentions"]
            trend = trends.get(name, ("stable", ""))
            trend_label = trend[1] if trend else ""

            # 热度级别
            if pc >= 6:
                heat_icon, heat_label = "●", "全平台共振"
            elif pc >= 3:
                heat_icon, heat_label = "●", "多平台扩散"
            elif pc >= 2:
                heat_icon, heat_label = "◉", "双平台萌芽"
            else:
                heat_icon, heat_label = "○", "单平台早期"

            # 趋势颜色
            tc = {"new": "#c0392b", "up": "#c0392b", "stable": "#636e72",
                  "down": "#1a7a3a"}.get(trend[0], "#636e72")

            # 候选股票
            stocks = sig.get("stocks", [])
            stock_str = " · ".join(
                f'{s[1]} {s[2]}' for s in stocks[:3]
            ) if stocks else "待分析映射"

            lines.append(
                f'<div style="padding:10px 14px;margin:6px 0;'
                f'background:#fff;border-radius:6px;'
                f'border-left:3px solid {tc};'
                f'box-shadow:0 1px 3px rgba(0,0,0,.04)">'
                # 第一行：信号名 + 热度 + 趋势
                f'<div style="display:flex;align-items:center;gap:8px;'
                f'flex-wrap:wrap;margin-bottom:4px">'
                f'<span style="font-weight:700;font-size:14px;color:var(--tx)">{name}</span>'
                f'<span style="font-size:11px;padding:1px 6px;border-radius:3px;'
                f'background:{tc}15;color:{tc};font-weight:600">{trend_label if trend_label else heat_label}</span>'
                f'<span style="font-size:11px;color:var(--tx3)">'
                f'{pc}平台 · {tm}条 · Top: {sig["top_positions"]}</span>'
                f'</div>'
                # 第二行：平台
                f'<div style="font-size:11px;color:var(--tx3);margin-bottom:3px">'
                f'平台: {", ".join(sig["platforms"][:6])}'
                f'{" +" + str(len(sig["platforms"]) - 6) + "更多" if len(sig["platforms"]) > 6 else ""}'
                f'</div>'
                # 第三行：标题样本
                f'<div style="font-size:12px;color:var(--tx2);margin-bottom:4px;'
                f'max-height:36px;overflow:hidden">'
                f'{"; ".join(sig["sample"][:3])[:200]}'
                f'</div>'
                # 第四行：候选股票
                f'<div style="font-size:11px;color:var(--tx3)">'
                f'候选: {stock_str}'
                f'</div>'
                f'</div>'
            )

    # ── 季节性 ──
    if seasonal:
        lines.append('<div style="margin-top:10px;padding:8px 12px;'
                     'background:#fef9e7;border-radius:4px;font-size:12px">'
                     '<span style="color:#c0a050;font-weight:600">'
                     '季节性提醒 · 非信息差</span> · '
                     + ' · '.join(f'{n} ({s["platform_count"]}平台)' for n, s in seasonal)
                     + '</div>')

    # ── 消遣折叠 ──
    if entertainment:
        lines.append('<details style="margin-top:4px;font-size:11px;color:var(--tx3)">'
                     f'<summary style="cursor:pointer">消遣资讯 '
                     f'· {len(entertainment)} 组 · 无投资信号</summary>')
        for name, sig in entertainment:
            lines.append(f'<span style="margin-left:12px">{name} '
                         f'{sig["platform_count"]}平台</span> · ')
        lines.append('</details>')

    # ── 底部说明 ──
    lines.append('<div style="margin-top:12px;padding-top:8px;border-top:1px solid #dfe6e9;'
                 'font-size:11px;color:var(--tx3)">'
                 '以上为规则引擎自动扫描结果，候选股票为静态映射仅供提示。'
                 '深度投资分析请使用 WorkBuddy 说"今天有什么新信号"。'
                 '</div>')

    lines.append('</div>')
    return '\n'.join(lines)


def update_html(html_path, signals_data, total_titles, trends, ts_str):
    """更新 HTML 中的自动快讯区"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 更新时间戳
    html = re.sub(
        r'<div class="ts">[^<]*</div>',
        f'<div class="ts">数据刷新：{ts_str} CST · 自动化管道 · GitHub Actions</div>',
        html, count=1,
    )

    # 2. 生成快讯 HTML
    flash_html = generate_flash_html(signals_data, total_titles, trends, ts_str)

    # 3. 替换信号扫描区
    marker = '<!-- ══════════════════ 信号扫描 · 自动生成 ══════════════════ -->'
    scan_pattern = re.compile(
        r'<!-- ═+ 信号扫描 · 自动生成 ═+ -->.*?(?=<!-- ═+ ZONE 1)',
        re.DOTALL,
    )

    if scan_pattern.search(html):
        html = scan_pattern.sub(marker + "\n" + flash_html + "\n\n", html, count=1)
    else:
        zone1 = '<!-- ══════════════════ ZONE 1'
        if zone1 in html:
            html = html.replace(zone1, marker + "\n" + flash_html + "\n\n" + zone1, 1)

    # 4. 内容哈希
    content_hash = compute_content_hash(html)
    hash_file = DATA_DIR / ".content_hash.txt"
    old_hash = hash_file.read_text().strip() if hash_file.exists() else ""
    hash_file.write_text(content_hash)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    is_fresh = old_hash != content_hash
    return is_fresh


def main():
    latest_path = DATA_DIR / "latest.json"
    if not latest_path.exists():
        print("[flash] latest.json 不存在，跳过")
        return 0

    print("[flash] 扫描热词信号...")
    signals, total_titles = scan_signals(latest_path)

    # 分类统计
    potential = [(n, s) for n, s in signals if s["category"] == "潜在信号"]
    seasonal = [(n, s) for n, s in signals if s["category"] == "季节性"]
    entertainment = [(n, s) for n, s in signals if s["category"] == "消遣"]

    # 趋势检测
    trends = detect_trends(signals)

    # 源统计
    data = load_json(latest_path)
    sources = data.get("sources", {})
    ok_count = sum(1 for s in sources.values() if s.get("status") == "ok")

    print(f"[flash] 热词 {total_titles} · 信号 {len(potential)} ({len(seasonal)}季/{len(entertainment)}娱)")
    for name, sig in potential[:5]:
        t = trends.get(name, ("stable", ""))
        print(f"  {t[0]:>6} {name} · {sig['platform_count']}平台/{sig['total_mentions']}条")

    # 更新 HTML
    now = datetime.now(CST)
    ts_str = now.strftime("%m-%d %H:%M")
    is_fresh = update_html(HTML_PATH, signals, total_titles, trends, ts_str)

    status = "OK" if is_fresh else "WARN (no change)"
    print(f"[flash] HTML updated · {status}")

    # 输出报告
    report = {
        "scan_time": now.isoformat(),
        "total_titles": total_titles,
        "sources_ok": ok_count,
        "sources_total": len(sources),
        "signals": [
            {"name": n, "platform_count": s["platform_count"],
             "category": s["category"],
             "trend": trends.get(n, ("stable", ""))[0],
             "top": s["top_positions"],
             "stocks": [list(ss[:2]) for ss in s.get("stocks", [])]}
            for n, s in signals[:10]
        ],
    }
    report_path = DATA_DIR / "signal_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[flash] 报告: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
