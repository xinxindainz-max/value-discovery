#!/usr/bin/env python3
"""
价值发现 · 数据抓取管道 v3.0
从23个数据源批量抓取热榜数据，输出结构化JSON。
用法: python data_fetcher.py [--output data/latest.json] [--timeout 15]
设计原则：
- 每个源独立超时+指数退避重试(最多3次)，单个失败不影响整体
- 输出包含源状态(ok/fail/timeout)、抓取时间戳、重试次数、原始数据
- 所有路径使用绝对路径，适配自动化环境
v3.0: 指数退避重试、retries追踪
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta

# GitHub Actions 环境强制 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import requests
except ImportError:
    print("[FATAL] requests 库未安装，请运行: pip install requests")
    sys.exit(1)

# ============================================================
# 配置
# ============================================================
CST = timezone(timedelta(hours=8))

DATA_SOURCES = {
    # === 国际 ===
    "google_trends": {
        "label": "Google Trends",
        "url": "https://api.trendsmcp.ai/api",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer tmcp_live_rl5x9g3gvyux2nwhfsgvkmfn9bw0nl2s",
            "Content-Type": "application/json"
        },
        "body": {"mode": "top_trends", "type": "Google Trends", "limit": 20}
    },
    # === 国内免费渠道 ===
    "weibo": {
        "label": "微博热搜",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=weibo",
        "method": "GET",
        "headers": {}
    },
    "baidu": {
        "label": "百度热搜",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=baidu",
        "method": "GET",
        "headers": {}
    },
    "zhihu": {
        "label": "知乎热榜",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=zhihu",
        "method": "GET",
        "headers": {}
    },
    "douyin": {
        "label": "抖音总榜",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=douyin",
        "method": "GET",
        "headers": {}
    },
    "bilibili": {
        "label": "B站全站日榜",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=bilibili",
        "method": "GET",
        "headers": {}
    },
    "wechat": {
        "label": "微信热文",
        "url": "https://tophub.today/n/WnBe01o371",
        "method": "GET",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        "note": "tophub.today直连 · HTML正则解析",
        "no_proxy": True
    },
    "toutiao": {
        "label": "今日头条",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=toutiao",
        "method": "GET",
        "headers": {}
    },
    "smzdm": {
        "label": "什么值得买",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=smzdm",
        "method": "GET",
        "headers": {}
    },
    "xiaohongshu": {
        "label": "小红书",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=xiaohongshu",
        "method": "GET",
        "headers": {}
    },
    "kuaishou": {
        "label": "快手",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=kuaishou",
        "method": "GET",
        "headers": {}
    },
    # === 新增：财经/科技/社交（2026.06.30 举一反三） ===
    "36kr": {
        "label": "36氪",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=36kr",
        "method": "GET",
        "headers": {}
    },
    "ithome": {
        "label": "IT之家",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=ithome",
        "method": "GET",
        "headers": {}
    },
    "sina": {
        "label": "新浪热榜",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=sina",
        "method": "GET",
        "headers": {}
    },
    "qq_news": {
        "label": "腾讯新闻",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=qq-news",
        "method": "GET",
        "headers": {}
    },
    "netease_news": {
        "label": "网易新闻",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=netease-news",
        "method": "GET",
        "headers": {}
    },
    "thepaper": {
        "label": "澎湃新闻",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=thepaper",
        "method": "GET",
        "headers": {}
    },
    "tieba": {
        "label": "百度贴吧",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=tieba",
        "method": "GET",
        "headers": {}
    },
    "hupu": {
        "label": "虎扑",
        "url": "https://uapis.cn/api/v1/misc/hotboard?type=hupu",
        "method": "GET",
        "headers": {}
    },
    # === TrendsMCP 国际渠道 ===
    "trendsmcp_x": {
        "label": "X/Twitter 热门",
        "url": "https://api.trendsmcp.ai/api",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer tmcp_live_rl5x9g3gvyux2nwhfsgvkmfn9bw0nl2s",
            "Content-Type": "application/json"
        },
        "body": {"mode": "top_trends", "type": "X (Twitter) Trending", "limit": 15}
    },
    "trendsmcp_youtube": {
        "label": "YouTube 热门",
        "url": "https://api.trendsmcp.ai/api",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer tmcp_live_rl5x9g3gvyux2nwhfsgvkmfn9bw0nl2s",
            "Content-Type": "application/json"
        },
        "body": {"mode": "top_trends", "type": "YouTube Trending", "limit": 15}
    },
    "trendsmcp_reddit": {
        "label": "Reddit World News",
        "url": "https://api.trendsmcp.ai/api",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer tmcp_live_rl5x9g3gvyux2nwhfsgvkmfn9bw0nl2s",
            "Content-Type": "application/json"
        },
        "body": {"mode": "top_trends", "type": "Reddit World News", "limit": 15}
    },
}


def _parse_tophub_html(html_text):
    """从 tophub.today HTML 中解析微信热文，返回 UAPIs 兼容格式"""
    import re
    from datetime import datetime, timezone, timedelta
    cst = timezone(timedelta(hours=8))

    items = []
    # 匹配: <a href="..." target="_blank" rel="nofollow" itemid="123">标题</a>
    # 其后紧跟 <td class="ws"> 中的阅读量（可选）
    pattern = re.compile(
        r'<a\s+href="([^"]+)"[^>]*?itemid="(\d+)"[^>]*?>\s*([^<]+?)\s*</a>',
        re.DOTALL
    )

    for m in pattern.finditer(html_text):
        url = m.group(1)
        itemid = m.group(2)
        title = m.group(3).strip()
        # 过滤掉非文章链接（如导航、about、help等）
        if not url.startswith("https://mp.weixin.qq.com"):
            continue
        if not title or len(title) < 3:
            continue
        items.append({
            "title": title,
            "url": url,
            "itemid": itemid,
        })

    # 去重（按 itemid）
    seen = set()
    unique_items = []
    for item in items:
        if item["itemid"] not in seen:
            seen.add(item["itemid"])
            unique_items.append(item)

    # 转为 UAPIs 兼容格式
    result_list = []
    for i, item in enumerate(unique_items[:30], 1):
        result_list.append({
            "index": i,
            "title": item["title"],
            "url": item["url"],
            "hot_value": item["itemid"],
            "extra": {},
        })

    return {
        "type": "wechat",
        "update_time": datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S"),
        "list": result_list,
    }


def fetch_one(key, cfg, timeout_sec, max_retries=3):
    """抓取单个数据源，含指数退避重试。返回 (status, data, error_msg, elapsed_ms, retries)"""
    t0 = time.time()
    last_error = None

    for attempt in range(max_retries):
        try:
            session = requests.Session()
            # no_proxy 源：显式禁用代理 + 跳过环境变量，防止 GitHub Actions 代理干扰
            req_kwargs = {"headers": cfg.get("headers", {}), "timeout": timeout_sec}
            if cfg.get("no_proxy"):
                session.trust_env = False
                req_kwargs["proxies"] = {"http": None, "https": None}

            if cfg["method"] == "GET":
                resp = session.get(cfg["url"], **req_kwargs)
            else:  # POST
                resp = session.post(cfg["url"], json=cfg.get("body", {}), **req_kwargs)

            elapsed = int((time.time() - t0) * 1000)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except (json.JSONDecodeError, ValueError):
                    # 微信热文：tophub.today HTML → 解析为结构化数据
                    if key == "wechat":
                        data = _parse_tophub_html(resp.text)
                    else:
                        data = {"raw_text": resp.text[:10000]}
                return ("ok", data, None, elapsed, attempt)

            # 非200 → 5xx/429/400(Cloudflare WAF) 重试
            retryable = (resp.status_code >= 500 or resp.status_code == 429 or
                         (resp.status_code == 400 and cfg.get("no_proxy")))
            if retryable and attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait)
                last_error = f"HTTP {resp.status_code} (重试 {attempt+1}/{max_retries})"
                continue
            return ("fail", None, f"HTTP {resp.status_code}", elapsed, attempt)

        except requests.exceptions.Timeout:
            elapsed = int((time.time() - t0) * 1000)
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
                last_error = f"超时 (重试 {attempt+1}/{max_retries})"
                continue
            return ("timeout", None, f"重试{max_retries}次均超时 ({timeout_sec}s/次)", elapsed, attempt)

        except requests.exceptions.ConnectionError as e:
            elapsed = int((time.time() - t0) * 1000)
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
                last_error = f"连接失败 (重试 {attempt+1}/{max_retries})"
                continue
            return ("fail", None, f"连接失败: {str(e)[:100]}", elapsed, attempt)

        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
                last_error = f"{type(e).__name__} (重试 {attempt+1}/{max_retries})"
                continue
            return ("fail", None, f"{type(e).__name__}: {str(e)[:100]}", elapsed, attempt)

    elapsed = int((time.time() - t0) * 1000)
    return ("fail", None, last_error or "未知错误", elapsed, max_retries - 1)


def run_all(timeout_sec=15):
    """执行全量抓取"""
    results = {
        "meta": {
            "fetched_at": datetime.now(CST).isoformat(),
            "fetched_at_unix": int(time.time()),
            "timeout_sec": timeout_sec,
            "pipeline_version": "3.0",
        },
        "sources": {},
        "summary": {"total": len(DATA_SOURCES), "ok": 0, "fail": 0, "timeout": 0},
        "retry_stats": {"total_retries": 0, "sources_retried": 0},
    }

    for key, cfg in DATA_SOURCES.items():
        label = cfg["label"]
        print(f"[{label}] 抓取中...", end=" ", flush=True)
        status, data, error, elapsed, retries = fetch_one(key, cfg, timeout_sec)

        results["sources"][key] = {
            "label": label,
            "status": status,
            "elapsed_ms": elapsed,
            "error": error,
            "data": data,
            "retries": retries,
        }
        results["summary"][status] += 1
        if retries > 0:
            results["retry_stats"]["total_retries"] += retries
            results["retry_stats"]["sources_retried"] += 1

        icon = {"ok": "✓", "fail": "✗", "timeout": "⏱"}[status]
        retry_note = f" (rt{retries})" if retries > 0 else ""
        print(f"{icon} {elapsed}ms{retry_note}" + (f" {error}" if error else ""))

    print(f"\n{'='*50}")
    retry_info = ""
    if results["retry_stats"]["total_retries"] > 0:
        retry_info = (f" | 重试: {results['retry_stats']['total_retries']}次 "
                      f"({results['retry_stats']['sources_retried']}源)")
    print(f"完成: {results['summary']['ok']}/{results['summary']['total']} 成功, "
          f"{results['summary']['fail']} 失败, {results['summary']['timeout']} 超时{retry_info}")
    return results


def save(results, output_path):
    """保存结果到JSON文件"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[✓] 已保存到 {output_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="价值发现 · 数据抓取管道")
    parser.add_argument("--output", default=None,
                        help="输出JSON路径 (默认: data/latest.json)")
    parser.add_argument("--timeout", type=int, default=15,
                        help="单源超时秒数 (默认15)")
    args = parser.parse_args()

    # 确定输出路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = args.output or os.path.join(script_dir, "data", "latest.json")

    print(f"价值发现 · 数据抓取管道 v3.0")
    print(f"输出: {output_path}")
    print(f"超时: {args.timeout}s/源 · 最多3次重试")
    print(f"{'='*50}")

    results = run_all(args.timeout)
    save(results, output_path)

    # 返回状态码：全部成功=0，部分失败=1
    if results["summary"]["fail"] > 0 or results["summary"]["timeout"] > 0:
        print("\n⚠ 部分数据源失败，但已保存可用数据")
    return 0  # 总是返回0，部分失败不阻断下游


if __name__ == "__main__":
    sys.exit(main())
