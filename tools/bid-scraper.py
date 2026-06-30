# 投标监控爬虫 v4 - 修复关键词策略
# 核心发现：ccgp搜索不支持组合关键词，需要用宽泛词搜索后按IT关键词筛选
import json, os, re, time, ssl, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta
from html import unescape

CST = timezone(timedelta(hours=8))
OUTPUT_DIR = "data"
TIMEOUT = 25

# 核心搜索词（宽泛，用于搜索）
SEARCH_KW = ["监理", "信息化", "信息系统", "第三方检测"]

# IT关键词（用于从监理结果中筛选IT类）
IT_WORDS = ["信息", "软件", "数据", "系统", "数字", "智慧", "网络", "平台", "云平台",
            "APP", "IT", "信息化", "互联网", "通讯", "通信", "计算机", "电子政务",
            "政务", "运维", "运营", "测评", "等保", "安全测评", "密码"]

# 广东/深圳关键词
GD_REGIONS = ["广东", "深圳", "广州", "东莞", "佛山", "珠海", "惠州", "中山",
              "江门", "肇庆", "清远", "汕头", "湛江", "茂名", "韶关", "河源",
              "宝安", "龙岗", "南山", "福田", "罗湖", "龙华", "光明", "坪山",
              "广东省", "深圳市"]

# 排除词（非IT类的项目）
EXCLUDE = ["公路", "道路", "桥梁", "隧道", "排水", "供水", "供暖", "燃气",
           "农田", "水利", "防汛", "造林", "绿化", "园林", "林业", "农业",
           "装修", "装饰", "修缮", "外墙", "屋面", "基坑", "边坡", "桩基",
           "病理", "医疗", "检验标本", "体检", "食品", "餐饮", "食堂",
           "保洁", "保安", "物业", "垃圾", "环卫", "排污"]

# ccgp专用Header（简洁，避免触发反爬）
CCGP_HD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://search.ccgp.gov.cn/",
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def fetch_ccgp(url):
    """专用ccgp请求"""
    req = urllib.request.Request(url, headers=CCGP_HD)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = resp.read()
            for enc in ['utf-8', 'gbk', 'gb2312']:
                try:
                    return raw.decode(enc)
                except:
                    pass
            return raw.decode('utf-8', errors='replace')
    except:
        return ""


def fetch_sz(url):
    """深圳平台请求"""
    hd = dict(CCGP_HD)
    hd["Referer"] = "http://zfcg.szggzy.com:8081/"
    req = urllib.request.Request(url, headers=hd)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = resp.read()
            for enc in ['utf-8', 'gbk', 'gb2312']:
                try:
                    return raw.decode(enc)
                except:
                    pass
            return raw.decode('utf-8', errors='replace')
    except:
        return ""


def search_ccgp(keyword, pages=3):
    """搜索ccgp，返回标题+链接+日期列表"""
    items = []
    start = (datetime.now(CST) - timedelta(days=90)).strftime("%Y:%m:%d")
    end = datetime.now(CST).strftime("%Y:%m:%d")

    for page in range(1, pages + 1):
        kw = urllib.parse.quote(keyword)
        url = (f"https://search.ccgp.gov.cn/bxsearch"
               f"?searchtype=1&page_index={page}&bidSort=0"
               f"&buyerName=&projectId=&pinMu=0&bidType=0&dbselect=bidx"
               f"&kw={kw}"
               f"&start_time={urllib.parse.quote(start)}"
               f"&end_time={urllib.parse.quote(end)}"
               f"&timeType=6&displayZone=&zoneId=&pppStatus=0&agentName=")
        html = fetch_ccgp(url)
        if not html or len(html) < 3000:
            break

        # 解析链接
        page_items = parse_ccgp_page(html, keyword)
        items.extend(page_items)

        if len(page_items) < 10 and page > 1:
            break
        time.sleep(1.5)

    return items


def parse_ccgp_page(html, keyword):
    """从ccgp搜索结果页提取条目"""
    items = []
    # 匹配所有 bid 链接
    link_pat = re.compile(
        r'<a\s+href="(http://www\.ccgp\.gov\.cn/cggg/[^"]+)"[^>]*>\s*(.+?)\s*</a>',
        re.DOTALL
    )
    for link, title_raw in link_pat.findall(html):
        title = re.sub(r'<[^>]+>', '', unescape(title_raw)).strip()
        if len(title) < 5:
            continue

        # 在链接附近找日期
        pos = html.find(link)
        ctx_text = html[pos:pos + 600] if pos > 0 else ""

        date_m = re.search(r'(\d{4}\.\d{2}\.\d{2})\s+\d{2}:\d{2}', ctx_text)
        date_str = date_m.group(1).replace('.', '-') if date_m else ""

        # 找品目分类
        cat_m = re.search(r'服务/([^*]+)', ctx_text)
        category = cat_m.group(1).strip() if cat_m else ""

        items.append({
            "title": title,
            "link": link,
            "date": date_str or datetime.now(CST).strftime("%Y-%m-%d"),
            "region_raw": ctx_text,  # 暂存，后续精确提取
            "category": category,
            "source": "中国政府采购网",
            "search_kw": keyword,
        })

    return items


def extract_region(ctx_text):
    """从上下文提取地区"""
    m = re.search(r'\|\s*([^\|]{2,8}?)\s*\|', ctx_text)
    return m.group(1).strip() if m else ""


