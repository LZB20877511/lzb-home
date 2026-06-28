# 投标监控爬虫 - 政府采购招标信息采集
# 数据来源：中国政府采购网 + 深圳政府采购平台
# 用法：python tools/bid-scraper.py

import json, os, re, time, ssl, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta
from html import unescape

# 北京时间
CST = timezone(timedelta(hours=8))
OUTPUT_DIR = "data"
MAX_PAGES = 3          # 每个关键词最多翻页数
TIMEOUT = 25
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0"

def e(s): return urllib.parse.quote(s)

# ====== 搜索关键词 ======
KEYWORDS = [
    "信息系统监理",
    "信息化监理",
    "信息化监理服务",
    "初步设计与概算",
    "项目建议书",
    "第三方检测",
    "检测服务",
    "项目管理服务",
]

# 目标地区关键词（用于标题/内容过滤）
TARGET_REGIONS = ["广东", "深圳", "广州", "东莞", "佛山", "珠海", "惠州", "中山", 
                  "宝安", "龙岗", "南山", "福田", "罗湖", "龙华", "光明", "坪山", "盐田"]

# ====== HTTP 请求 ======
def fetch(url, encoding='utf-8'):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = resp.read()
            try: return raw.decode(encoding)
            except: return raw.decode('gbk', errors='replace')
    except Exception as e:
        return ""

# ====== 中国政府采购网搜索 ======
def search_ccgp(keyword):
    """搜索中国政府采购网"""
    items = []
    print(f"  🔍 搜索: {keyword}")
    
    start_date = (datetime.now(CST) - timedelta(days=60)).strftime("%Y:%m:%d")
    end_date = datetime.now(CST).strftime("%Y:%m:%d")
    
    for page in range(1, MAX_PAGES + 1):
        kw_enc = urllib.parse.quote(keyword)
        url = (f"https://search.ccgp.gov.cn/bxsearch"
               f"?searchtype=1&page_index={page}&bidSort=0"
               f"&buyerName=&projectId=&pinMu=0&bidType=0&dbselect=bidx"
               f"&kw={kw_enc}"
               f"&start_time={urllib.parse.quote(start_date)}"
               f"&end_time={urllib.parse.quote(end_date)}"
               f"&timeType=6&displayZone=&zoneId=&pppStatus=0&agentName=")
        
        html = fetch(url)
        if not html: break
        
        page_items = parse_ccgp_results(html, keyword)
        items.extend(page_items)
        
        # 如果页内没有目标地区的结果，提前结束
        if len(page_items) == 0 and page > 1:
            break
        
        time.sleep(1.5)
    
    print(f"     → {len(items)} 条广东/深圳相关")
    return items

def parse_ccgp_results(html, keyword):
    """解析搜索结果页面"""
    items = []
    # 提取每个公告条目：通过链接和区域信息定位
    # 匹配: <a href="...">标题</a> ... | 广东 | 或 | 深圳 |
    pattern = re.compile(
        r'<a\s+href="(http://www\.ccgp\.gov\.cn/cggg/dfgg/[^"]+)"[^>]*>([^<]+)</a>'
        r'.*?(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})'
        r'.*?\|\s*([^\|]+?)\s*\|',
        re.DOTALL
    )
    matches = pattern.findall(html)
    
    for link, title, date_str, region in matches:
        title = unescape(title.strip())
        region = region.strip()
        
        # 检查是否为目标地区
        if not any(r in region for r in ["广东", "深圳"]):
            # 也检查标题中是否包含目标地区
            if not any(r in title for r in TARGET_REGIONS):
                continue
        
        # 排除废标/更正公告（如果关键词要求排除）
        # 保留所有，用户可以从标签区分
        
        pub_date = date_str.replace('.', '-').split()[0]
        
        items.append({
            "title": title,
            "link": link,
            "date": pub_date,
            "region": region,
            "source": "中国政府采购网",
            "keyword": keyword
        })
    
    return items

# ====== 深圳政府采购平台 ======
def search_shenzhen():
    """直接爬深圳政府采购平台招标公告列表"""
    items = []
    print(f"  🔍 搜索: 深圳政府采购平台")
    
    # 深圳采购平台 - 公开招标公告列表
    sz_urls = [
        "http://zfcg.szggzy.com:8081/gsgg/002001/002001002/list.html",
    ]
    
    for url in sz_urls:
        html = fetch(url)
        if not html: continue
        
        # 解析列表页面
        # 深圳平台通常用 <li> 或 <tr> 结构
        sz_items = parse_sz_results(html)
        items.extend(sz_items)
    
    # 对每个结果做关键词匹配
    matched = []
    for item in items:
        title = item["title"]
        for kw in KEYWORDS:
            if any(t in title for t in [kw, kw.replace("服务", ""), kw.replace("信息化", "信息")]):
                item["keyword"] = kw
                matched.append(item)
                break
    
    print(f"     → {len(matched)} 条匹配关键词")
    return matched[:50]

