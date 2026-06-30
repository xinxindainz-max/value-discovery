#!/usr/bin/env python3
"""
价值发现 · 源标签注册表
单一事实来源 —— 管道、HTML更新器、健康检查全部引用此文件。
标签一旦确定不允许私自定义新名称，新增源必须在此注册。
"""

# ============================================================
# 注册表（按ID排序）
# id: 管道内部键名
# label: HTML展示标签（也是update_html.py用来匹配的唯一标识）
# group: 分组（国内/国际/行情）
# check_url: 健康检查用连通性测试URL
# ============================================================

REGISTRY = {
    # === 国内 · UAPIs ===
    "weibo":       {"label": "微博热搜",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=weibo"},
    "baidu":       {"label": "百度热搜",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=baidu"},
    "zhihu":       {"label": "知乎热榜",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=zhihu"},
    "douyin":      {"label": "抖音总榜",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=douyin"},
    "bilibili":    {"label": "B站全站日榜",   "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=bilibili"},
    "wechat":      {"label": "微信热文",     "group": "国内", "check_url": "https://tophub.today/n/WnBe01o371"},
    "toutiao":     {"label": "今日头条",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=toutiao"},
    "smzdm":       {"label": "什么值得买",   "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=smzdm"},
    "xiaohongshu": {"label": "小红书",       "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=xiaohongshu"},
    "kuaishou":    {"label": "快手",         "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=kuaishou"},
    "36kr":        {"label": "36氪",        "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=36kr"},
    "ithome":      {"label": "IT之家",      "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=ithome"},
    "sina":        {"label": "新浪热榜",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=sina"},
    "qq_news":     {"label": "腾讯新闻",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=qq-news"},
    "netease_news":{"label": "网易新闻",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=netease-news"},
    "thepaper":    {"label": "澎湃新闻",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=thepaper"},
    "tieba":       {"label": "百度贴吧",     "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=tieba"},
    "hupu":        {"label": "虎扑",         "group": "国内", "check_url": "https://uapis.cn/api/v1/misc/hotboard?type=hupu"},

    # === 国际 · TrendsMCP ===
    "google_trends":       {"label": "Google Trends",      "group": "国际", "check_url": "https://api.trendsmcp.ai/api"},
    "trendsmcp_x":         {"label": "X/Twitter 热门",     "group": "国际", "check_url": "https://api.trendsmcp.ai/api"},
    "trendsmcp_youtube":   {"label": "YouTube 热门",       "group": "国际", "check_url": "https://api.trendsmcp.ai/api"},
    "trendsmcp_reddit":    {"label": "Reddit World News",  "group": "国际", "check_url": "https://api.trendsmcp.ai/api"},

    # === 行情 ===
    "westock":             {"label": "westock 行情",       "group": "行情", "check_url": "https://qt.gtimg.cn/q=sz000333"},
}

# 反向索引：label → id
LABEL_TO_ID = {v["label"]: k for k, v in REGISTRY.items()}

# 所有已知标签的集合（用于update_html.py检测HTML中有但registry中没有的标签）
ALL_LABELS = set(LABEL_TO_ID.keys())

def get_label(source_id):
    """根据ID获取标准标签"""
    entry = REGISTRY.get(source_id)
    return entry["label"] if entry else source_id

def get_check_url(source_id):
    """获取健康检查URL"""
    entry = REGISTRY.get(source_id)
    return entry["check_url"] if entry else None

def validate_html_labels(html_labels):
    """
    检查HTML中的标签是否都在registry中注册。
    返回 (matched, unmatched) 两个列表。
    """
    unmatched = [l for l in html_labels if l not in ALL_LABELS]
    matched = [l for l in html_labels if l in ALL_LABELS]
    return matched, unmatched
