#!/usr/bin/env python3
"""
价值发现 · 运行后验证 v1.0
每次管道运行后的最后一道工序。验证所有输出完整性，发现异常时自动标注。
退出码: 0=全部正常, 1=有异常但不阻断, 2=致命异常
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
import json
import re
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(PIPELINE_DIR))
DATA_DIR = os.path.join(PIPELINE_DIR, "data")

OK = "  [OK]"
WARN = "  [WARN]"
FAIL = "  [FAIL]"


def main():
    print("=" * 50)
    print("价值发现 · 运行后验证 v1.0")
    print(f"时间: {datetime.now(CST).isoformat()}")
    print("=" * 50)

    anomalies = 0
    fatals = 0

    # ================================================================
    # 1. 验证 JSON 数据文件
    # ================================================================
    print("\n[1/4] 数据文件完整性")

    # latest.json — 热榜数据
    latest_path = os.path.join(DATA_DIR, "latest.json")
    if os.path.exists(latest_path):
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                latest = json.load(f)
            ok_count = latest.get("summary", {}).get("ok", 0)
            total = latest.get("summary", {}).get("total", 0)
            fail_count = latest.get("summary", {}).get("fail", 0)
            timeout_count = latest.get("summary", {}).get("timeout", 0)
            ok_pct = ok_count / total * 100 if total > 0 else 0

            if ok_pct >= 80:
                print(f"{OK} latest.json — {ok_count}/{total} 源正常 ({ok_pct:.0f}%)")
            elif ok_pct >= 50:
                print(f"{WARN} latest.json — {ok_count}/{total} 源正常 ({ok_pct:.0f}%) · 低于80%")
                anomalies += 1
            else:
                print(f"{FAIL} latest.json — {ok_count}/{total} 源正常 ({ok_pct:.0f}%) · 大面积失败")
                fatals += 1

            # 检测 API Key 失效信号
            trendsmcp_keys = [k for k in latest.get("sources", {})
                             if "trendsmcp" in k.lower() or k == "google_trends"]
            all_tmcp_fail = all(
                latest["sources"][k].get("status") != "ok"
                for k in trendsmcp_keys
            ) if trendsmcp_keys else False

            if all_tmcp_fail and trendsmcp_keys:
                # 检查是否是 HTTP 401/403 导致
                for k in trendsmcp_keys:
                    err = latest["sources"][k].get("error", "")
                    if "401" in err or "403" in err or "UNAUTHORIZED" in err.upper():
                        print(f"{WARN} TrendsMCP Key 可能已过期 ({k})")
                        anomalies += 1
                        break

        except json.JSONDecodeError as e:
            print(f"{FAIL} latest.json 损坏: {e}")
            fatals += 1
    else:
        print(f"{FAIL} latest.json 不存在")
        fatals += 1

    # stocks.json — 股票数据
    stocks_path = os.path.join(DATA_DIR, "stocks.json")
    if os.path.exists(stocks_path):
        try:
            with open(stocks_path, "r", encoding="utf-8") as f:
                stocks = json.load(f)
            stock_count = stocks.get("count", 0)
            expected = 14  # 当前股票池大小
            if stock_count >= expected * 0.7:
                print(f"{OK} stocks.json — {stock_count}/{expected} 只股票获取成功")
            elif stock_count > 0:
                print(f"{WARN} stocks.json — {stock_count}/{expected} 只 · 不到70%")
                anomalies += 1
            else:
                print(f"{FAIL} stocks.json — 0只股票获取成功")
                fatals += 1
        except json.JSONDecodeError as e:
            print(f"{FAIL} stocks.json 损坏: {e}")
            fatals += 1
    else:
        print(f"{FAIL} stocks.json 不存在")
        fatals += 1

    # ================================================================
    # 2. 验证 HTML 文件
    # ================================================================
    print("\n[2/4] HTML 文件验证")
    html_path = os.path.join(PROJECT_DIR, "发现榜.html")

    if not os.path.exists(html_path):
        print(f"{FAIL} 发现榜.html 不存在")
        fatals += 1
    else:
        size = os.path.getsize(html_path)
        if size < 3000:
            print(f"{FAIL} 发现榜.html 大小异常: {size} bytes (可能被清空)")
            fatals += 1
        elif size < 5000:
            print(f"{WARN} 发现榜.html 偏小: {size} bytes")
            anomalies += 1
        else:
            print(f"{OK} 发现榜.html — {size:,} bytes")

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        # 检查时间戳是否更新
        today_str = datetime.now(CST).strftime("%Y-%m-%d")
        if today_str in html:
            print(f"{OK} HTML 包含今日日期 {today_str}")
        else:
            print(f"{WARN} HTML 可能未更新 — 未找到今日日期 {today_str}")
            anomalies += 1

        # 检查源状态栏
        src_tag_count = len(re.findall(r'src-tag', html))
        if src_tag_count >= 15:
            print(f"{OK} 源状态栏正常 — {src_tag_count} 个标签")
        else:
            print(f"{WARN} 源状态栏异常 — 仅 {src_tag_count} 个标签")
            anomalies += 1

        # 检查股票数据是否注入
        price_count = len(re.findall(r'\d+\.\d{2}', html))
        if price_count > 10:
            print(f"{OK} 股票价格数据已注入 — {price_count}+ 处价格")
        else:
            print(f"{WARN} 价格数据可能缺失 — 仅 {price_count} 处")
            anomalies += 1

    # ================================================================
    # 3. 历史对比（如有上次数据）
    # ================================================================
    print("\n[3/4] 历史对比")
    last_path = os.path.join(DATA_DIR, "last.json")
    if os.path.exists(last_path):
        try:
            with open(last_path, "r", encoding="utf-8") as f:
                last = json.load(f)
            last_ok = last.get("summary", {}).get("ok", 0)
            curr_ok = latest.get("summary", {}).get("ok", 0)
            delta = curr_ok - last_ok
            if delta >= 0:
                print(f"{OK} 相比上次: {last_ok} → {curr_ok} ({delta:+d})")
            else:
                print(f"{WARN} 相比上次: {last_ok} → {curr_ok} ({delta}) · 源数下降")
                anomalies += 1
        except Exception as e:
            print(f"  [SKIP] 历史对比失败: {e}")
    else:
        print(f"  [SKIP] 无历史数据（首次运行）")

    # ================================================================
    # 4. 保存本次快照为 last.json（供下次对比）
    # ================================================================
    print("\n[4/4] 保存历史快照")
    try:
        if os.path.exists(latest_path):
            import shutil
            shutil.copy2(latest_path, os.path.join(DATA_DIR, "last.json"))
            print(f"{OK} 已保存本次快照到 last.json")
    except Exception as e:
        print(f"  [SKIP] 保存快照失败: {e}")

    # ================================================================
    # 结论
    # ================================================================
    print("\n" + "=" * 50)
    if fatals > 0:
        print(f"结果: [FAIL] {fatals} 个致命异常 → 建议人工检查")
        return 2
    if anomalies > 0:
        print(f"结果: [WARN] {anomalies} 个异常 → 已自动标注，可正常使用")
        return 1
    print("结果: [OK] 全部验证通过 · 管道健康")
    return 0


if __name__ == "__main__":
    sys.exit(main())
