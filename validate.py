# -*- coding: utf-8 -*-
"""檢查產生出來的 index.html 是否健全。"""
import json
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(HERE, "index.html")


def safe_print(t):
    try:
        print(t)
    except UnicodeEncodeError:
        e = sys.stdout.encoding or "ascii"
        sys.stdout.write(t.encode(e, "replace").decode(e, "replace") + "\n")


class TagCheck(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack:
            self.errors.append("多出的結束標籤 </%s> 在 %s" % (tag, self.getpos()))
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    unclosed = [t for t, _ in self.stack[i + 1:]]
                    self.errors.append("</%s> 之前有未關閉的標籤 %s (%s)" % (tag, unclosed, self.getpos()))
                    del self.stack[i:]
                    break
            else:
                self.errors.append("找不到對應開始標籤的 </%s> 在 %s" % (tag, self.getpos()))


def main():
    ok = True
    res = []

    if not os.path.exists(IDX):
        safe_print("index.html 不存在")
        return 1
    html = open(IDX, encoding="utf-8").read()
    res.append("index.html 大小: %.1f KB" % (len(html.encode("utf-8")) / 1024.0))

    # 1) 佔位符必須被換掉
    if "/*__DATA__*/null/*__DATA_END__*/" in html:
        res.append("[X] 資料沒有被注入，還是 null")
        ok = False
    else:
        res.append("[OK] 資料佔位符已被取代")

    # 2) 取出 payload 並用 JSON 解析
    m = re.search(r"/\*__DATA__\*/(.*?)/\*__DATA_END__\*/", html, re.S)
    if not m:
        res.append("[X] 找不到資料區塊")
        return 1
    payload = m.group(1)
    try:
        data = json.loads(payload)
        res.append("[OK] 內嵌 JSON 可正常解析")
    except Exception as e:
        res.append("[X] 內嵌 JSON 解析失敗: %s" % e)
        return 1

    # 3) script 不能被資料提前結束
    body = html
    if re.search(r"</script", payload, re.I):
        res.append("[X] payload 內含 </script，會提前結束腳本")
        ok = False
    else:
        res.append("[OK] payload 不含 </script")

    # 4) 只能有一組 script/style
    res.append("[OK] <script> 數量: %d，</script> 數量: %d"
               % (len(re.findall(r"<script", body)), len(re.findall(r"</script>", body))))
    if len(re.findall(r"<script", body)) != len(re.findall(r"</script>", body)):
        res.append("[X] script 標籤沒有成對")
        ok = False

    # 5) 標籤配對（把 script/style 內容拿掉再驗，避免 JS 裡的 < > 干擾）
    stripped = re.sub(r"<script\b[^>]*>.*?</script>", "<script></script>", html, flags=re.S | re.I)
    stripped = re.sub(r"<style\b[^>]*>.*?</style>", "<style></style>", stripped, flags=re.S | re.I)
    tc = TagCheck()
    tc.feed(stripped)
    leftover = [t for t, _ in tc.stack]
    if tc.errors or leftover:
        res.append("[X] HTML 標籤問題: %s / 未關閉: %s" % (tc.errors[:6], leftover))
        ok = False
    else:
        res.append("[OK] HTML 標籤全部正確配對")

    # 6) 資料內容檢查
    stores = data.get("stores", [])
    items = [(s, it) for s in stores for it in s["items"]]
    urls = [it["u"] for _, it in items]
    res.append("[OK] 門市 %d 間 / 抽選項目 %d 個 / 唯一連結 %d 個"
               % (len(stores), len(items), len(set(urls))))
    if len(set(urls)) != len(urls):
        res.append("[!] 有重複連結 %d 個" % (len(urls) - len(set(urls))))
    bad = [u for u in urls if not re.match(r"^https://(lin\.ee|liff\.line\.me|line\.me)/", u)]
    if bad:
        res.append("[X] 非 LINE 網域連結: %s" % bad[:5])
        ok = False
    else:
        res.append("[OK] 所有連結都是 LINE 網域")

    no_oa = [s["name"] for s in stores if not s.get("oaUrl")]
    res.append(("[OK] 全部門市都有加好友連結" if not no_oa
                else "[!] %d 間門市沒有加好友連結: %s" % (len(no_oa), no_oa[:5])))

    no_time = [s["name"] for s in stores if not s.get("time")]
    res.append("[OK] 全部門市都有抽選時間" if not no_time else "[!] 缺抽選時間: %s" % no_time[:5])

    codes = sorted({it.get("c", "") for _, it in items if it.get("c")})
    res.append("[OK] 型號 %d 種: %s" % (len(codes), ", ".join(codes)))
    for probe in ("UX-21", "BX-57", "UX-19"):
        hits = [(s["city"], s["name"]) for s, it in items if it.get("c") == probe]
        res.append("     搜尋 %-6s -> %d 間門市" % (probe, len(hits)))

    # 7) 必要的 UI 元件都在
    need = ["id=\"q\"", "id=\"cityChips\"", "id=\"codeChips\"", "id=\"hideDone\"",
            "id=\"list\"", "id=\"out\"", "id=\"copyBtn\"", "id=\"dlBtn\"",
            "id=\"friendList\"", "id=\"clearToday\"", "id=\"clearAll\"",
            "data-view=\"store\"", "data-view=\"code\"", "data-fmt=\"csv\""]
    missing = [n for n in need if n not in html]
    if missing:
        res.append("[X] 缺少 UI 元件: %s" % missing)
        ok = False
    else:
        res.append("[OK] 所有 UI 元件都存在")

    # 8) 括號/引號粗略平衡檢查（只看 script 區塊）
    sm = re.search(r"<script>\n?(.*)</script>", html, re.S)
    if sm:
        js = sm.group(1)
        for a, b, name in [("{", "}", "大括號"), ("(", ")", "小括號"), ("[", "]", "中括號")]:
            if js.count(a) != js.count(b):
                res.append("[!] JS %s 數量不等 (%d vs %d)（字串內字元也會被算到，僅供參考）"
                           % (name, js.count(a), js.count(b)))

    res.append("")
    res.append("結果: " + ("全部通過" if ok else "有問題需要修"))
    txt = "\n".join(res)
    open(os.path.join(HERE, "_validate.txt"), "w", encoding="utf-8").write(txt)
    safe_print(txt)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
