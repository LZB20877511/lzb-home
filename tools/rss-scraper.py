# 财经数据采集器 v2
# 用法：python tools/rss-scraper.py
# 自动抓取RSS+API源，生成JSON供网站使用

import json
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
import urllib.parse
import ssl
import os
import re
import time
from datetime import datetime, timezone, timedelta
from html import unescape

# ============ 配置 ============
OUTPUT_DIR = "data"
MAX_PER_SOURCE = 30
TIMEOUT = 20
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0"

def e(s): return urllib.parse.quote(s)

# ============ 数据源 ============

A_SOURCES = [
    # 新浪财经实时新闻（直接API，最可靠），多页获取增加数量
    {"name":"新浪财经","url":"https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=80&page=1","cat":"a-stock","type":"sina"},
    {"name":"新浪财经2","url":"https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2517&k=&num=30&page=1","cat":"a-stock","type":"sina"},
    # 财联社 RSS
    {"name":"财联社","url":"https://rsshub.app/cls/telegraph","cat":"a-stock","type":"rss"},
    # 雪球
    {"name":"雪球","url":"https://rsshub.app/xueqiu/hots/stock","cat":"a-stock","type":"rss"},
    # 东方财富要闻
    {"name":"东方财富-要闻","url":"https://rsshub.app/eastmoney/search/"+e("要闻"),"cat":"a-stock","type":"rss"},
]

US_SOURCES = [
    {"name":"Yahoo Finance","url":"https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,NVDA,TSLA,AAPL&region=US&lang=en-US","cat":"us-stock","type":"rss"},
    {"name":"CNBC","url":"https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114","cat":"us-stock","type":"rss"},
    {"name":"MarketWatch","url":"https://feeds.marketwatch.com/marketwatch/topstories","cat":"us-stock","type":"rss"},
    {"name":"Reuters","url":"https://rsshub.app/reuters/world","cat":"us-stock","type":"rss"},
]

POLICY_SOURCES = [
    {"name":"证监会","url":"https://rsshub.app/csrc/news","cat":"policy","type":"rss"},
    {"name":"央行","url":"https://rsshub.app/gov/pbc/goutongjiaoliu","cat":"policy","type":"rss"},
    {"name":"新浪政策","url":"https://rsshub.app/sina/finance/macro","cat":"policy","type":"rss"},
]

MACRO_SOURCES = [
    {"name":"新华社","url":"https://rsshub.app/xinhua/news/fortune","cat":"macro","type":"rss"},
    {"name":"新浪宏观","url":"https://rsshub.app/sina/finance/macro","cat":"macro","type":"rss"},
]

CAPITAL_SOURCES = [
    {"name":"北向资金","url":"https://rsshub.app/eastmoney/search/"+e("北向资金"),"cat":"capital-flow","type":"rss"},
]

DRAGON_SOURCES = [
    {"name":"龙虎榜","url":"https://rsshub.app/eastmoney/search/"+e("龙虎榜"),"cat":"dragon-tiger","type":"rss"},
]

MARGIN_SOURCES = [
    {"name":"融资融券","url":"https://rsshub.app/eastmoney/search/"+e("融资融券"),"cat":"margin","type":"rss"},
]

ANNOUNCE_SOURCES = [
    {"name":"巨潮资讯","url":"https://rsshub.app/cninfo/announcement","cat":"announce","type":"rss"},
    {"name":"公告-减持","url":"https://rsshub.app/eastmoney/search/"+e("减持"),"cat":"announce","type":"rss"},
    {"name":"公告-解禁","url":"https://rsshub.app/eastmoney/search/"+e("解禁"),"cat":"announce","type":"rss"},
    # 东方财富公告API（直接）
    {"name":"公告API","url":"https://np-anotice-stock.eastmoney.com/api/security/ann?page_size=30&page_index=1&ann_type=SHA,SZA&client_source=web","cat":"announce","type":"json"},
]

# ============ 核心函数 ============

def fetch_source(src):
    """抓取一个源，返回条目列表"""
    items = []
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(src["url"], headers={
            "User-Agent": UA,
            "Accept": "application/json, text/xml, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://finance.sina.com.cn/"
        })

        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = resp.read()

        # 解码
        try: text = raw.decode("utf-8")
        except: 
            try: text = raw.decode("gbk")
            except: text = raw.decode("latin-1")

        src_type = src.get("type", "rss")

        if src_type == "json":
            items = parse_json(text, src)
        elif src_type == "sina":
            items = parse_sina(text, src)
        else:
            items = parse_xml(text, src)

        print(f"  ✅ {src['name']}: {len(items)} 条")

    except urllib.error.HTTPError as e:
        code = e.code
        # 403/429 静默跳过，其他报错
        if code not in (403, 429):
            print(f"  ⚠️ {src['name']}: HTTP {code}")
    except Exception as e:
        msg = str(e)[:100]
        if "403" not in msg and "Forbidden" not in msg:
            print(f"  ⚠️ {src['name']}: {type(e).__name__}: {msg}")

    return items[:MAX_PER_SOURCE]


