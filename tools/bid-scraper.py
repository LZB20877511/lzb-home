# 投标监控爬虫 v3 - 优化关键词 + 地区过滤
# 用法：python tools/bid-scraper.py

import json, os, re, time, ssl, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta
from html import unescape

CST = timezone(timedelta(hours=8))
OUTPUT_DIR = "data"
TIMEOUT = 25

# === 地区 zoneId（从 ccgp 搜索页面提取） ===
# 广东 = 440000, 深圳 = 440300
ZONE_IDS = {
    "广东": "440000",
    "深圳": "440300",
}

# === 搜索关键词组（经过测试优化） ===
# 第一组：核心业务关键词（宽泛，命中率高）
CORE_KEYWORDS = [
    "信息化",           # 能覆盖：信息化监理、信息化项目、信息化建设
    "信息系统",         # 能覆盖：信息系统监理、信息系统工程
    "第三方检测",       # 第三方检测
]

# 第二组：精确词（单独搜，补充）
EXACT_KEYWORDS = [
    "信息化工程监理",
    "初步设计与概算",
    "项目建议书",
    "项目管理服务",
]

ALL_KEYWORDS = CORE_KEYWORDS + EXACT_KEYWORDS

# 目标地区
# 省份/城市级匹配（用于粗筛）
TARGET_PROVINCES = ["广东", "深圳", "广东省", "深圳市"]
# 区县级匹配（仅在确认是广东/深圳后才用）
TARGET_DISTRICTS = ["宝安", "龙岗", "南山", "福田", "罗湖", "龙华", "光明", "坪山", "盐田",
                    "广州", "东莞", "佛山", "珠海", "惠州", "中山", "江门", "肇庆", "清远",
                    "汕头", "湛江", "茂名", "韶关", "河源", "梅州", "潮州", "揭阳", "云浮", "阳江", "汕尾"]

# 排除词（不是IT类监理的项目）
EXCLUDE_WORDS = [
    # 土木工程类
    "公路", "道路", "桥梁", "隧道", "排水", "供水", "供暖", "燃气",
    "农田", "水利", "防汛", "造林", "绿化", "园林", "林业", "农业",
    "装修", "装饰", "房屋修缮", "外墙", "屋面",
    "施工监理", "工程监理", "建筑", "市政",
    # 非IT服务类
    "病理", "医疗", "检验", "体检", "食品", "餐饮", "食堂",
    "保洁", "保安", "物业", "垃圾", "环卫",
]

HD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://search.ccgp.gov.cn/",
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def fetch(url):
    req = urllib.request.Request(url, headers=HD)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = resp.read()
            for enc in ['utf-8', 'gbk', 'gb2312']:
                try: return raw.decode(enc)
                except: pass
            return raw.decode('utf-8', errors='replace')
    except Exception as e:
        return ""


def search_ccgp(keyword, zone_name=None):
    """搜索政府采购网，可选指定地区"""
    zone_id = ZONE_IDS.get(zone_name, "") if zone_name else ""
    display = zone_name if zone_name else ""
    label = f"{keyword}{'@'+zone_name if zone_name else ''}"
    print(f"  🔍 {label}...", end=" ")
    
    start = (datetime.now(CST) - timedelta(days=60)).strftime("%Y:%m:%d")
    end = datetime.now(CST).strftime("%Y:%m:%d")
    
    items = []
    for page in range(1, 4):
        kw = urllib.parse.quote(keyword)
        url = (f"https://search.ccgp.gov.cn/bxsearch"
               f"?searchtype=1&page_index={page}&bidSort=0"
               f"&buyerName=&projectId=&pinMu=0&bidType=0&dbselect=bidx"
               f"&kw={kw}"
               f"&start_time={urllib.parse.quote(start)}"
               f"&end_time={urllib.parse.quote(end)}"
               f"&timeType=6"
               f"&displayZone={urllib.parse.quote(display)}"
               f"&zoneId={zone_id}"
               f"&pppStatus=0&agentName=")
        html = fetch(url)
        if not html: break
        
        page_items = parse_results(html, keyword, zone_name)
        items.extend(page_items)
        if len(page_items) < 15 and page > 1:
            break
        time.sleep(1.5)
    
    print(f"{len(items)}条")
    return items


