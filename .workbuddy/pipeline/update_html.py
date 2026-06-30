#!/usr/bin/env python3
"""
价值发现 · HTML更新器 v2.0
服务端自动更新：读取现有HTML，替换时间戳、股票价格、数据源状态。
不做分析，只做机械数据替换。保持CSS和布局不变。
v2.0: 接入source_registry进行标签验证，检测未对齐标签。
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

# GitHub Actions 环境强制 UTF-8
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 加载源标签注册表
try:
    from source_registry import ALL_LABELS, LABEL_TO_ID, validate_html_labels
except ImportError:
    # GitHub Actions 环境兼容
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from source_registry import ALL_LABELS, LABEL_TO_ID, validate_html_labels

CST = timezone(timedelta(hours=8))
# 从 .workbuddy/pipeline/update_html.py 向上三级到项目根
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HTML_SOURCE = os.path.join(PROJECT_DIR, "发现榜.html")
HTML_DEPLOY = os.path.join(PROJECT_DIR, "index.html")  # GitHub Pages入口
DATA_DIR = os.path.join(PROJECT_DIR, ".workbuddy", "pipeline", "data")


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_timestamp(html):
    """更新页面时间戳"""
    now = datetime.now(CST)
    ts_str = now.strftime("%Y-%m-%d %H:%M CST")

    # 替换头部时间戳
    html = re.sub(
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+CST)',
        ts_str,
        html
    )
    print(f"[✓] 时间戳更新: {ts_str}")
    return html


def update_source_bar(html, latest_data):
    """更新数据源状态栏"""
    if not latest_data or "sources" not in latest_data:
        print("[!] 无数据源信息，跳过状态栏更新")
        return html

    sources = latest_data["sources"]

    # 查找并替换每个 src-tag
    def replace_tag(match):
        full_tag = match.group(0)
        label_match = re.search(r'>(.+?)<', full_tag)
        if not label_match:
            return full_tag
        label = label_match.group(1).strip()

        # 精确匹配
        for key, src in sources.items():
            if src["label"] == label:
                if src["status"] == "ok":
                    return full_tag.replace("src-fail", "src-ok")
                else:
                    return full_tag.replace("src-ok", "src-fail")

        # 模糊匹配：HTML标签是管道标签的子串 或 管道标签是HTML标签的子串
        for key, src in sources.items():
            plabel = src["label"]
            if label in plabel or plabel in label:
                if src["status"] == "ok":
                    return full_tag.replace("src-fail", "src-ok")
                else:
                    return full_tag.replace("src-ok", "src-fail")

        return full_tag

    html = re.sub(r'<span class="src-tag[^"]*"[^>]*>.*?</span>', replace_tag, html)
    print(f"[✓] 数据源状态栏已更新")
    return html


def update_stock_prices(html, stocks_data):
    """更新HTML中的股票价格和PE"""
    if not stocks_data or "stocks" not in stocks_data:
        print("[!] 无股票数据，跳过价格更新")
        return html

    stocks = stocks_data["stocks"]

    for code, s in stocks.items():
        if not s.get("price"):
            continue

        name = s["name"]
        price = s["price"]
        pe = s.get("pe_ratio")
        pb = s.get("pb_ratio")
        chg = s.get("change_pct")

        # 在HTML中查找并更新这家公司的数据
        # 策略：在包含公司名的区域附近，更新价格、PE、PB等数字

        # 更新PE数字 (格式: PE 13.31 或 PE:13.31)
        if pe:
            # 匹配 PE后跟数字的模式
            pe_pattern = re.compile(
                rf'({re.escape(name)}.*?)(PE[：:\s]*)\d+\.?\d*',
                re.DOTALL
            )
            html = pe_pattern.sub(
                lambda m: m.group(1) + m.group(2) + f"{pe:.2f}",
                html
            )

        # 更新PB (如果有)
        if pb:
            pb_pattern = re.compile(
                rf'({re.escape(name)}.*?)(PB[：:\s]*)\d+\.?\d*',
                re.DOTALL
            )
            html = pb_pattern.sub(
                lambda m: m.group(1) + m.group(2) + f"{pb:.2f}",
                html
            )

    print(f"[✓] 股票价格已更新 ({len(stocks)} 只)")
    return html


def update_data_source_count(html, latest_data):
    """更新数据源计数显示"""
    if not latest_data:
        return html

    ok_count = latest_data.get("summary", {}).get("ok", 0)
    total = latest_data.get("summary", {}).get("total", 0)

    # 更新 "X/Y 可用" 这样的文本
    html = re.sub(
        r'\d+/\d+\s*(个数据源可用|可用|源可用)',
        f'{ok_count}/{total} 源可用',
        html
    )
    return html


def main():
    print("价值发现 · HTML更新器 v1.0")
    print(f"时间: {datetime.now(CST).isoformat()}")

    if not os.path.exists(HTML_SOURCE):
        print(f"[FATAL] HTML文件不存在: {HTML_SOURCE}")
        return 1

    with open(HTML_SOURCE, "r", encoding="utf-8") as f:
        html = f.read()

    original_len = len(html)

    # 1. 更新时间戳
    html = update_timestamp(html)

    # 2. 更新数据源状态
    latest = load_json(os.path.join(DATA_DIR, "latest.json"))
    if latest:
        # 检测HTML中未在registry注册的标签
        html_labels = set(re.findall(r'class="src-tag[^"]*"[^>]*>([^<]+)</span>', html))
        matched, unmatched = validate_html_labels(html_labels)
        if unmatched:
            print(f"[!] HTML存在未注册标签: {unmatched}")
            print(f"    请在 source_registry.py 中注册或修正HTML标签")

        html = update_source_bar(html, latest)
        html = update_data_source_count(html, latest)

    # 3. 更新股票价格
    stocks = load_json(os.path.join(DATA_DIR, "stocks.json"))
    if stocks:
        html = update_stock_prices(html, stocks)

    # 保存 — 同时写入 index.html (GitHub Pages入口) 和 发现榜.html
    for path in [HTML_SOURCE, HTML_DEPLOY]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[✓] 已保存 {os.path.basename(path)}")


if __name__ == "__main__":
    sys.exit(main())
