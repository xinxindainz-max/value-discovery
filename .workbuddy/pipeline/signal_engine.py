#!/usr/bin/env python3
"""
Value Discovery · Signal Engine v4.0
=====================================
Outputs three-zone JSON (early / seasonal / priced-in) for discovery board.
Dynamic JSON-driven page: dist/index.html fetches data/discovery_board.json.

Zones:
  ZONE 1: 早期/异动 — L1-L3 sources, behavior keywords, not yet mainstream
  ZONE 2: 季节性提醒 — matches SEASONAL_KEYWORDS
  ZONE 3: 已起飞 — L5-L6 sources + high rank, already fully priced

Output: discovery_board.json
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Windows UTF-8
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / ".workbuddy" / "pipeline" / "data"

# ── Layer System ──
PLATFORM_LAYER = {
    "X/Twitter 热门": 1, "Reddit World News": 1,
    "Google Trends": 2,
    "小红书": 3, "什么值得买": 3,
    "抖音总榜": 4, "B站全站日榜": 4, "知乎热榜": 4, "快手": 4, "YouTube 热门": 4,
    "36氪": 5, "IT之家": 5,
    "微博热搜": 6, "百度热搜": 6, "腾讯新闻": 6, "网易新闻": 6,
    "今日头条": 6, "微信热文": 6, "新浪热榜": 6, "澎湃新闻": 6,
    "百度贴吧": 6, "虎扑": 6,
}

# ── Action Verb Heuristics ──
ACTION_VERBS = re.compile(
    # 中文用户动作词
    r"使用|购买|买了|入手|开始|增加|改用|换成|换了|学会|下载|体验|"
    r"推荐|种草|拔草|值得买|怎么选|哪个好|好用|实用|"
    r"囤|囤货|开箱|测评|对比|下单|加入购物车|收藏|"
    r"试了|用了|穿搭|搭配|买了啥|想买|要不要买|看看|"
    # 什么值得买隐含行为信号 —— 促销语言 = 购买意图
    r"今日必买|百亿补贴|淘金币可用|88VIP|手慢无|"
    r"历史低价|绝对值|好价|性价比|"
    # 英文
    r"buy|buying|purchase|using|switching|adopting|trying|testing|"
    r"subscribing|downloading|installing",
    re.IGNORECASE
)
NEWS_VERBS = re.compile(
    r"发布|发布会|最新|报道|揭露|震惊|官宣|曝光|公告|突发|刚刚|"
    r"正式|宣布|声明|上市|推出|首发|揭幕|亮相|揭晓|"
    r"回应|辟谣|通报|通知|警告|announces?|launches?|reveals?"
)

# ── Reject Filters (expanded) ──
NON_BEHAVIOR_KEYWORDS = re.compile(
    r"地震|台风|暴雨|洪水|火山|海啸|战争|冲突|入侵|制裁|"
    r"遇难|死亡|伤|事故|火灾|爆炸|枪击|坠毁|翻坠|"
    r"earthquake|tsunami|hurricane|typhoon|flood|tornado|volcano|"
    r"invasion|war|conflict|attack|strike|bombing|missile|"
    r"extreme.heat|heat.warning|winter.storm|storm.warning|"
    # 体育
    r"世界杯|足球赛|比赛|联赛|决赛|冠军|淘汰赛|晋级|绝杀|点球|"
    r"世界杯|奥运|金牌|赛季|阵容|自由市场|交易至|"
    # 娱乐/八卦
    r"电影|电视剧|综艺|演唱会|新歌|MV|明星|演员|歌手|偶像|"
    r"结婚|离婚|绯闻|恋情|八卦|颜值|全球最美|"
    r"王俊凯|白鹿|杨紫|凯恩|詹姆斯|湖人|"
    # 政治/社会
    r"政策|法规|条例|通知|会议|讲话|勋章|党建|建党|"
    r"总书记|主席|总理|外交|领事|大使馆|"
    r"习近平|普京|基辅|防空|导弹|"
    # 社会评论/情感
    r"脱下长衫|打工|毕业照|毕业典礼|孩童|宝宝|姑姑|"
    r"女子|男子|小伙|姑娘|婆婆|"
    # 股市/金融（纯行情非消费）
    r"股价|涨停|跌停|大盘|股市|基金|熔断|A股|新股|"
    r"成交额|指数|沪深|恒生|"
    # 教育
    r"高考|志愿|录取|查分|考试|退学|清华|北大|"
    # 其他噪音
    r"景区|道歉|刀片|刺绳|豪宅|流浪汉|许家印|"
    r"赛格|商铺|拍卖|拍出|"
    # 职场/企业新闻（非消费行为）
    r"裁员|裁人|降薪|离职|开除|解雇|"
    # 社会新闻
    r"警方|警情|通报|报警|报案|拘留|刑拘|"
    # 娱乐人物
    r"耳帝|曾沛慈|敖尹|"
    # B站杂烩/娱乐视频
    r"断网补全|摇一摇|月薪猫|夜坝|买命|炸虫|体验湘西|失控|表情全程|"
    # 算力/AI行业新闻（非消费）
    r"算力|大模型|GPU采购|融资支持|"
    # 纯股市行情（非消费行为）
    r"上市首日|涨超|跌超|新股上市|首日涨|收盘|开盘|盘中|"
    # 误匹配防护
    r"风景|看更美|更美的|"
    # 辟谣功能上线（非消费行为）
    r"辟谣.正式上线|辟谣.上线|"
    # 信息泄露/技术八卦（非消费）
    r"信息泄露|开发板|手搓|"
    # 游戏角色/动漫
    r"吃醋|暴跳如雷|茜特菈莉|桑多涅|旅行者|"
    # 美食探店（非投资信号）
    r"大众点评|必吃|探店|今朝有玩|"
    # 企业注册/公司成立（非消费行为）
    r"成立新.*公司|智能科技公司|增资至|旗下.*公司|"
    # 创业/融资新闻
    r"创业|融资|团队创业|硬氪首发|首发.*完成|"
    # 二手车市场
    r"二手豪车|改干烧烤|车商",
    re.IGNORECASE
)

# ── Consumer Relevance Whitelist ──
# An item MUST match at least one of these to be included
CONSUMER_KEYWORDS = re.compile(
    # 产品品类
    r"手机|笔记本|平板|耳机|手表|手环|相机|镜头|电视|显示器|"
    r"冰箱|空调|洗衣机|风扇|扫地机|净化器|加湿器|"
    r"充电|电池|充电宝|电源|插头|插座|开关|"
    r"路由器|网线|信号|mesh|无线|"
    r"键盘|鼠标|手柄|显卡|主板|内存|硬盘|"
    r"酸奶|牛奶|咖啡|奶茶|零食|饮料|白酒|啤酒|"
    r"口红|护肤|面膜|精华|防晒|彩妆|"
    r"鞋子|球鞋|包包|裙子|外套|羽绒服|"
    r"床垫|枕头|沙发|家具|"
    r"无人机|机器人|机器狗|陪伴|智能|"
    r"电车|新能源|充电桩|混动|"
    r"折叠屏|鸿蒙|harmonyos|iOS|android|"
    # 品牌
    r"苹果|apple|iphone|华为|荣耀|honor|小米|xiaomi|红米|"
    r"酷态科|酷科|cuco|领普|京东云|ROG|华硕|"
    r"大疆|dji|格力|美的|海尔|海信|tcl|"
    r"索尼|sony|三星|samsung|LG|佳能|尼康|"
    r"蔚来|理想|小鹏|比亚迪|byd|问界|极氪|"
    r"安克|anker|倍思|baseus|"
    # 购买行为
    r"买|入手|开箱|测评|对比|下单|补贴|好价|性价比|"
    r"降价|打折|促销|首发|发布|上市|开售|"
    r"必买|值得买|种草|拔草|推荐|"
    r"排长龙|排队|抢购|秒杀|"
    r"buy|purchase|deal|discount|launch|release|"
    r"price|priced|cost|afford",
    re.IGNORECASE
)

SEASONAL_KEYWORDS = re.compile(
    r"618|双11|双十二|双12|Prime\s*Day|prime\s*day|黑五|Black\s*Friday|black\s*friday|"
    r"年货节|开学季|毕业季|暑假|寒假|春节|国庆|五一|端午|中秋|清明|"
    r"财报季|Q[1-4]财报|年报|季报",
    re.IGNORECASE
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Data Extraction ──
def extract_raw_items(latest_data):
    """从 latest.json 提取所有原始条目"""
    items = []
    sources = latest_data.get("sources", {})
    for key, src in sources.items():
        if src.get("status") != "ok":
            continue
        label = src.get("label", key)
        layer = PLATFORM_LAYER.get(label, 6)
        src_data = src.get("data", {})
        entries = src_data.get("list", []) if isinstance(src_data, dict) else []

        body = src_data.get("body", "") if isinstance(src_data, dict) else ""
        if body and not entries:
            try:
                parsed = json.loads(body)
                raw_data = parsed.get("data", [])
                if raw_data:
                    entries = []
                    for item in raw_data:
                        if isinstance(item, list) and len(item) >= 2:
                            entries.append({"index": item[0], "title": str(item[1]), "hot_value": ""})
            except (json.JSONDecodeError, KeyError):
                pass

        for i, item in enumerate(entries):
            if isinstance(item, dict):
                title = item.get("title") or item.get("word") or ""
                rank = item.get("index", item.get("rank", i + 1))
            elif isinstance(item, str):
                title = item
                rank = i + 1
            else:
                continue
            if not title or len(title.strip()) < 2:
                continue
            items.append({
                "source": label, "source_key": key, "layer": layer,
                "title": title.strip()[:200], "rank": int(rank) if rank else i + 1,
            })
    return items


# ── Behavior Detection ──
def is_behavior(title):
    """返回 True 如果标题与消费/产品/品牌相关"""
    # 先拒绝噪音
    if NON_BEHAVIOR_KEYWORDS.search(title):
        return False
    if SEASONAL_KEYWORDS.search(title):
        return False
    # 必须匹配消费品白名单
    if not CONSUMER_KEYWORDS.search(title):
        return False
    return True


def has_action(title):
    """标题是否包含动作词"""
    return bool(ACTION_VERBS.search(title))


# ── Simple Keyword Clustering (no TF-IDF) ──
def extract_keywords(title):
    """从标题中提取关键词用于分组（中文+英文品牌名）"""
    # 中文 2-4 字片段
    words = re.findall(r'[\u4e00-\u9fff]{2,4}', title)
    # 英文品牌名/产品名（3+ 字母）
    en_words = re.findall(r'[a-zA-Z][a-zA-Z0-9]{2,}', title)
    return set(w for w in words if w not in NOISE_WORDS) | \
           set(w.lower() for w in en_words if w.lower() not in NOISE_WORDS)


NOISE_WORDS = {
    "今日", "必买", "可用", "限时", "热门", "推荐", "精选", "超值",
    "点击", "查看", "更多", "最新", "已经", "还有", "真的", "觉得",
    "这个", "那个", "什么", "怎么", "有没有", "会不会",
    "the", "and", "for", "with", "this", "that",
}


def group_items(items):
    """简单关键词重合度分组"""
    clusters = []
    assigned = [False] * len(items)
    for i, item in enumerate(items):
        if assigned[i]:
            continue
        ki = extract_keywords(item["title"])
        if not ki:
            clusters.append([item])
            assigned[i] = True
            continue

        members = [item]
        assigned[i] = True
        for j in range(i + 1, len(items)):
            if assigned[j]:
                continue
            kj = extract_keywords(items[j]["title"])
            if not kj:
                continue
            overlap = ki & kj
            # 只要有1个关键词重合就合并
            if len(overlap) >= 1:
                members.append(items[j])
                assigned[j] = True
                ki |= kj  # 吸收关键词
        clusters.append(members)
    return clusters


# ── Confidence Assignment ──
def assign_confidence(cluster):
    """
    HIGH: true action verbs + multi-item + L1-L2 source
    MEDIUM: action verbs + L3 source + multi-item
    LOW: weak signal or single item
    """
    action_count = sum(1 for it in cluster if has_action(it["title"]))
    action_ratio = action_count / max(len(cluster), 1)
    layers = set(it["layer"] for it in cluster)
    sources = set(it["source"] for it in cluster)

    if action_count >= 2 and action_ratio >= 0.5 and min(layers) <= 2:
        return "High"
    if action_count >= 2 and action_ratio >= 0.4 and min(layers) <= 3:
        return "Medium"
    if action_count >= 1 and len(cluster) >= 2:
        return "Medium"
    return "Low"


# ── Topic Extraction ──
def extract_topic(cluster):
    """从 cluster 中提取核心话题名（品牌 + 产品）"""
    for item in cluster:
        title = item["title"]
        # 什么值得买格式：冒号后是品牌+产品
        m = re.search(
            r'[：:]\s*([\u4e00-\u9fff\w][\u4e00-\u9fff\w\s·\-+]{2,40}?)(?:[\d,，。！？、]|\s\d|\s*$|[\[\(（])',
            title
        )
        if m:
            candidate = m.group(1).strip()
            promos = {"今日必买", "88VIP", "淘金币可用", "手慢无", "限时特惠", "百亿补贴",
                      "国家补贴", "京东", "天猫", "拼多多"}
            if candidate not in promos and len(candidate) >= 2:
                return candidate[:40]

    # 尝试提取品牌名（中文2-6字或英文3+字母）
    t = cluster[0]["title"]
    # 先找已知品牌
    brands = re.findall(
        r'(苹果|iPhone|华为|荣耀|小米|红米|酷态科|领普|京东云|ROG|华硕|'
        r'大疆|格力|美的|海尔|索尼|三星|佳能|尼康|'
        r'蔚来|理想|小鹏|比亚迪|问界|极氪|安克|倍思|'
        r'[A-Z][a-zA-Z]{2,})', t
    )
    if brands:
        # 找品牌后面的产品描述
        brand = brands[0]
        m = re.search(re.escape(brand) + r'\s*([\u4e00-\u9fff\w\s·\-+]{0,30})', t)
        if m and m.group(1).strip():
            return (brand + ' ' + m.group(1).strip())[:40]
        return brand

    # fallback: 取前20字
    return t[:30]


# ── Narrative Generation ──
def generate_behavior_shift(cluster):
    """一句话描述人类行为变化"""
    topic = extract_topic(cluster)
    sources = list(set(it["source"] for it in cluster))
    primary = sources[0]

    if "值得买" in primary:
        if has_action(cluster[0]["title"]):
            return f"People are evaluating and comparing {topic} for purchase on social commerce platforms"
        return f"Consumers are showing increasing purchase intent for {topic}"

    if "小红书" in primary:
        return f"People are actively sharing and exploring {topic} on social platforms"

    if any("搜索" in s or "Trends" in s for s in sources):
        return f"People are increasingly searching for information about {topic}"

    return f"Users are showing early engagement with {topic}"


def generate_evidence(cluster):
    """证据描述：来源层级变化，具体化"""
    layers = list(set(it["layer"] for it in cluster))
    sources = list(set(it["source"] for it in cluster))
    min_l, max_l = min(layers), max(layers)
    n = len(cluster)

    # 展示 cluster 中的标题片段作为证据
    sample_titles = [it["title"][:50] for it in cluster[:3]]
    sample_str = " · ".join(sample_titles[:2])

    if min_l == max_l and max_l <= 3:
        return f"Increase in L{min_l} purchase-intent activity on " \
               f"{', '.join(sources[:2])} with {n} related discussions" \
               f"{' (' + sample_str + ')' if n <= 3 else ''}"
    return f"Activity spreading from L{min_l} to L{max_l} across " \
           f"{', '.join(sources[:2])}, {n} mentions showing consumer engagement"


def generate_why_early(cluster):
    """为什么不是已经 mainstream"""
    layers = set(it["layer"] for it in cluster)
    max_l = max(layers)
    if max_l <= 3:
        return "Not yet present in L5/L6 media, still confined to early adopters"
    if max_l <= 4:
        return "Just reaching general content platforms, not yet in mainstream media"
    return "Early stage of broader diffusion, media coverage remains limited"


# ── Main Engine ──
def run_engine():
    """
    v4.0 · Three-Zone Discovery Board Engine
    Output: discovery_board.json with early/seasonal/priced-in zones
    """
    latest_path = DATA_DIR / "latest.json"
    if not latest_path.exists():
        print("[engine] latest.json 不存在，退出")
        return None

    latest = load_json(latest_path)
    items = extract_raw_items(latest)
    print(f"[engine] 原始条目: {len(items)}")

    # ── Filter: keep only behavior-related items ──
    behavior_items = [it for it in items if is_behavior(it["title"])]
    non_behavior_count = len(items) - len(behavior_items)
    print(f"[engine] 行为过滤后: {len(behavior_items)} (排除 {non_behavior_count} 非行为)")

    if not behavior_items:
        # Output empty board
        output = {
            "generated_at": datetime.now(CST).isoformat(),
            "thermo": {
                "heating": [{"rank": 1, "text": "暂无升温信号"}],
                "cooling": [{"rank": 1, "text": "暂无降温信号"}],
                "sector_valuation": {"name": "—", "pe": "—", "percentile_5y": "—", "note": "暂无数据"},
                "cross_opportunity": "暂无",
                "cross_danger": "暂无",
                "crowded_consensus": "暂无"
            },
            "zones": [
                {"id": "early", "label": "早期/异动", "desc": "非日历可预测加速 · 信息差窗口", "cards": []},
                {"id": "seasonal", "label": "季节性提醒", "desc": "日历可预测 · 非信息差", "cards": []},
                {"id": "priced", "label": "已起飞", "desc": "已充分定价 · 追入风险高", "cards": []}
            ],
            "meta": {"total_scanned": len(items), "non_behavior_filtered": non_behavior_count}
        }
        _write_output(output)
        return output

    # ── Group into clusters ──
    clusters = group_items(behavior_items)
    print(f"[engine] 分组产出: {len(clusters)} 个簇")

    # ── Classify each cluster into a zone ──
    early_clusters = []
    seasonal_clusters = []
    priced_clusters = []

    for cluster in clusters:
        # Check seasonal first (highest priority exclusion)
        is_seasonal = any(SEASONAL_KEYWORDS.search(it["title"]) for it in cluster)
        if is_seasonal:
            seasonal_clusters.append(cluster)
            continue

        layers = [it["layer"] for it in cluster]
        max_l = max(layers)
        min_l = min(layers)

        # Early: primarily L1-L3, still confined to early platforms
        if max_l <= 3:
            early_clusters.append(cluster)
        # Priced-in: L5-L6 present, already in mainstream media
        elif min_l >= 5:
            priced_clusters.append(cluster)
        # Mixed: default to early if any L1-L3 present
        else:
            early_clusters.append(cluster)

    print(f"[engine] 分区: early={len(early_clusters)}, seasonal={len(seasonal_clusters)}, priced={len(priced_clusters)}")

    # ── Build cards for each zone ──
    def build_card(cluster, zone):
        topic = extract_topic(cluster)
        sources = list(set(it["source"] for it in cluster))
        source_keys = list(set(it.get("source_key","") for it in cluster))
        max_l = max(it["layer"] for it in cluster)
        min_l = min(it["layer"] for it in cluster)
        n = len(cluster)

        # Diffusion dots
        if max_l <= 2:
            diffusion = "●○○ 早期"
        elif max_l <= 4:
            diffusion = "●●○ 扩散中"
        else:
            diffusion = "●●● 已扩散"

        # Tags
        if zone == "seasonal":
            stage = "季节性"
            badge = "周期性"
        elif zone == "priced":
            stage = "已充分定价"
            badge = "充分定价"
        else:
            stage = "早期信号"
            badge = "新信号"

        # Source pills with layer info
        source_pills = [{"text": s, "type": "pill"} for s in sources]

        # One-liner: use actual title snippet for context
        sample_title = cluster[0]["title"][:60]
        source_str = "、".join(sources[:3])
        if zone == "seasonal":
            one_liner = f"周期性事件——{source_str}出现{topic}相关讨论，去年同期亦有类似热度，属季节性波动，非信息差。"
        elif zone == "priced":
            one_liner = f"已充分定价——{sample_title}。已扩散至{source_str}，价格大概率已反映。"
        else:
            one_liner = f"早期异动——{sample_title}。来源：{source_str}，扩散度{diffusion}。"

        # Logic: try to be specific based on topic
        logic = f"利好：{topic}讨论热度上升 → 相关公司下季度收入有望超预期 · 需验证营收占比"

        # Foot: include source count and sample
        foot = f"{n} 条相关 · {', '.join(sources[:3])}"
        if n > 1:
            foot += f" | 跨{len(sources)}个平台"

        return {
            "id": f"{zone}-{topic[:20]}",
            "tags": {
                "industry": topic[:15],
                "stage": stage,
                "badge": badge,
                "crowding": "待算"
            },
            "headline": topic,
            "diffusion": diffusion,
            "sources": source_pills,
            "one_liner": one_liner,
            "logic": logic,
            "foot": foot,
            "ai_note": "工具初判·待我核实" if zone == "early" else ""
        }

    # Build zones (limit 10 cards per zone)
    zones = [
        {
            "id": "early",
            "label": "早期/异动",
            "desc": "非日历可预测加速 · 信息差窗口",
            "cards": [build_card(c, "early") for c in early_clusters[:10]]
        },
        {
            "id": "seasonal",
            "label": "季节性提醒",
            "desc": "日历可预测 · 非信息差",
            "cards": [build_card(c, "seasonal") for c in seasonal_clusters[:10]]
        },
        {
            "id": "priced",
            "label": "已起飞",
            "desc": "已充分定价 · 追入风险高",
            "cards": [build_card(c, "priced") for c in priced_clusters[:10]]
        }
    ]

    # ── Generate thermo ──
    early_cards = zones[0]["cards"]
    priced_cards = zones[2]["cards"]

    thermo = {
        "heating": [
            {"rank": i + 1, "text": c["headline"][:50]}
            for i, c in enumerate(early_cards[:5])
        ] if early_cards else [{"rank": 1, "text": "暂无升温信号"}],
        "cooling": [
            {"rank": i + 1, "text": c["headline"][:50]}
            for i, c in enumerate(priced_cards[:5])
        ] if priced_cards else [{"rank": 1, "text": "暂无降温信号"}],
        "sector_valuation": {
            "name": "待更新",
            "pe": "—",
            "percentile_5y": "—",
            "note": "自动生成·待核实"
        },
        "cross_opportunity": "早期区信号存在信息差机会" if early_cards else "暂无",
        "cross_danger": "已起飞区信号追入风险高" if priced_cards else "暂无",
        "crowded_consensus": "待分析"
    }

    # ── Output ──
    now = datetime.now(CST)
    output = {
        "generated_at": now.isoformat(),
        "thermo": thermo,
        "zones": zones,
        "meta": {
            "total_scanned": len(items),
            "non_behavior_filtered": non_behavior_count,
            "clusters": len(clusters),
            "zones_count": {
                "early": len(early_clusters),
                "seasonal": len(seasonal_clusters),
                "priced": len(priced_clusters)
            },
            "data_time": now.strftime("%Y-%m-%d %H:%M") + " CST"
        }
    }

    _write_output(output)

    # ── Summary ──
    print(f"\n[engine] ===== DISCOVERY BOARD v4.0 =====")
    for zone in zones:
        print(f"  {zone['label']}: {len(zone['cards'])} cards")
    print(f"  温度计 升温: {len(thermo['heating'])} 条 | 降温: {len(thermo['cooling'])} 条")

    return output


def _write_output(output):
    """Write discovery_board.json (v4.0 three-zone format)"""
    output_path = DATA_DIR / "discovery_board.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    import shutil
    # Copy to dist/data/ for CloudStudio deployment
    dist_dir = ROOT / "dist" / "data"
    dist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_path, dist_dir / "discovery_board.json")

    # Copy to data/ for local preview
    public_dir = ROOT / "data"
    public_dir.mkdir(exist_ok=True)
    shutil.copy2(output_path, public_dir / "discovery_board.json")

    print(f"[engine] 已写入 {output_path}")


def main():
    """Main entry point — v4.0 three-zone discovery board"""
    output = run_engine()
    if output is None:
        return 1
    zones = output.get("zones", [])
    total_cards = sum(len(z.get("cards", [])) for z in zones)
    if total_cards == 0:
        print("[engine] 今日无信号，输出空看板")
    else:
        print(f"[engine] 输出 {total_cards} 张卡片")
    return 0


if __name__ == "__main__":
    sys.exit(main())
