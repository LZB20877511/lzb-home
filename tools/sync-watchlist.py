#!/usr/bin/env python3
"""同步自选股到 LZB Cloudflare Worker KV — 在本地运行"""

import json, urllib.request

WORKER = "https://api-relay.lzb19820403.workers.dev"

with open("data/watchlist.json", encoding="utf-8") as f:
    stocks = json.load(f)

for s in stocks:
    data = json.dumps(s).encode()
    req = urllib.request.Request(
        f"{WORKER}/api/watchlist",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = resp.read().decode()
        print(f"OK {s['code']} {s['name']}: {result}")
    except Exception as e:
        print(f"ERR {s['code']} {s['name']}: {e}")

print(f"\nSynced {len(stocks)} stocks")
