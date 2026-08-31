# -*- coding: utf-8 -*-
"""
量測真正手機寬度下是否有水平溢出。

無頭 Chrome 的 innerWidth 最小會被夾在 500px，用 --window-size 量不到 320/390 的情況，
所以改用 iframe：把 index.html 放進指定寬度的 iframe，iframe 內部就是真實的窄視窗。

用法： python test_layout.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(HERE, "index.html")
WIDTHS = [320, 360, 390, 414, 480, 600, 820]
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

HARNESS = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>layout probe</title>
<style>body{margin:0}iframe{border:0;display:block}</style></head>
<body>
<div id="TESTOUT" style="display:none"></div>
<div id="frames">__FRAMES__</div>
<script>
var WIDTHS = __WIDTHS__;
function probe(win, vw){
  var doc = win.document, de = doc.documentElement;
  var offenders = [];
  var all = doc.querySelectorAll('body *');
  for(var i=0;i<all.length;i++){
    var el = all[i];
    var r = el.getBoundingClientRect();
    if(r.width === 0 && r.height === 0) continue;
    var cs = win.getComputedStyle(el);
    if(cs.display === 'none' || cs.visibility === 'hidden') continue;
    if(r.right > vw + 1.5 || r.left < -1.5){
      var d = el.id ? '#'+el.id : (el.className ? '.'+String(el.className).split(/\\s+/).slice(0,2).join('.') : '');
      offenders.push({sel: el.tagName.toLowerCase()+d, left:Math.round(r.left),
                      right:Math.round(r.right), w:Math.round(r.width),
                      txt:(el.textContent||'').trim().slice(0,24)});
    }
  }
  // 量幾個關鍵可點擊元素的高度，確認觸控目標夠大
  var tapMin = 999, tapWho = '';
  ['a.go','button.mark','nav.tabs button','.chip'].forEach(function(sel){
    var e = doc.querySelector(sel);
    if(e){ var h = e.getBoundingClientRect().height; if(h < tapMin){ tapMin = Math.round(h); tapWho = sel; } }
  });
  return {
    width: vw,
    innerWidth: win.innerWidth,
    scrollWidth: de.scrollWidth,
    overflowPx: de.scrollWidth - win.innerWidth,
    offenderCount: offenders.length,
    offenders: offenders.slice(0,10),
    itemsRendered: doc.querySelectorAll('#list li[data-k]').length,
    minTapHeight: tapMin,
    minTapSel: tapWho
  };
}
function run(){
  var out = [];
  for(var i=0;i<WIDTHS.length;i++){
    var f = document.getElementById('f'+WIDTHS[i]);
    try { out.push(probe(f.contentWindow, WIDTHS[i])); }
    catch(e){ out.push({width:WIDTHS[i], error:String(e && e.message || e)}); }
  }
  document.getElementById('TESTOUT').textContent = '@@RESULT@@'+JSON.stringify(out)+'@@END@@';
}
var tries = 0;
(function wait(){
  tries++;
  var ready = WIDTHS.every(function(w){
    var f = document.getElementById('f'+w);
    try { return f.contentDocument && f.contentDocument.querySelectorAll('#list li[data-k]').length > 0; }
    catch(e){ return false; }
  });
  if(ready || tries > 120) run();
  else setTimeout(wait, 60);
})();
</script>
</body></html>
"""


def safe_print(t):
    try:
        print(t)
    except UnicodeEncodeError:
        e = sys.stdout.encoding or "ascii"
        sys.stdout.write(t.encode(e, "replace").decode(e, "replace") + "\n")


def main():
    chrome = next((c for c in CHROME_CANDIDATES if os.path.exists(c)), None)
    if not chrome:
        safe_print("找不到瀏覽器")
        return 2
    if not os.path.exists(IDX):
        safe_print("index.html 不存在")
        return 1

    frames = "\n".join(
        '<iframe id="f%d" src="index.html" style="width:%dpx;height:1000px"></iframe>' % (w, w)
        for w in WIDTHS
    )
    harness = HARNESS.replace("__FRAMES__", frames).replace("__WIDTHS__", json.dumps(WIDTHS))
    hpath = os.path.join(HERE, "_layout_harness.html")
    open(hpath, "w", encoding="utf-8").write(harness)

    prof = tempfile.mkdtemp(prefix="lay_")
    try:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
               "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
               "--allow-file-access-from-files",
               "--user-data-dir=" + prof, "--window-size=1400,1200",
               "--virtual-time-budget=15000", "--dump-dom",
               "file:///" + hpath.replace("\\", "/")]
        p = subprocess.run(cmd, capture_output=True, timeout=240)
    finally:
        shutil.rmtree(prof, ignore_errors=True)

    dom = p.stdout.decode("utf-8", "replace")
    m = re.search(r"@@RESULT@@(.*?)@@END@@", dom, re.S)
    if not m:
        safe_print("探測失敗\n" + p.stderr.decode("utf-8", "replace")[:2000])
        return 1

    results = json.loads(m.group(1))
    lines, fails = [], 0
    for r in results:
        if r.get("error"):
            lines.append("[FAIL] 寬 %-4d 錯誤: %s" % (r["width"], r["error"]))
            fails += 1
            continue
        over = r["overflowPx"] > 1
        small_tap = r["minTapHeight"] < 32
        bad = over or r["itemsRendered"] == 0 or small_tap
        if bad:
            fails += 1
        lines.append("[%s] 寬 %-4d innerWidth=%-4d scrollWidth=%-4d 溢出=%-3dpx 超界元素=%-2d 渲染項目=%-4d 最小觸控高=%dpx(%s)"
                     % ("FAIL" if bad else "PASS", r["width"], r["innerWidth"], r["scrollWidth"],
                        r["overflowPx"], r["offenderCount"], r["itemsRendered"],
                        r["minTapHeight"], r["minTapSel"]))
        for o in r["offenders"]:
            lines.append("         超界 %-26s left=%-5d right=%-5d w=%-5d %s"
                         % (o["sel"], o["left"], o["right"], o["w"], o["txt"]))
    lines.append("")
    lines.append("結果：%s" % ("全部寬度都沒有水平溢出，觸控目標也夠大" if fails == 0
                              else "有 %d 個寬度不合格" % fails))
    txt = "\n".join(lines)
    open(os.path.join(HERE, "_layout_report.txt"), "w", encoding="utf-8").write(txt)
    safe_print(txt)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