def parse_results(html, keyword, zone_name=None):
    """解析搜索结果"""
    items = []
    
    # 匹配链接和标题
    link_pattern = re.compile(
        r'<a\s+href="(https?://www\.ccgp\.gov\.cn/cggg/[^"]+)"[^>]*>\s*(.+?)\s*</a>',
        re.DOTALL
    )
    
    for link, title in link_pattern.findall(html):
        title = re.sub(r'<[^>]+>', '', unescape(title)).strip()
        if not title or len(title) < 5:
            continue
        
        # 排除非IT类
        if any(w in title for w in EXCLUDE_WORDS):
            continue
        
        # 找上下文
        pos = html.find(link)
        context = html[pos:pos + 800] if pos > 0 else ""
        
        # 日期
        date_match = re.search(r'(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})', context)
        date_str = date_match.group(1).replace('.', '-').split()[0] if date_match else datetime.now(CST).strftime("%Y-%m-%d")
        
        # 地区
        region_match = re.search(r'\|\s*([^\|]{2,10}?)\s*\|\s*\*?\*?', context)
        region = region_match.group(1).strip() if region_match else ""
        
        # 品目分类
        cat_match = re.search(r'服务/信息技术服务/([^*]+)', context)
        category = cat_match.group(1).strip() if cat_match else ""
        
        # 指定了地区过滤
        if zone_name and zone_name not in region:
            continue
        
        # 判断是否为IT类（信息类）
        is_it = any(w in title for w in ["信息", "软件", "数据", "网络", "系统", "数字", "智慧", "云", "平台", "APP", "IT"])
        is_it = is_it or "信息技术" in category
        
        items.append({
            "title": title,
            "link": link,
            "date": date_str,
            "region": region,
            "category": category,
            "source": "中国政府采购网",
            "keyword": keyword,
            "is_it": is_it,
        })
    
    return items


def search_shenzhen():
    """深圳政府采购平台"""
    print("  🔍 深圳采购平台...", end=" ")
    items = []
    url = "http://zfcg.szggzy.com:8081/gsgg/002001/002001002/list.html"
    html = fetch(url)
    if not html:
        print("无法访问")
        return []
    
    link_pattern = re.compile(
        r'href="(/gsgg/002001/002001002/\d+/[^"]+\.html)"[^>]*title="([^"]+)"',
        re.DOTALL
    )
    matches = link_pattern.findall(html)
    if not matches:
        link_pattern2 = re.compile(
            r'<a[^>]*href="([^"]*002001002[^"]*)"[^>]*>([^<]{10,200})</a>',
            re.DOTALL
        )
        matches = link_pattern2.findall(html)
    
    for link, title in matches:
        title = re.sub(r'<[^>]+>', '', unescape(title)).strip()
        if not link.startswith("http"):
            link = "http://zfcg.szggzy.com:8081" + link
        
        # 判断相关性
        is_relevant = any(w in title for w in [
            "信息", "软件", "数据", "网络", "系统", "数字", "智慧", "云",
            "监理", "检测", "测评", "咨询", "设计", "开发", "运维", "安全"
        ])
        if not is_relevant:
            continue
        
        for kw in ALL_KEYWORDS:
            kw_s = kw.replace("服务", "").replace("信息化", "信息")
            if any(t in title for t in [kw, kw_s]):
                items.append({
                    "title": title,
                    "link": link,
                    "date": datetime.now(CST).strftime("%Y-%m-%d"),
                    "region": "深圳",
                    "source": "深圳政府采购平台",
                    "keyword": kw,
                    "is_it": True,
                })
                break
    
    print(f"{len(items)}条")
    return items[:30]