def parse_sina(text, src):
    """解析新浪财经滚动新闻API"""
    items = []
    try:
        data = json.loads(text)
        news_list = data.get("result", {}).get("data", [])
        for n in news_list:
            title = (n.get("title") or "").strip()
            link = n.get("url") or n.get("wapurl") or ""
            # ctime 是 Unix 时间戳
            ctime_str = str(n.get("ctime", ""))
            if ctime_str:
                ctime = int(ctime_str)
                dt = datetime.fromtimestamp(ctime) if ctime > 1000000000 else datetime.now()
            else:
                dt = datetime.now()
            desc = (n.get("intro") or n.get("summary") or "").strip()
            source = n.get("media_name") or src["name"]

            if title and len(title) > 3:
                items.append({
                    "title": title,
                    "link": link,
                    "date": dt.strftime("%Y-%m-%d %H:%M"),
                    "summary": strip_html(desc)[:200],
                    "source": source,
                    "category": src["cat"]
                })
    except Exception as e:
        print(f"    新浪解析失败: {e}")
    return items


def parse_json(text, src):
    """解析JSON格式（东方财富API等）"""
    items = []
    try:
        data = json.loads(text)
        # 东方财富新闻API格式
        if "data" in data and isinstance(data["data"], dict):
            news_list = data["data"].get("list") or data["data"].get("items") or []
        elif "data" in data and isinstance(data["data"], list):
            news_list = data["data"]
        else:
            news_list = data.get("items") or data.get("list") or []

        for n in news_list:
            title = (n.get("title") or n.get("name") or n.get("art_title") or "").strip()
            link = (n.get("url") or n.get("link") or n.get("art_url") or "")
            if "http" not in str(link) and n.get("art_code"):
                link = f"https://finance.eastmoney.com/a/{n['art_code']}.html"
            t = (n.get("show_time") or n.get("date") or n.get("noticedate") or "")
            desc = (n.get("summary") or n.get("digest") or n.get("content") or "")

            # 提取股票代码（公告API: codes[0].stock_code 和 codes[0].short_name）
            stock_code = ""
            stock_name = ""
            codes = n.get("codes") or n.get("codeList") or []
            if isinstance(codes, list) and len(codes) > 0:
                c0 = codes[0]
                stock_code = str(c0.get("stock_code") or c0.get("secucode") or "")
                stock_name = str(c0.get("short_name") or c0.get("name") or "")

            if not stock_code:
                stock_code = str(n.get("stock_code") or n.get("secucode") or "")

            if title and len(title) > 3:
                items.append({
                    "title": unescape(title.strip()),
                    "link": str(link).strip(),
                    "date": parse_date(t),
                    "summary": strip_html(unescape(str(desc)))[:200],
                    "source": src["name"],
                    "category": src["cat"],
                    "stock_code": stock_code,
                    "stock_name": stock_name
                })
    except Exception as e:
        print(f"    JSON解析失败: {e}")
    return items