def is_target_region(item):
    """判断是否广东/深圳"""
    region = extract_region(item.get("region_raw", ""))
    title = item.get("title", "")

    # 先看地区字段
    if any(r in region for r in ["广东", "深圳"]):
        item["region"] = region
        return True

    # 再看标题
    for r in GD_REGIONS:
        if r in title:
            # 排除同名异地：唐山≠中山，龙华区vs龙华中学
            if r in ["龙华", "南山", "福田", "罗湖", "宝安", "光明", "坪山", "盐田", "龙岗"]:
                # 区名必须和广东/深圳同时出现才认
                if not any(p in title for p in ["深圳", "广东", "广州"]):
                    continue
            item["region"] = r
            return True

    return False


def is_it_item(item):
    """判断是否IT/信息类"""
    title = item.get("title", "")
    category = item.get("category", "")
    text = title + " " + category

    # 排除非IT类
    if any(w in title for w in EXCLUDE):
        return False

    # IT关键词匹配
    return any(w in text for w in IT_WORDS)


def search_shenzhen():
    """深圳政府采购平台"""
    print("  🔍 深圳采购平台...")
    items = []
    for page in [1, 2]:
        url = f"http://zfcg.szggzy.com:8081/gsgg/002001/002001002/{page}.html" if page > 1 else \
              "http://zfcg.szggzy.com:8081/gsgg/002001/002001002/list.html"
        html = fetch_sz(url)
        if not html:
            print("    → 无法访问")
            break

        # 解析
        pat = re.compile(r'title="([^"]+)"[^>]*onclick[^>]*href="(/gsgg/[^"]+)"', re.DOTALL)
        matches = pat.findall(html)
        if not matches:
            pat2 = re.compile(r'href="(/gsgg/002001/002001002/[^"]+)"[^>]*>([^<]{10,200})<', re.DOTALL)
            matches = [(t, l) for l, t in pat2.findall(html)]

        for title, link in matches:
            title = re.sub(r'<[^>]+>', '', unescape(title)).strip()
            if len(title) < 5:
                continue
            if not link.startswith("http"):
                link = "http://zfcg.szggzy.com:8081" + link

            if any(w in title for w in IT_WORDS):
                items.append({
                    "title": title,
                    "link": link,
                    "date": datetime.now(CST).strftime("%Y-%m-%d"),
                    "region": "深圳",
                    "source": "深圳政府采购平台",
                    "search_kw": "深圳采购",
                    "category": "",
                })

        time.sleep(1)

    print(f"    → {len(items)} 条IT相关")
    return items


def save_and_summary(items):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 去重
    seen = set()
    unique = []
    for item in items:
        key = item["title"][:35]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    unique.sort(key=lambda x: x.get("date", ""), reverse=True)

    # 标记IT类
    it_items = [i for i in unique if is_it_item(i)]
    for i in unique:
        i["is_it"] = is_it_item(i)

    data = {
        "updated": datetime.now(CST).isoformat(),
        "source": "政府采购招标公告",
        "count": len(unique),
        "it_count": len(it_items),
        "items": unique,
    }
    path = os.path.join(OUTPUT_DIR, "bids.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 生成摘要
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    sp = os.path.join(OUTPUT_DIR, "bids-summary.html")
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
<h1>📋 招标信息聚合</h1>
<div class="meta">生成时间：{now} | 总计 {len(unique)} 条 | IT/信息类 {len(it_items)} 条</div>
<h2>🖥️ IT/信息类（{len(it_items)} 条）</h2>
"""
    for item in it_items[:60]:
        cat = f' [{item.get("category","")}]' if item.get("category") else ''
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} | {item.get("region","")} | {item.get("source","")}{cat}</div></div>\n'

    other = [i for i in unique if not i.get("is_it")]
    h += f'<h2>📋 其他招标（{len(other)} 条）</h2>'
    for item in other[:50]:
        h += f'<div class="item"><a href="{item["link"]}" target="_blank">{item["title"]}</a><div class="info">📅 {item.get("date","")} | {item.get("source","")}</div></div>\n'

    h += '</body></html>'
    with open(sp, "w", encoding="utf-8") as f:
        f.write(h)

    print(f"  💾 bids.json: {len(unique)} 条 (IT类 {len(it_items)})")
    print(f"  📄 bids-summary.html")
    return unique


def main():
    print("=" * 50)
    print(f"  投标监控爬虫 v4  {datetime.now(CST):%Y-%m-%d %H:%M}")
    print(f"  搜索词: {SEARCH_KW}")
    print(f"  IT过滤: {IT_WORDS[:6]}...")
    print("=" * 50)

    all_items = []

    for kw in SEARCH_KW:
        print(f"  🔍 {kw}...", end=" ")
        items = search_ccgp(kw, pages=2)
        print(f"{len(items)}条")

        # 筛选广东/深圳
        gd_items = []
        for item in items:
            if is_target_region(item):
                gd_items.append(item)

        print(f"    → 广东/深圳 {len(gd_items)}条")
        all_items.extend(gd_items)
        time.sleep(2)

    # 深圳平台
    all_items.extend(search_shenzhen())

    save_and_summary(all_items)

    # 打印IT类结果
    it = [i for i in all_items if is_it_item(i)]
    it_dedup = []
    seen = set()
    for i in it:
        k = i["title"][:35]
        if k not in seen:
            seen.add(k)
            it_dedup.append(i)
    print(f"\n✅ IT/信息类招标 ({len(it_dedup)} 条):")
    for i in it_dedup[:15]:
        print(f"  [{i.get('region',''):4s}] {i['title'][:70]}")


if __name__ == "__main__":
    import sys
    main()
