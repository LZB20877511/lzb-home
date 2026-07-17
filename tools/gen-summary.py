# 静态摘要页生成器
# 读取 data/*.json → 生成 finance-summary.html（纯HTML无JS，AI可直接阅读）
import json, os
from datetime import datetime

OUTPUT = "finance-summary.html"
DATA_FILES = [
    ("data/a-stock.json", "A股要闻"),
    ("data/us-stock.json", "美股映射"),
    ("data/kr-stock.json", "韩股要闻"),
    ("data/announce.json", "个股公告"),
]

def load_data():
    all_items = []
    for path, label in DATA_FILES:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("items", []):
                    item["_cat_name"] = label
                    all_items.append(item)
    # 按时间倒序
    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    return all_items

def category_stats(items):
    stats = {}
    for item in items:
        cat = item.get("_cat_name", "其他")
        stats[cat] = stats.get(cat, 0) + 1
    return stats

def generate(items):
    stats = category_stats(items)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    h = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>财经摘要 - LZB</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei",sans-serif;max-width:900px;margin:20px auto;padding:20px;background:#0d1117;color:#c9d1d9;line-height:1.8;font-size:14px}}
h1{{color:#58a6ff;font-size:20px;margin-bottom:4px}}
.meta{{color:#8b949e;font-size:12px;margin-bottom:16px}}
.stats{{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap}}
.stat{{padding:4px 10px;border-radius:12px;font-size:12px;background:#161b22;border:1px solid #30363d;color:#8b949e}}
.stat b{{color:#c9d1d9}}
.toc{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px 16px;margin:16px 0}}
.toc a{{color:#58a6ff;text-decoration:none;margin:0 8px;font-size:13px}}
.toc a:hover{{text-decoration:underline}}
h2{{color:#58a6ff;font-size:16px;margin:28px 0 10px;padding-bottom:6px;border-bottom:1px solid #30363d}}
.item{{padding:8px 0;border-bottom:1px solid rgba(48,54,61,.5)}}
.item .t{{font-weight:600;margin-bottom:2px}}
.item .t a{{color:#c9d1d9;text-decoration:none}}
.item .s{{font-size:12px;color:#8b949e;margin-top:2px}}
.item .m{{font-size:11px;color:#8b949e;margin-top:2px}}
.item .m .src{{color:#58a6ff}}
.item .alert .t a{{color:#f85149}}
.stock-code{{color:#58a6ff;font-size:12px;font-weight:600;margin-left:6px}}
.footer{{margin-top:32px;padding-top:12px;border-top:1px solid #30363d;font-size:11px;color:#484f58;text-align:center}}
</style>
</head>
<body>
<h1>📊 财经摘要</h1>
<div class="meta">生成时间：{now} | 合计 {len(items)} 条 | <a href="finance.html">交互版</a> | 每2分钟自动更新</div>

<div class="stats">
"""

    for cat, count in sorted(stats.items()):
        h += f'<span class="stat">{cat} <b>{count}</b></span>\n'

    h += f"""</div>

<div class="toc">
  📑 快速跳转：
  <a href="#stats">概览</a>
"""

    for path, label in DATA_FILES:
        h += f'  <a href="#{label}">{label}</a>\n'

    h += """</div>

<h2 id="stats">📋 数据概览</h2>
<table style="width:100%;font-size:12px;border-collapse:collapse">
"""

    for cat, count in sorted(stats.items()):
        h += f'<tr><td style="padding:4px 0;border-bottom:1px solid #21262d">{cat}</td><td style="text-align:right;font-weight:600">{count} 条</td></tr>\n'

    h += f'<tr><td style="padding:4px 0;font-weight:600">合计</td><td style="text-align:right;font-weight:700;color:#58a6ff">{len(items)} 条</td></tr>\n'
    h += '</table>\n'

    # 按分类输出
    for path, label in DATA_FILES:
        cat_items = [i for i in items if i.get("_cat_name") == label]
        h += f'\n<h2 id="{label}">{label}（{len(cat_items)} 条）</h2>\n'

        for item in cat_items:
            title = item.get("title", "")
            link = item.get("link", "#")
            date = item.get("date", "")
            summary = item.get("summary", "")
            source = item.get("source", "")
            stock_code = item.get("stock_code", "")
            is_alert = "减持" in title or "解禁" in title or "ST" in title or "预警" in title
            alert_class = ' class="alert"' if is_alert else ""

            h += f'<div class="item"{alert_class}>\n'
            h += f'  <div class="t"><a href="{link}">{title}</a>{f"<span class=stock-code>{stock_code}</span>" if stock_code else ""}</div>\n'
            if summary:
                h += f'  <div class="s">{summary[:200]}</div>\n'
            h += f'  <div class="m"><span class="src">{source}</span> · {date}</div>\n'
            h += f'</div>\n'

    h += '</body>\n</html>'
    return h

if __name__ == "__main__":
    items = load_data()
    html = generate(items)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 生成 {OUTPUT}: {len(items)} 条，{len(html)} 字节")
    print("   AI可直接阅读，所有内容无需JS即可显示")