def save(items):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    seen = set()
    unique = []
    for item in items:
        key = item["title"][:30]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    unique.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    data = {
        "updated": datetime.now(CST).isoformat(),
        "source": "政府采购招标公告",
        "count": len(unique),
        "keywords": ALL_KEYWORDS,
        "items": unique
    }
    path = os.path.join(OUTPUT_DIR, "bids.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 bids.json: {len(unique)} 条")
    return unique


def gen_summary(items):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    path = os.path.join(OUTPUT_DIR, "bids-summary.html")
    sz = [i for i in items if "深圳" in (i.get("region") or "")]
    gd = [i for i in items if "广东" in (i.get("region") or "") and "深圳" not in (i.get("region") or "")]
    it_items = [i for i in items if i.get("is_it")]
    
    h = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>招标信息 - LZB</title>
<style>body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;max-width:900px;margin:20px auto;padding:20px;background:#0d1117;color:#c9d1d9;font-size:14px;line-height:1.8}}
h1{{color:#d2991d;font-size:18px}}.meta{{color:#8b949e;font-size:12px;margin-bottom:16px}}
h2{{color:#d2991d;font-size:15px;border-bottom:1px solid #30363d;padding-bottom:6px;margin-top:24px}}
.item{{padding:8px 0;border-bottom:1px solid rgba(48,54,61,.5)}}
.item a{{color:#c9d1d9;text-decoration:none}}.item a:hover{{color:#d2991d}}
.info{{font-size:11px;color:#8b949e;margin-top:2px}}.it{{color:#58a6ff}}
</style></head>
<body>
<h1>📋 招标信息聚合 - 广东/深圳</h1>
<div class="meta">生成时间：{now} | 合计 {len(items)} 条 | IT类 {len(it_items)} 条</div>

<h2>🖥️ IT/信息类（{len(it_items)} 条）</h2>
"""
    for item in it_items[:50]:
        cat = f' [{item.get("category","")}]' if item.get("category") else ''
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} | {item.get("source","")} | {item.get("region","")}{cat}</div></div>\n'
    
    h += f'<h2>📍 深圳市（{len(sz)} 条）</h2>'
    for item in sz[:30]:
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} | {item.get("source","")}</div></div>\n'
    
    h += f'<h2>📍 广东省其他（{len(gd)} 条）</h2>'
    for item in gd[:50]:
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} | {item.get("source","")} | {item.get("region","")}</div></div>\n'
    
    h += '</body></html>'
    with open(path, "w", encoding="utf-8") as f:
        f.write(h)
    print(f"  📄 bids-summary.html")


def main():
    print("=" * 50)
    print(f"  投标监控爬虫 v3  {datetime.now(CST):%Y-%m-%d %H:%M}")
    print("=" * 50)
    
    all_items = []
    
    for kw in CORE_KEYWORDS:
        items = search_ccgp(kw)
        # 从全国结果中筛选广东/深圳相关的
        all_regions = TARGET_PROVINCES + TARGET_DISTRICTS
        target = [i for i in items if any(r in (i.get("region") or "") + (i.get("title") or "") for r in all_regions)]
        if target:
            all_items.extend(target)
        time.sleep(2)
    
    for kw in EXACT_KEYWORDS:
        for zone in ["广东", "深圳"]:
            items = search_ccgp(kw, zone)
            all_items.extend(items)
            time.sleep(2)
    
    # 深圳本地平台
    all_items.extend(search_shenzhen())
    
    unique = save(all_items)
    gen_summary(unique)
    
    it_count = len([i for i in unique if i.get("is_it")])
    print(f"\n✅ 完成: {len(all_items)} → {len(unique)} 条 (IT类 {it_count})")


if __name__ == "__main__":
    import sys
    main()
