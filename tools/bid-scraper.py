# 投标监控爬虫 v2 - 简化版
# 用法：python tools/bid-scraper.py

import json, os, re, time, ssl, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta
from html import unescape

CST = timezone(timedelta(hours=8))
OUTPUT_DIR = "data"
TIMEOUT = 20

KEYWORDS = [
    "信息系统监理", "信息化监理", "信息化监理服务",
    "初步设计与概算", "项目建议书",
    "第三方检测", "检测服务", "项目管理服务",
]

TARGET_REGIONS = ["广东", "深圳", "广州", "东莞", "佛山", "珠海", "惠州", "中山",
                  "宝安", "龙岗", "南山", "福田", "罗湖", "龙华", "光明", "坪山", "盐田"]

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
    except: return ""


def search_ccgp(keyword):
    print(f"  🔍 搜索: {keyword}")
    items = []
    start = (datetime.now(CST) - timedelta(days=90)).strftime("%Y:%m:%d")
    end = datetime.now(CST).strftime("%Y:%m:%d")

    for page in range(1, 3):
        kw = urllib.parse.quote(keyword)
        url = (f"https://search.ccgp.gov.cn/bxsearch"
               f"?searchtype=1&page_index={page}&bidSort=0"
               f"&buyerName=&projectId=&pinMu=0&bidType=0&dbselect=bidx"
               f"&kw={kw}&start_time={urllib.parse.quote(start)}"
               f"&end_time={urllib.parse.quote(end)}"
               f"&timeType=6&displayZone=&zoneId=&pppStatus=0&agentName=")
        html = fetch(url)
        if not html: break

        # 解析方法：找 ul.vule 或 li 里面的链接
        page_items = parse_results(html, keyword)
        if not page_items and page > 1:
            break
        items.extend(page_items)
        time.sleep(1.5)

    target = [i for i in items if any(r in (i.get("region") or "") for r in ["广东", "深圳"]) or any(r in i.get("title", "") for r in TARGET_REGIONS)]
    print(f"     → {len(target)} 条广东/深圳")
    return target


def parse_results(html, keyword):
    items = []
    # 从WebFetch结果看，结构是: <a href="...">标题</a> 后跟着日期 | 采购人 | 代理机构 | **类型** | 地区 |
    # 匹配: <a href="http://www.ccgp.gov.cn/cggg/dfgg/...">标题</a>
    link_pattern = re.compile(
        r'<a\s+href="(https?://www\.ccgp\.gov\.cn/cggg/[^"]+)"[^>]*>\s*(.+?)\s*</a>',
        re.DOTALL
    )
    for link, title in link_pattern.findall(html):
        title = re.sub(r'<[^>]+>', '', unescape(title)).strip()
        if not title or len(title) < 5:
            continue

        # 在这个链接附近找日期和地区
        pos = html.find(link)
        if pos < 0: pos = html.find(re.escape(link[:60]))
        context = html[pos:pos + 600] if pos > 0 else ""

        # 提取日期: 2026.06.28 20:01:25
        date_match = re.search(r'(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})', context)
        date_str = date_match.group(1) if date_match else ""

        # 提取地区: | 广东 | 或 | 深圳 |
        region_match = re.search(r'\|\s*([^\|]{2,10}?)\s*\|', context)
        region = region_match.group(1).strip() if region_match else ""

        items.append({
            "title": title,
            "link": link,
            "date": date_str.replace('.', '-').split()[0] if date_str else datetime.now(CST).strftime("%Y-%m-%d"),
            "region": region,
            "source": "中国政府采购网",
            "keyword": keyword
        })

    return items


