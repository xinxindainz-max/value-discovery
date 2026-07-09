#!/usr/bin/env python3
"""
历史数据库管理器
存储每日信号快照到CSV，计算7/30/90天变化
"""
import csv
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent.parent
HISTORY_DIR = ROOT / ".workbuddy" / "pipeline" / "data" / "history"
SNAPSHOT_DIR = ROOT / ".workbuddy" / "pipeline" / "data" / "snapshot"

CSV_FIELDS = ["date", "company", "metric", "value"]

def get_today_str():
    return datetime.now(CST).strftime("%Y-%m-%d")

def get_date_str(days_ago):
    d = datetime.now(CST) - timedelta(days=days_ago)
    return d.strftime("%Y-%m-%d")

def ensure_dirs():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

def append_history(company, metric, value):
    """追加一条历史记录到CSV"""
    ensure_dirs()
    csv_path = HISTORY_DIR / "signals.csv"
    today = get_today_str()
    
    # 检查今天是否已有这条记录（避免重复）
    existing = []
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing = [r for r in reader if r["date"] == today and r["company"] == company and r["metric"] == metric]
    
    if existing:
        # 更新今天的值
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r["date"] == today and r["company"] == company and r["metric"] == metric:
                    r["value"] = str(value)
                rows.append(r)
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    else:
        # 追加新行
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if csv_path.stat().st_size == 0:
                writer.writeheader()
            writer.writerow({"date": today, "company": company, "metric": metric, "value": str(value)})

def save_snapshot(data):
    """保存完整快照到JSON"""
    ensure_dirs()
    today = get_today_str()
    snapshot_path = SNAPSHOT_DIR / f"{today}.json"
    import json
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_history(company, metric):
    """
    获取某公司某指标的历史数据
    返回: [{date, value}, ...] 按日期升序
    """
    csv_path = HISTORY_DIR / "signals.csv"
    if not csv_path.exists():
        return []
    
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["company"] == company and r["metric"] == metric:
                try:
                    rows.append({"date": r["date"], "value": float(r["value"])})
                except ValueError:
                    pass
    
    rows.sort(key=lambda x: x["date"])
    return rows

def calculate_changes(company, metric, current_value):
    """
    计算7/30/90天变化
    返回: {current, d7, d30, d90, change_7d, change_30d, change_90d, has_history}
    """
    history = get_history(company, metric)
    
    result = {
        "current": current_value,
        "change_7d": None,
        "change_30d": None,
        "change_90d": None,
        "value_7d_ago": None,
        "value_30d_ago": None,
        "value_90d_ago": None,
        "has_history": len(history) > 0,
        "history_days": len(history),
    }
    
    if not history or current_value is None:
        return result
    
    today = get_today_str()
    
    for days, key in [(7, "7d"), (30, "30d"), (90, "90d")]:
        target_date = get_date_str(days)
        # 找最接近目标日期的记录
        closest = None
        for h in history:
            if h["date"] <= target_date:
                closest = h
            elif closest is None:
                closest = h
        
        if closest and closest["date"] != today:
            old_val = closest["value"]
            if old_val != 0:
                change = round((current_value - old_val) / old_val * 100, 1)
            else:
                change = None
            result[f"change_{key}"] = change
            result[f"value_{key}_ago"] = old_val
    
    return result

def get_trend_direction(changes):
    """根据变化数据判断趋势方向"""
    c7 = changes.get("change_7d")
    c30 = changes.get("change_30d")
    
    if c7 is None and c30 is None:
        return "no_data"
    
    # 优先看7天变化
    if c7 is not None:
        if c7 > 10:
            return "rising"
        elif c7 < -10:
            return "falling"
    
    # 7天不明显看30天
    if c30 is not None:
        if c30 > 20:
            return "rising"
        elif c30 < -20:
            return "falling"
    
    return "flat"

def cleanup_old_data(max_days=90):
    """删除超过90天的历史数据"""
    csv_path = HISTORY_DIR / "signals.csv"
    if not csv_path.exists():
        return
    
    cutoff = get_date_str(max_days)
    rows = []
    removed = 0
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["date"] >= cutoff:
                rows.append(r)
            else:
                removed += 1
    
    if removed > 0:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[history] 清理 {removed} 条超过{max_days}天的旧数据")

def get_history_summary():
    """返回历史数据概况"""
    csv_path = HISTORY_DIR / "signals.csv"
    if not csv_path.exists():
        return {"total_records": 0, "date_range": "无", "companies": 0}
    
    dates = set()
    companies = set()
    count = 0
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            dates.add(r["date"])
            companies.add(r["company"])
            count += 1
    
    if dates:
        return {
            "total_records": count,
            "date_range": f"{min(dates)} ~ {max(dates)}",
            "days": len(dates),
            "companies": len(companies),
        }
    return {"total_records": 0, "date_range": "无", "companies": 0}