def parse_sz_results(html):
    """解析深圳采购平台列表"""
    items = []
    # 尝试多种列表格式
    # 格式1: <li><a href="...">标题</a><span>日期</span></li>
    pattern1 = re.compile(
        r'<a\s+href="([^"]*002001002[^"]*)"[^>]*>([^<]{10,200})</a>',
        re.DOTALL
    )
    # 格式2: <a> 后面跟 span.date
    pattern2 = re.compile(
        r'href="(/gsgg/002001/002001002/\d+/\w+\.html)"[^>]*title="([^"]+)"',
        re.DOTALL
    )
    
    for pattern in [pattern2, pattern1]:
        matches = pattern.findall(html)
        if matches:
            for link, title in matches:
                title = unescape(title.strip())
                if not link.startswith("http"):
                    link = "http://zfcg.szggzy.com:8081" + link
                items.append({
                    "title": title,
                    "link": link,
                    "date": datetime.now(CST).strftime("%Y-%m-%d"),
                    "region": "深圳",
                    "source": "深圳政府采购平台"
                })
            break
    
    return items

# ====== 保存和汇总 ======
def save(items):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 去重（按标题去重）
    seen = set()
    unique = []
    for item in items:
        key = item["title"][:30]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    
    # 按日期倒序
    unique.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    data = {
        "updated": datetime.now(CST).isoformat(),
        "source": "政府采购招标公告",
        "count": len(unique),
        "keywords": KEYWORDS,
        "regions": TARGET_REGIONS,
        "items": unique
    }
    
    path = os.path.join(OUTPUT_DIR, "bids.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 {path}: {len(unique)} 条")
    return unique

# ====== 生成简单摘要页 ======
def gen_summary(items):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    path = os.path.join(OUTPUT_DIR, "bids-summary.html")
    
    # 按地区分组
    sz_items = [i for i in items if "深圳" in (i.get("region") or "")]
    gd_items = [i for i in items if "广东" in (i.get("region") or "") and "深圳" not in (i.get("region") or "")]
    
    h = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>投标监控 - LZB</title>
<style>
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;max-width:900px;margin:20px auto;padding:20px;background:#0d1117;color:#c9d1d9;font-size:14px;line-height:1.8}}
h1{{color:#58a6ff;font-size:18px}}
.meta{{color:#8b949e;font-size:12px;margin-bottom:16px}}
.section{{margin:24px 0}}
.section h2{{color:#58a6ff;font-size:15px;border-bottom:1px solid #30363d;padding-bottom:6px}}
.item{{padding:8px 0;border-bottom:1px solid rgba(48,54,61,.5)}}
.item a{{color:#c9d1d9;text-decoration:none;font-weight:500}}
.item a:hover{{color:#58a6ff}}
.item .info{{font-size:11px;color:#8b949e;margin-top:2px}}
.new-badge{{display:inline-block;background:#58a6ff;color:#fff;font-size:9px;padding:1px 5px;border-radius:6px;margin-left:6px}}
</style>
</head>
<body>
<h1>📋 投标监控 - 广东/深圳</h1>
<div class="meta">生成时间：{now} | 合计 {len(items)} 条 | 监控关键词：{", ".join(KEYWORDS[:4])}等</div>

<div class="section">
<h2>📍 深圳市（{len(sz_items)} 条）</h2>
"""
    for item in sz_items[:30]:
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} · {item.get("source","")} · 关键词：{item.get("keyword","")}</div></div>\n'
    
    h += f"""
</div>
<div class="section">
<h2>📍 广东省（{len(gd_items)} 条）</h2>
"""
    for item in gd_items[:50]:
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} · {item.get("source","")} · 关键词：{item.get("keyword","")}</div></div>\n'
    
    h += '</div></body></html>'
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(h)
    print(f"  📄 摘要页: {path}")

# ====== 主流程 ======
def main():
    print("=" * 50)
    print(f"  投标监控爬虫  {datetime.now(CST):%Y-%m-%d %H:%M}")
    print(f"  关键词: {', '.join(KEYWORDS[:4])}...")
    print(f"  地区: 广东省 + 深圳市")
    print("=" * 50)
    
    all_items = []
    
    # 1. 中国政府采购网 - 多关键词搜索
    print("\n📡 中国政府采购网...")
    for kw in KEYWORDS:
        items = search_ccgp(kw)
        all_items.extend(items)
        time.sleep(2)  # 避免请求过快
    
    # 2. 深圳政府采购平台
    print("\n📡 深圳政府采购平台...")
    sz_items = search_shenzhen()
    all_items.extend(sz_items)
    
    # 保存
    unique = save(all_items)
    
    # 生成摘要
    gen_summary(unique)
    
    print(f"\n✅ 投标监控采集完成: {len(all_items)} → 去重 {len(unique)} 条")
    print(f"   深圳: {len([i for i in unique if '深圳' in (i.get('region') or '')])} 条")
    print(f"   广东: {len([i for i in unique if '广东' in (i.get('region') or '') and '深圳' not in (i.get('region') or '')])} 条")

if __name__ == "__main__":
    import sys
    main()
