# -*- coding: utf-8 -*-
"""
從 uxux11.github.io/funbox-line 的 HTML 抽出「抽選連結」資料，輸出 data.json。

用法：
    python extract.py                # 自動從網路下載最新頁面並解析
    python extract.py _src_pages.html  # 解析本機已下載的 HTML

輸出：data.json（給 build.py 產生 index.html 用）
"""
import re
import sys
import os
import json
import html as htmllib

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_URL = "https://uxux11.github.io/funbox-line/"


def fetch(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return raw.decode("utf-8", errors="replace")


def safe_print(txt):
    """Windows 主控台常是 cp950/cp1252，直接 print 中文會炸掉。"""
    try:
        print(txt)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        sys.stdout.write(txt.encode(enc, errors="replace").decode(enc, errors="replace") + "\n")


def clean(s):
    """去掉標籤、解 HTML entity、壓縮空白。"""
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s)
    s = s.replace("\u3000", " ")
    return re.sub(r"\s+", " ", s).strip()


# 商品型號，例如 BX-57 / UX-21 / BXG-01。
# 注意：不能用 \b 收尾，因為像「UX-20榮耀戰神」後面直接接中文，\b 不成立。
CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,4}-\d{1,3})(?!\d)")


def product_code(name):
    m = CODE_RE.search(name.upper())
    return m.group(1) if m else ""


def parse_draws(src):
    """解析抽選區塊：城市 -> 門市 -> 商品/連結。"""
    stores = []

    # 每一間門市：<div class="draw-store" data-draw-city="台北市"> ... </div>
    # 用 data-draw-city 當切點，抓到下一個 draw-store / draw-city-group / 區塊結束為止。
    starts = [m for m in re.finditer(
        r'<div class="draw-store"[^>]*data-draw-city="([^"]*)"[^>]*>', src)]

    for idx, m in enumerate(starts):
        city = htmllib.unescape(m.group(1)).strip()
        begin = m.end()
        end = starts[idx + 1].start() if idx + 1 < len(starts) else len(src)
        block = src[begin:end]

        nm = re.search(r'<div class="draw-store-name"[^>]*>(.*?)</div>', block, re.S)
        name = clean(nm.group(1)) if nm else ""
        if not name:
            continue

        tm = re.search(r'<div class="draw-start"[^>]*>(.*?)</div>', block, re.S)
        time_txt = clean(tm.group(1)) if tm else ""
        time_txt = re.sub(r"^抽選時間[：:]\s*", "", time_txt)

        items = []
        seen = set()
        # 每個商品項：<div class="draw-product">名稱</div> ... <a class="draw-link" href="...">
        for im in re.finditer(
            r'<div class="draw-product"[^>]*>(.*?)</div>\s*'
            r'<a[^>]*class="draw-link[^"]*"[^>]*href="([^"]+)"',
            block, re.S,
        ):
            p = clean(im.group(1))
            u = htmllib.unescape(im.group(2)).strip()
            if not p or not u or u in seen:
                continue
            seen.add(u)
            items.append({"p": p, "c": product_code(p), "u": u})

        if items:
            stores.append({"city": city, "name": name, "time": time_txt, "items": items})

    return stores