def search_shenzhen():
    print("  🔍 搜索: 深圳政府采购平台")
    items = []
    # 深圳采购平台公告列表
    url = "http://zfcg.szggzy.com:8081/gsgg/002001/002001002/list.html"
    html = fetch(url)
    if not html:
        print("     → 无法访问")
        return []

    # 匹配: href="/gsgg/002001/002001002/...html" title="标题"
    link_pattern = re.compile(
        r'href="(/gsgg/002001/002001002/\d+/[^"]+\.html)"[^>]*title="([^"]+)"',
        re.DOTALL
    )
    matches = link_pattern.findall(html)
    if not matches:
        # 备用匹配
        link_pattern2 = re.compile(
            r'<a[^>]*href="([^"]*002001002[^"]*)"[^>]*>([^<]{10,200})</a>',
            re.DOTALL
        )
        matches = link_pattern2.findall(html)

    for link, title in matches:
        title = re.sub(r'<[^>]+>', '', unescape(title)).strip()
        if not link.startswith("http"):
            link = "http://zfcg.szggzy.com:8081" + link

        # 关键词匹配
        matched_kw = None
        for kw in KEYWORDS:
            kw_short = kw.replace("服务", "").replace("信息化", "信息")
            if any(t in title for t in [kw, kw_short]):
                matched_kw = kw
                break

        if matched_kw:
            items.append({
                "title": title,
                "link": link,
                "date": datetime.now(CST).strftime("%Y-%m-%d"),
                "region": "深圳",
                "source": "深圳政府采购平台",
                "keyword": matched_kw
            })

    print(f"     → {len(items)} 条")
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
        "keywords": KEYWORDS,
        "regions": TARGET_REGIONS,
        "items": unique
    }
    path = os.path.join(OUTPUT_DIR, "bids.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 {path}: {len(unique)} 条")
    return unique


def gen_summary(items):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    path = os.path.join(OUTPUT_DIR, "bids-summary.html")
    sz = [i for i in items if "深圳" in (i.get("region") or "")]
    gd = [i for i in items if "广东" in (i.get("region") or "") and "深圳" not in (i.get("region") or "")]

    h = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>招标信息 - LZB</title>
<style>body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;max-width:900px;margin:20px auto;padding:20px;background:#0d1117;color:#c9d1d9;font-size:14px;line-height:1.8}}
h1{{color:#d2991d;font-size:18px}}.meta{{color:#8b949e;font-size:12px;margin-bottom:16px}}
h2{{color:#d2991d;font-size:15px;border-bottom:1px solid #30363d;padding-bottom:6px;margin-top:24px}}
.item{{padding:8px 0;border-bottom:1px solid rgba(48,54,61,.5)}}
.item a{{color:#c9d1d9;text-decoration:none}}.item a:hover{{color:#d2991d}}
.info{{font-size:11px;color:#8b949e;margin-top:2px}}
</style></head>
<body>
<h1>📋 招标信息聚合 - 广东/深圳</h1>
<div class="meta">生成时间：{now} | 合计 {len(items)} 条</div>
<h2>📍 深圳市（{len(sz)} 条）</h2>
"""
    for item in sz[:30]:
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} · {item.get("source","")}</div></div>\n'
    h += f'<h2>📍 广东省（{len(gd)} 条）</h2>'
    for item in gd[:50]:
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} · {item.get("source","")} | {item.get("region","")}</div></div>\n'
    h += '</body></html>'
    with open(path, "w", encoding="utf-8") as f:
        f.write(h)
    print(f"  📄 {path}")


def main():
    print("=" * 50)
    print(f"  投标监控爬虫 v2  {datetime.now(CST):%Y-%m-%d %H:%M}")
    print("=" * 50)

    all_items = []
    print("\n📡 中国政府采购网...")
    for kw in KEYWORDS:
        items = search_ccgp(kw)
        all_items.extend(items)
        time.sleep(2)

    print("\n📡 深圳政府采购平台...")
    all_items.extend(search_shenzhen())

    unique = save(all_items)
    gen_summary(unique)
    print(f"\n✅ 完成: {len(all_items)} → 去重 {len(unique)} 条")


if __name__ == "__main__":
    import sys
    main()
