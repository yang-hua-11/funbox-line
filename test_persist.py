# -*- coding: utf-8 -*-
"""
驗證「已抽記錄」真的會存進 localStorage 並在重新載入後留著。
用本機 http server 跑（等同放上 GitHub Pages 的情況），開兩次瀏覽器共用同一個設定檔。

用法： python test_persist.py
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 第一次載入：標記一個項目
PASS1 = r"""
<div id="TESTOUT" style="display:none"></div>
<script>
(function(){
  var R = [];
  try{
    R.push({t:"localStorage 可用", ok: lsOK});
    state.q = "UX-21"; render();
    var li = document.querySelector('#list li[data-k]');
    var k = li.getAttribute('data-k');
    setDone(k, true);
    R.push({t:"已寫入記錄", ok: isToday(k), x:k});
    var raw = null;
    try { raw = localStorage.getItem("funbox_done_v2"); } catch(e){ raw = "ERR:"+e.message; }
    R.push({t:"localStorage 有內容", ok: !!raw && raw.indexOf("UX-21") !== -1, x:String(raw).slice(0,120)});
    R.push({t:"記錄的鍵", ok:true, x:k});
  }catch(err){ R.push({t:"例外", ok:false, x:err.message}); }
  document.getElementById('TESTOUT').textContent = "@@RESULT@@"+JSON.stringify(R)+"@@END@@";
})();
</script>
"""

# 第二次載入：確認記錄還在
PASS2 = r"""
<div id="TESTOUT" style="display:none"></div>
<script>
(function(){
  var R = [];
  try{
    R.push({t:"localStorage 可用", ok: lsOK});
    var raw = null;
    try { raw = localStorage.getItem("funbox_done_v2"); } catch(e){ raw = null; }
    R.push({t:"重新載入後 localStorage 仍有資料", ok: !!raw, x:String(raw).slice(0,120)});
    var keys = Object.keys(done);
    R.push({t:"重新載入後 done 物件有記錄", ok: keys.length === 1, x:keys.join(";")});
    R.push({t:"該記錄日期是今天", ok: keys.length===1 && isToday(keys[0]), x:done[keys[0]]});
    state.q = "UX-21"; render();
    var doneLi = document.querySelectorAll('#list li.done').length;
    R.push({t:"重新載入後該列顯示為已抽(灰色)", ok: doneLi === 1, x:String(doneLi)});
    R.push({t:"統計反映已抽 1 項", ok:/今天已抽 1 \/ 2/.test(document.getElementById('doneTxt').textContent),
            x:document.getElementById('doneTxt').textContent});
    state.hideDone = true; render();
    R.push({t:"只看未抽會排除它", ok: document.querySelectorAll('#list li[data-k]').length === 1,
            x:String(document.querySelectorAll('#list li[data-k]').length)});
  }catch(err){ R.push({t:"例外", ok:false, x:err.message}); }
  document.getElementById('TESTOUT').textContent = "@@RESULT@@"+JSON.stringify(R)+"@@END@@";
})();
</script>
"""


def safe_print(t):
    try:
        print(t)
    except UnicodeEncodeError:
        e = sys.stdout.encoding or "ascii"
        sys.stdout.write(t.encode(e, "replace").decode(e, "replace") + "\n")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def run_chrome(chrome, profile, url):
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-first-run", "--no-default-browser-check", "--disable-extensions",
           "--user-data-dir=" + profile, "--virtual-time-budget=6000",
           "--dump-dom", url]
    p = subprocess.run(cmd, capture_output=True, timeout=180)
    dom = p.stdout.decode("utf-8", "replace")
    m = re.search(r"@@RESULT@@(.*?)@@END@@", dom, re.S)
    if not m:
        return None, dom, p.stderr.decode("utf-8", "replace")
    return json.loads(m.group(1)), dom, ""


def main():
    chrome = next((c for c in CHROME_CANDIDATES if os.path.exists(c)), None)
    if not chrome:
        safe_print("找不到 Chrome/Edge，跳過")
        return 2

    root = tempfile.mkdtemp(prefix="site_")
    html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    open(os.path.join(root, "p1.html"), "w", encoding="utf-8").write(html.replace("</body>", PASS1 + "\n</body>"))
    open(os.path.join(root, "p2.html"), "w", encoding="utf-8").write(html.replace("</body>", PASS2 + "\n</body>"))

    port = free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=root)
    handler.log_message = lambda *a, **k: None
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)

    profile = tempfile.mkdtemp(prefix="chrp_")
    lines = []
    try:
        r1, dom1, err1 = run_chrome(chrome, profile, "http://127.0.0.1:%d/p1.html" % port)
        if r1 is None:
            safe_print("第一次載入沒有測試結果\n" + err1[:1500])
            return 1
        lines.append("--- 第 1 次載入（標記已抽）---")
        for r in r1:
            lines.append("[%s] %s%s" % ("PASS" if r["ok"] else "FAIL", r["t"],
                                        ("   -> " + r["x"]) if r.get("x") else ""))

        r2, dom2, err2 = run_chrome(chrome, profile, "http://127.0.0.1:%d/p2.html" % port)
        if r2 is None:
            safe_print("第二次載入沒有測試結果\n" + err2[:1500])
            return 1
        lines.append("")
        lines.append("--- 第 2 次載入（重新開頁，確認記錄留著）---")
        for r in r2:
            lines.append("[%s] %s%s" % ("PASS" if r["ok"] else "FAIL", r["t"],
                                        ("   -> " + r["x"]) if r.get("x") else ""))

        allr = r1 + r2
        fails = sum(1 for r in allr if not r["ok"])
        lines.append("")
        lines.append("共 %d 項，通過 %d，失敗 %d" % (len(allr), len(allr) - fails, fails))
        txt = "\n".join(lines)
        open(os.path.join(HERE, "_persist_report.txt"), "w", encoding="utf-8").write(txt)
        safe_print(txt)
        return 0 if fails == 0 else 1
    finally:
        srv.shutdown()
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