def parse_accounts(src):
    """解析「加好友」區塊：門市名 -> LINE 官方帳號 ID。抽獎前要先加好友，所以一起留著。"""
    accounts = []
    for m in re.finditer(
        r'<div class="card"[^>]*data-region="([^"]*)"[^>]*>(.*?)(?=<div class="card"|</div>\s*<div id=|$)',
        src, re.S,
    ):
        region = htmllib.unescape(m.group(1)).strip()
        block = m.group(2)
        nm = re.search(r'<div class="store-name"[^>]*>(.*?)</div>', block, re.S)
        am = re.search(r'<span class="line-id"[^>]*>(.*?)</span>', block, re.S)
        hm = re.search(r'href="(https://line\.me/[^"]+)"', block)
        if not nm:
            continue
        accounts.append({
            "region": region,
            "name": clean(nm.group(1)),
            "id": clean(am.group(1)) if am else "",
            "u": htmllib.unescape(hm.group(1)).strip() if hm else "",
        })
    return accounts


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if not os.path.isabs(path):
            path = os.path.join(HERE, path)
        src = open(path, encoding="utf-8", errors="replace").read()
        origin = path
    else:
        src = fetch(SRC_URL)
        origin = SRC_URL
        open(os.path.join(HERE, "_src_pages.html"), "w", encoding="utf-8").write(src)

    stores = parse_draws(src)
    accounts = parse_accounts(src)

    # 頁面上的公告標題（例如「8/28 抽選已更新！」）
    tm = re.search(r'<h1 class="draw-main-title"[^>]*>(.*?)</h1>', src, re.S)
    notice = clean(tm.group(1)) if tm else ""

    # 抽獎前必須先加該門市的 LINE 官方帳號好友，所以把加好友連結掛回門市。
    # 名稱對不起來的（門市叫「大葉高島屋」、帳號叫「高島屋百貨」）用這張對照表人工指定。
    ALIAS = {
        "Fun box忠孝SOGO": "台北忠孝遠東SOGO",
        "Funbox-信義A8店(陀螺販售)": "信義新天地A8館",
        "Funbox Toys-大葉高島屋": "高島屋百貨",
        "Funbox-南港潤泰": "潤泰南港車站店",
        "來玩聚-北車地下街": "台北地下街16號",
        "Funbox LaLaport南港": "南港LaLaport",
        "FunBox Toys-汐止遠雄店": "汐科遠雄",
        "Funbox新店誠品店": "新店裕隆城",
        "Funbox toys - 桃園台茂店": "台茂購物中心",
        "FUNBOX 台中遠百店": "台中遠東",
        "Funbox 新光三越台中店": "台中三越",
        "Funbox 台中遠雄店": "台中新時代",
        "funbox-台南新天地": "台南西門",
        "Funbox Toys-台南南紡店": "南紡購物中心",
        "Funbox高雄sogo店": "崇光高雄",
        "fun box 義大2館": "義大二館",
        "Funbox高雄義享店": "義享天地",
        "Funbox 宜蘭新月店": "新月廣場",
        "Funbox澎湖3號港店": "澎坊商場",
    }

    def norm(s):
        s = re.sub(r"(funbox|fun\s*box|來玩聚|toys|購物中心|廣場|百貨|店|館|門市|\s|[-—‧·()（）])",
                   "", s, flags=re.I)
        return s.lower()

    by_name = {a["name"]: a for a in accounts if a["u"]}
    acc_map = {}
    for a in accounts:
        if a["u"]:
            acc_map.setdefault(norm(a["name"]), a)

    matched = 0
    for s in stores:
        hit = None
        # 1) 人工對照表優先
        if s["name"] in ALIAS:
            hit = by_name.get(ALIAS[s["name"]])
        key = norm(s["name"])
        # 2) 正規化後完全相同
        if not hit:
            hit = acc_map.get(key)
        # 3) 互為子字串，取重疊最長的那個，避免短名亂配
        if not hit and key:
            best, best_len = None, 0
            for k, a in acc_map.items():
                if len(k) < 2:
                    continue
                if (k in key or key in k) and len(k) > best_len:
                    best, best_len = a, len(k)
            hit = best
        if hit:
            s["oa"] = hit["id"]
            s["oaUrl"] = hit["u"]
            matched += 1

    data = {
        "notice": notice,
        "source": SRC_URL,
        "stores": stores,
        "accounts": accounts,
    }

    out = os.path.join(HERE, "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    total_items = sum(len(s["items"]) for s in stores)
    codes = sorted({i["c"] for s in stores for i in s["items"] if i["c"]})
    report = [
        "來源: %s" % origin,
        "公告: %s" % notice,
        "縣市數: %d" % len({s["city"] for s in stores}),
        "門市數: %d" % len(stores),
        "抽獎項目數: %d" % total_items,
        "官方帳號數: %d (成功對上門市 %d)" % (len(accounts), matched),
        "商品型號 (%d): %s" % (len(codes), ", ".join(codes)),
        "輸出: %s" % out,
    ]
    txt = "\n".join(report)
    open(os.path.join(HERE, "_extract_report.txt"), "w", encoding="utf-8").write(txt)
    safe_print(txt)


if __name__ == "__main__":
    main()
