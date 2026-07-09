#!/usr/bin/env python3
"""
TrendsMCP API 调用器 — 多Key轮换 + 额度管理
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent.parent
KEYS_FILE = ROOT / ".workbuddy" / "pipeline" / "trends_keys.json"
USAGE_FILE = ROOT / ".workbuddy" / "pipeline" / "data" / "trends_usage.json"

def load_config():
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_usage():
    if USAGE_FILE.exists():
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_usage(usage):
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(usage, f, ensure_ascii=False, indent=2)

def get_today_str():
    return datetime.now(CST).strftime("%Y-%m-%d")

def get_month_str():
    return datetime.now(CST).strftime("%Y-%m")

def get_available_key():
    """找到一个还有额度的Key，返回 (key, key_index)"""
    config = load_config()
    usage = load_usage()
    today = get_today_str()
    month = get_month_str()
    
    dead_keys = set(config.get("dead_keys", []))
    
    for i, key in enumerate(config["keys"]):
        if i in dead_keys:
            continue
        key_id = f"key_{i}"
        ku = usage.get(key_id, {"daily": {}, "monthly": {}})
        
        daily_used = ku.get("daily", {}).get(today, 0)
        monthly_used = ku.get("monthly", {}).get(month, 0)
        
        if daily_used < config["daily_limit_per_key"] and monthly_used < config["monthly_limit_per_key"]:
            return key, i
    
    return None, -1

def record_usage(key_index):
    """记录一次API调用"""
    usage = load_usage()
    today = get_today_str()
    month = get_month_str()
    key_id = f"key_{key_index}"
    
    if key_id not in usage:
        usage[key_id] = {"daily": {}, "monthly": {}}
    
    usage[key_id]["daily"][today] = usage[key_id]["daily"].get(today, 0) + 1
    usage[key_id]["monthly"][month] = usage[key_id]["monthly"].get(month, 0) + 1
    
    save_usage(usage)

def call_trends_api(keyword, source, mode="get_growth", percent_growth=None):
    """
    调用 TrendsMCP API
    返回解析后的数据 dict，或 None（失败时）
    """
    key, key_idx = get_available_key()
    if key is None:
        print("[trends] 所有Key额度已用完")
        return None
    
    payload = {
        "mode": mode,
        "keyword": keyword,
        "source": source,
    }
    if percent_growth:
        payload["percent_growth"] = percent_growth
    
    try:
        resp = requests.post(
            "https://api.trendsmcp.ai/api",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=30
        )
        
        if resp.status_code != 200:
            print(f"[trends] API返回 {resp.status_code}: {resp.text[:200]}")
            return None
        
        data = resp.json()
        body = data.get("body", "")
        
        if isinstance(body, str):
            # 检查是否是额度用完的错误
            if "limit" in body.lower() or "exceeded" in body.lower():
                print(f"[trends] Key {key_idx} 额度用完: {body[:100]}")
                # 标记此key今天用完
                return None
            body = json.loads(body)
        
        record_usage(key_idx)
        return body
        
    except Exception as e:
        print(f"[trends] API调用失败: {e}")
        return None

def get_google_growth(keyword, periods=None):
    """
    获取 Google Search 增长数据
    返回: {period: {growth: float, direction: str, recent_value: float}} 或 None
    """
    if periods is None:
        periods = ["1M", "3M", "6M", "1Y"]
    
    body = call_trends_api(
        keyword=keyword,
        source="google search",
        mode="get_growth",
        percent_growth=periods
    )
    
    if not body or "results" not in body:
        return None
    
    result = {}
    for r in body["results"]:
        if r.get("status") == "success":
            result[r["period"]] = {
                "growth": r.get("growth", 0),
                "direction": r.get("direction", "flat"),
                "recent_value": r.get("recent_value", 0),
                "baseline_value": r.get("baseline_value", 0),
            }
    
    return result if result else None

def get_app_ranking_growth(android_package, periods=None):
    """
    获取 App Rankings 增长数据
    返回: {period: {growth: float, direction: str, recent_value: float}} 或 None
    """
    if not android_package:
        return None
    
    if periods is None:
        periods = ["1M"]
    
    body = call_trends_api(
        keyword=android_package,
        source="app rankings",
        mode="get_growth",
        percent_growth=periods
    )
    
    if not body or "results" not in body:
        return None
    
    result = {}
    for r in body["results"]:
        if r.get("status") == "success":
            result[r["period"]] = {
                "growth": r.get("growth", 0),
                "direction": r.get("direction", "flat"),
                "recent_value": r.get("recent_value", 0),
                "recent_volume": r.get("recent_volume", 0),
            }
    
    return result if result else None

def get_usage_summary():
    """返回当前额度使用情况"""
    config = load_config()
    usage = load_usage()
    today = get_today_str()
    month = get_month_str()
    
    total_daily = 0
    total_monthly = 0
    
    for i in range(len(config["keys"])):
        key_id = f"key_{i}"
        ku = usage.get(key_id, {"daily": {}, "monthly": {}})
        d = ku.get("daily", {}).get(today, 0)
        m = ku.get("monthly", {}).get(month, 0)
        total_daily += d
        total_monthly += m
        print(f"  Key {i+1}: 今日 {d}/{config['daily_limit_per_key']} | 本月 {m}/{config['monthly_limit_per_key']}")
    
    max_daily = len(config["keys"]) * config["daily_limit_per_key"]
    max_monthly = len(config["keys"]) * config["monthly_limit_per_key"]
    print(f"  总计: 今日 {total_daily}/{max_daily} | 本月 {total_monthly}/{max_monthly}")


if __name__ == "__main__":
    # Windows UTF-8
    if sys.platform == "win32":
        sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    
    print("=== TrendsMCP 额度使用情况 ===")
    get_usage_summary()
