#!/usr/bin/env python3
"""
价值发现 · 部署助手 v1.0
用于自动化的部署+桌面同步步骤（Python层兜底）
用法: python deploy_helper.py
"""

import os
import sys
import shutil
import subprocess
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
PROJECT_DIR = r"C:\Users\DD\WorkBuddy\2026-06-25-11-10-03"
HTML_FILE = os.path.join(PROJECT_DIR, "发现榜.html")
DESKTOP_COPY = r"C:\Users\DD\Desktop\价值发现_本周.html"
MEMORY_DIR = os.path.join(PROJECT_DIR, ".workbuddy", "memory")


def sync_desktop():
    """同步桌面副本"""
    if not os.path.exists(HTML_FILE):
        print(f"[✗] HTML 文件不存在: {HTML_FILE}")
        return False
    try:
        shutil.copy2(HTML_FILE, DESKTOP_COPY)
        print(f"[✓] 桌面副本已同步: {DESKTOP_COPY}")
        return True
    except Exception as e:
        print(f"[✗] 桌面同步失败: {e}")
        return False


def log_deploy(sources_ok, sources_total):
    """记录部署日志"""
    today = datetime.now(CST).strftime("%Y-%m-%d")
    log_file = os.path.join(MEMORY_DIR, f"{today}.md")
    os.makedirs(MEMORY_DIR, exist_ok=True)

    ts = datetime.now(CST).strftime("%H:%M")
    entry = f"\n[deploy {ts}] 部署完成, 数据源 {sources_ok}/{sources_total}\n"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"[✓] 日志已写入: {log_file}")


def main():
    print("价值发现 · 部署助手 v1.0")
    print(f"时间: {datetime.now(CST).isoformat()}")

    # 同步桌面
    sync_desktop()

    # 日志
    log_deploy("?", "?")

    print("[✓] 部署助手完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