def parse_xml(text, src):
    """解析XML（RSS/Atom）"""
    items = []
    try:
        text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\x80-\xFF\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', '', text)
        root = ET.fromstring(text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for item in root.iter("item"):
            title, link, date, desc = "", "", "", ""
            for child in item:
                tag = child.tag.lower()
                txt = (child.text or "").strip()
                if tag == "title": title = unescape(txt)
                elif tag == "link": link = txt
                elif tag in ("pubdate", "dc:date"): date = txt
                elif tag in ("description", "content:encoded"): desc = unescape(txt)
            if title and len(title) > 3:
                items.append({
                    "title": title, "link": link,
                    "date": parse_date(date),
                    "summary": strip_html(desc)[:200],
                    "source": src["name"], "category": src["cat"]
                })

        if not items:
            for entry in root.findall("atom:entry", ns):
                t_el = entry.find("atom:title", ns)
                l_el = entry.find("atom:link", ns)
                u_el = entry.find("atom:updated", ns)
                s_el = entry.find("atom:summary", ns)
                title = unescape(t_el.text.strip()) if t_el is not None and t_el.text else ""
                link = l_el.get("href", "") if l_el is not None else ""
                date = u_el.text.strip() if u_el is not None and u_el.text else ""
                desc = unescape(s_el.text) if s_el is not None and s_el.text else ""
                if title and len(title) > 3:
                    items.append({
                        "title": title, "link": link,
                        "date": parse_date(date),
                        "summary": strip_html(desc)[:200],
                        "source": src["name"], "category": src["cat"]
                    })
    except ET.ParseError:
        pass
    except Exception as e:
        print(f"    XML: {e}")
    return items


def parse_date(s):
    if not s: return datetime.now().strftime("%Y-%m-%d %H:%M")
    # 东方财富格式: 2026-06-21 14:30:00
    for fmt in ["%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%SZ",
                "%a, %d %b %Y %H:%M:%S %z","%Y-%m-%d %H:%M","%Y-%m-%d","%Y/%m/%d %H:%M"]:
        try: return datetime.strptime(str(s).strip(), fmt).strftime("%Y-%m-%d %H:%M")
        except: pass
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def strip_html(s):
    return re.sub(r'<[^>]+>', '', s).replace('&nbsp;',' ').strip()


# 美股噪声过滤：对A股短线交易者无价值的内容
US_NOISE_KEYWORDS = [
    'retirement', '401k', 'ira ', 'social security',
    'parenting', 'children', 'kids',
    'divorce', 'marriage',
    'vacation', 'travel', 'resort', 'hotel',
    'recipe', 'cooking', 'food', 'restaurant',
    'fitness', 'workout', 'health tips', 'wellness',
    'mortgage', 'home buying', 'house hunting', 'real estate',
    'credit card', 'debt management', 'personal loan',
    'life insurance', 'home insurance', 'car insurance',
    'celebrity', 'entertainment', 'sports',
    'college', 'student loan',
    'cruise', 'airline',
    'mattress', 'furniture',
    'pet ', 'dog ', 'cat ',
    'garden', 'lawn',
    'fashion', 'beauty',
]

def is_noise(item):
    """判断是否为噪声或无关内容"""
    title = (item.get("title") or "").lower()
    summary = (item.get("summary") or "").lower()
    text = title + " " + summary
    cat = item.get("category", "")

    # 美股噪声过滤
    if cat == "us-stock":
        for kw in US_NOISE_KEYWORDS:
            if kw in text:
                return True

    # 港股过滤：A股页面不需要纯港股内容
    if cat == "a-stock":
        hk_markers = ["港股", ".hk)", "（hk", "恒生", "h股", "hong kong"]
        if any(m in title for m in hk_markers):
            # 除非标题同时也提到A股相关
            a_markers = ["a股", "沪", "深", "北向", "科创", "创业"]
            if not any(m in title for m in a_markers):
                return True

    return False


def dedup(items):
    seen = set(); out = []
    for item in items:
        k = item["title"][:25]
        if k not in seen: seen.add(k); out.append(item)
    return out


def scrape(sources):
    all_items = []
    for src in sources:
        all_items.extend(fetch_source(src))
        time.sleep(0.3)
    return all_items


def save(items, filename, label):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # 噪声过滤
    before = len(items)
    items = [i for i in items if not is_noise(i)]
    noise_count = before - len(items)
    if noise_count > 0:
        print(f"    🧹 过滤噪声 {noise_count} 条")
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    items = dedup(items)
    data = {"updated": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "source": label, "count": len(items), "items": items}
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 {path}: {len(items)} 条")


def main():
    print("=" * 50)
    print(f"  财经采集器 v2  {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 50)

    a = scrape(A_SOURCES)
    us = scrape(US_SOURCES)
    policy = scrape(POLICY_SOURCES)
    macro = scrape(MACRO_SOURCES)
    capital = scrape(CAPITAL_SOURCES)
    dragon = scrape(DRAGON_SOURCES)
    margin = scrape(MARGIN_SOURCES)
    announce = scrape(ANNOUNCE_SOURCES)

    a_all = a + policy + macro + capital + dragon + margin
    save(a_all, "a-stock.json", "A股聚合")
    save(us, "us-stock.json", "美股聚合")
    save(announce, "announce.json", "个股公告")

    print(f"\n✅ A股相关:{len(a_all)}  美股:{len(us)}  公告:{len(announce)}  合计:{len(a_all)+len(us)+len(announce)}")
    print("📝 部署: cp data/*.json 到仓库 → git push")

    # 自动生成AI可读摘要页
    print("\n📄 生成AI摘要页...")
    os.system(f"{sys.executable} tools/gen-summary.py")


if __name__ == "__main__":
    import sys
    main()
