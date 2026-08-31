# -*- coding: utf-8 -*-
"""
把 data.json 塞進 template.html，產生可直接開啟的 index.html。
同時輸出 checklist.txt / checklist.csv，方便直接印或丟到手機。

用法：
    python build.py
"""
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
TPL = os.path.join(HERE, "template.html")
OUT = os.path.join(HERE, "index.html")


def safe_print(txt):
    try:
        print(txt)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        sys.stdout.write(txt.encode(enc, "replace").decode(enc, "replace") + "\n")


def js_json(obj):
    """安全嵌入 <script> 的 JSON：把可能提前結束 script 標籤的字元轉義掉。"""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    s = s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    # JS 字串裡 U+2028/2029 算換行，會造成語法錯誤
    return s.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def main():
    if not os.path.exists(DATA):
        safe_print("找不到 data.json，先執行： python extract.py")
        return 1
    if not os.path.exists(TPL):
        safe_print("找不到 template.html")
        return 1

    data = json.load(open(DATA, encoding="utf-8"))
    data["builtAt"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    tpl = open(TPL, encoding="utf-8").read()
    payload = js_json(data)

    marker = re.compile(r"/\*__DATA__\*/.*?/\*__DATA_END__\*/", re.S)
    if not marker.search(tpl):
        safe_print("template.html 裡找不到 /*__DATA__*/ ... /*__DATA_END__*/ 佔位符")
        return 1
    # 用 lambda 當 repl，避免 payload 裡的反斜線被當成 re 的替換語法
    html = marker.sub(lambda m: "/*__DATA__*/" + payload + "/*__DATA_END__*/", tpl, count=1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    stores = data["stores"]

    # ---- checklist.txt：門市 + 商品 + 連結 ----
    lines = [
        "Funbox 陀螺抽選清單",
        "資料版本：%s" % data["builtAt"],
        "公告：%s" % data.get("notice", ""),
        "來源：%s" % data.get("source", ""),
        "",
        "抽選仍需在 LINE 中自行完成；抽之前記得先加該門市官方帳號好友。",
        "=" * 56,
        "",
    ]
    cur_city = None
    total = 0
    for s in stores:
        if s["city"] != cur_city:
            cur_city = s["city"]
            lines.append("")
            lines.append("### %s ###" % cur_city)
        lines.append("")
        lines.append("%s（%s）" % (s["name"], s["time"] or "—"))
        if s.get("oaUrl"):
            lines.append("  加好友 %s  %s" % (s.get("oa", ""), s["oaUrl"]))
        for it in s["items"]:
            total += 1
            lines.append("  [ ] %s" % it["p"])
            lines.append("      %s" % it["u"])
    lines += ["", "=" * 56, "合計 %d 間門市 / %d 個抽選項目" % (len(stores), total)]
    open(os.path.join(HERE, "checklist.txt"), "w", encoding="utf-8").write("\n".join(lines))

    # ---- checklist.csv：可丟進 Excel / Google Sheet ----
    import csv
    with open(os.path.join(HERE, "checklist.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["縣市", "門市", "抽選時間", "型號", "商品", "抽獎連結", "官方帳號", "加好友連結", "已抽"])
        for s in stores:
            for it in s["items"]:
                w.writerow([s["city"], s["name"], s["time"], it.get("c", ""), it["p"], it["u"],
                            s.get("oa", ""), s.get("oaUrl", ""), ""])

    report = [
        "index.html      %6.1f KB" % (os.path.getsize(OUT) / 1024.0),
        "checklist.txt   %6.1f KB" % (os.path.getsize(os.path.join(HERE, "checklist.txt")) / 1024.0),
        "checklist.csv   %6.1f KB" % (os.path.getsize(os.path.join(HERE, "checklist.csv")) / 1024.0),
        "門市 %d / 抽選項目 %d / 資料版本 %s" % (len(stores), total, data["builtAt"]),
    ]
    txt = "\n".join(report)
    open(os.path.join(HERE, "_build_report.txt"), "w", encoding="utf-8").write(txt)
    safe_print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
