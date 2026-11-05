# -*- coding: utf-8 -*-
"""
短網址預解析器 — 把 data.json 裡的 lin.ee 全部解析成最終 liff.line.me 網址
================================================================================
這是「加速」的核心：抽選前先在電腦把所有 lin.ee 短網址解析成最終 LIFF 網址，
抽的時候模擬器直接開 liff.line.me，跳過 LINE 的短網址跳轉等待（每個省 1~3 秒）。

【用法】
    python resolve_links.py              # 解析 data.json 全部連結，輸出 resolved_links.json
    python resolve_links.py --city 台北市 # 只解析指定縣市
    python resolve_links.py --threads 16  # 調整平行解析的執行緒數（預設 12）
    python resolve_links.py --refresh     # 忽略快取，全部重新解析

【產出】
    resolved_links.json  — [{city, name, p, url(原始lin.ee), resolved(最終liff網址)}]
    _alias_cache.sqlite  — 解析快取，解析過的下次秒出（跟 APK 的 aliases 表同理）
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
OUT = os.path.join(HERE, "resolved_links.json")
CACHE = os.path.join(HERE, "_alias_cache.sqlite")


def init_cache():
    """建立/開啟 SQLite 快取（跟 APK 的 aliases 表同結構）。"""
    con = sqlite3.connect(CACHE)
    con.execute("CREATE TABLE IF NOT EXISTS aliases (url TEXT PRIMARY KEY, resolved TEXT NOT NULL)")
    con.commit()
    return con


def cache_get(con, url):
    row = con.execute("SELECT resolved FROM aliases WHERE url=?", (url,)).fetchone()
    return row[0] if row else None


def cache_put(con, url, resolved):
    con.execute("INSERT OR REPLACE INTO aliases (url, resolved) VALUES (?, ?)", (url, resolved))


def resolve_one(url, timeout=10):
    """跟隨跳轉拿到最終 URL。失敗回傳 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.geturl()
    except Exception:
        return None


def read_links(city_filter=None):
    """從 data.json 讀出所有連結（去重）。"""
    data = json.load(open(DATA, encoding="utf-8"))
    out, seen = [], set()
    for s in data.get("stores", []):
        if city_filter and s.get("city") != city_filter:
            continue
        for it in s.get("items", []):
            u = it.get("u")
            if not u or u in seen:
                continue
            seen.add(u)
            out.append({"city": s.get("city", ""), "name": s.get("name", ""),
                        "p": it.get("p", ""), "url": u})
    return out


def main():
    ap = argparse.ArgumentParser(description="lin.ee 短網址預解析器")
    ap.add_argument("--city", default=None, help="只解析指定縣市")
    ap.add_argument("--threads", type=int, default=12, help="平行解析的執行緒數（預設 12）")
    ap.add_argument("--refresh", action="store_true", help="忽略快取，全部重新解析")
    args = ap.parse_args()

    links = read_links(args.city)
    if not links:
        print("data.json 裡沒有連結（city 篩選？）")
        return 1

    con = init_cache()

    # 先吃快取
    todo = []
    for link in links:
        if not args.refresh:
            cached = cache_get(con, link["url"])
            if cached:
                link["resolved"] = cached
                continue
        todo.append(link)

    print("共 %d 個連結，其中 %d 個已有快取、%d 個需要解析。"
          % (len(links), len(links) - len(todo), len(todo)))

    if todo:
        print("開始平行解析（%d 執行緒）…" % args.threads)
        t0 = time.time()
        done = fail = 0
        with ThreadPoolExecutor(max_workers=args.threads) as ex:
            futs = {ex.submit(resolve_one, link["url"]): link for link in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                link = futs[fut]
                resolved = fut.result()
                if resolved:
                    link["resolved"] = resolved
                    cache_put(con, link["url"], resolved)
                    done += 1
                else:
                    link["resolved"] = link["url"]  # 解析失敗就退回原始 lin.ee（照樣能開）
                    fail += 1
                if i % 20 == 0 or i == len(todo):
                    print("  進度 %d/%d（成功 %d、失敗 %d）" % (i, len(todo), done, fail))
        con.commit()
        print("解析完成，耗時 %.1f 秒。" % (time.time() - t0))

    con.close()

    # 寫出結果
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"links": links}, f, ensure_ascii=False, indent=1)

    resolved_cnt = sum(1 for l in links if l.get("resolved", "").startswith("https://liff.line.me"))
    print("\n已輸出 %s" % OUT)
    print("  總連結 %d，成功解析成 liff 網址 %d。" % (len(links), resolved_cnt))
    if resolved_cnt < len(links):
        print("  （未解析成功的會退回原始 lin.ee，照樣能抽，只是沒加速。）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
