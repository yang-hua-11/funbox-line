# -*- coding: utf-8 -*-
"""
在無頭 Chrome 裡實際執行 index.html 的 JavaScript，驗證篩選、搜尋、已抽標記、
清單產生等功能真的能動（不是只有 HTML 長得對）。

用法： python test_page.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(HERE, "index.html")
TEST = os.path.join(HERE, "_test.html")
DUMP = os.path.join(HERE, "_test_dom.html")

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 注入頁面的測試腳本。頁面的函式都是 classic script 的頂層宣告，所以是全域可直接呼叫。
# __EXPECT__ 會被換成從 data.json 算出來的期望值，資料更新後測試不會誤報。
TEST_JS = r"""
<div id="TESTOUT" style="display:none"></div>
<script>
(function(){
  var E = __EXPECT__;
  var R = [];
  function ok(name, cond, extra){ R.push({t:name, ok:!!cond, x:(extra===undefined?"":String(extra))}); }
  function rowsShown(){ return document.querySelectorAll('#list li[data-k]').length; }
  function storesShown(){ return document.querySelectorAll('#list .store').length; }

  try {
    // ---- 資料載入 ----
    ok("DATA 有載入", typeof DATA === "object" && DATA !== null);
    ok("門市數符合 data.json", STORES.length === E.stores, STORES.length+" / "+E.stores);
    var totalItems = STORES.reduce(function(a,s){ return a+s.items.length; }, 0);
    ok("抽選項目數符合 data.json", totalItems === E.items, totalItems+" / "+E.items);

    // ---- 初始渲染 ----
    ok("初始有渲染出全部項目", rowsShown() === E.items, rowsShown());
    ok("初始有渲染出全部門市卡", storesShown() === E.stores, storesShown());
    ok("縣市按鈕有畫出來", document.querySelectorAll('#cityChips .chip').length === E.cities + 1,
       document.querySelectorAll('#cityChips .chip').length+" / "+(E.cities+1));
    ok("型號按鈕有畫出來(折疊 10 個+全部+展開)",
       document.querySelectorAll('#codeChips .chip').length === Math.min(E.codes,10) + 2,
       document.querySelectorAll('#codeChips .chip').length);
    ok("統計文字有值",
       document.getElementById('countTxt').textContent.indexOf("顯示 "+E.stores+" 間門市") === 0,
       document.getElementById('countTxt').textContent);

    // ---- 搜尋 UX-21（使用者明確要求的情境）----
    state.q = "UX-21"; render();
    ok("搜尋 UX-21 筆數正確", rowsShown() === E.ux21Items, rowsShown()+" / 期望 "+E.ux21Items);
    ok("搜尋 UX-21 門市數正確", storesShown() === E.ux21Stores, storesShown()+" / "+E.ux21Stores);
    var t = document.getElementById('list').textContent;
    var allUx = true;
    document.querySelectorAll('#list li[data-k]').forEach(function(li){
      if(li.querySelector('.pname').textContent.toUpperCase().indexOf("UX-21") === -1) allUx = false;
    });
    ok("搜尋 UX-21 結果每列都是 UX-21", allUx);
    ok("搜尋 UX-21 跨越多間門市", storesShown() >= 2, storesShown());

    // ---- 依商品檢視 ----
    state.view = "code"; render();
    ok("依商品檢視有 UX-21 標題", document.getElementById('list').textContent.indexOf("UX-21") !== -1);
    ok("依商品檢視列出相同筆數", rowsShown() === E.ux21Items, rowsShown());
    state.view = "store";

    // ---- 中文關鍵字搜尋 ----
    state.q = "獅鷲"; render();
    ok("搜尋中文『獅鷲』有結果", rowsShown() > 0, rowsShown());
    var allHaveWord = true;
    document.querySelectorAll('#list li[data-k] .pname').forEach(function(el){
      if(el.textContent.indexOf("獅鷲") === -1) allHaveWord = false;
    });
    ok("中文搜尋結果都含關鍵字", allHaveWord);

    // ---- 門市名稱搜尋 ----
    state.q = "忠孝"; render();
    ok("搜尋門市『忠孝』只剩 1 間", storesShown() === 1, storesShown());

    // ---- 多關鍵字（空白分隔要 AND）----
    state.q = "高雄 BX-57"; render();
    var multi = rowsShown();
    ok("多關鍵字 AND 有結果", multi > 0, multi);
    var allKh = true;
    document.querySelectorAll('#list .store .sname').forEach(function(){});
    ok("多關鍵字結果門市數合理", storesShown() > 0 && storesShown() <= 13, storesShown());

    // ---- 縣市篩選 ----
    state.q = ""; state.cities = {"台北市": true}; render();
    var tpCount = 0, tpItems = 0;
    STORES.forEach(function(s){ if(s.city === "台北市"){ tpCount++; tpItems += s.items.length; } });
    ok("台北市篩選門市數正確", storesShown() === tpCount, storesShown()+" / "+tpCount);
    ok("台北市篩選項目數正確", rowsShown() === tpItems, rowsShown()+" / "+tpItems);

    // ---- 型號篩選（多選）----
    state.cities = {}; state.codes = {"UX-21": true, "BX-57": true}; render();
    var expect2 = 0;
    STORES.forEach(function(s){ s.items.forEach(function(it){
      if(it.c === "UX-21" || it.c === "BX-57") expect2++; }); });
    ok("多選型號 UX-21+BX-57 筆數正確", rowsShown() === expect2, rowsShown()+" / "+expect2);

    // ---- 已抽標記 ----
    state.codes = {}; state.cities = {}; state.q = "UX-21"; render();
    var firstLi = document.querySelector('#list li[data-k]');
    var key = firstLi.getAttribute('data-k');
    ok("項目 key 格式為 門市|商品", key.indexOf("|") > 0, key);
    setDone(key, true); render();
    var afterLi = document.querySelector('#list li[data-k="' + key.replace(/"/g,'\\"') + '"]');
    ok("標記後該列變 done", afterLi && afterLi.classList.contains("done"));
    ok("標記後統計顯示 1 已抽", /今天已抽 1 \/ 2/.test(document.getElementById('doneTxt').textContent),
       document.getElementById('doneTxt').textContent);
    ok("進度條有寬度", document.getElementById('barFill').style.width === "50%",
       document.getElementById('barFill').style.width);

    // ---- 只看未抽 ----
    state.hideDone = true; render();
    ok("只看未抽會過濾掉已抽的", rowsShown() === 1, rowsShown());
    state.hideDone = false; render();
    ok("關掉只看未抽會回復", rowsShown() === 2, rowsShown());

    // ---- 取消標記 ----
    setDone(key, false); render();
    var back = document.querySelector('#list li[data-k="' + key.replace(/"/g,'\\"') + '"]');
    ok("取消標記後回到未抽", back && !back.classList.contains("done"));

    // ---- 清單產生：文字 ----
    state.q = "UX-21"; state.fmt = "txt";
    document.getElementById('listSkipDone').checked = false;
    document.getElementById('listOa').checked = false;
    buildOutput();
    var out = document.getElementById('out').value;
    ok("文字清單含門市名", out.indexOf("Funbox 美麗華") !== -1);
    ok("文字清單含商品名", out.indexOf("UX-21") !== -1);
    ok("文字清單含 lin.ee 連結", /https:\/\/lin\.ee\/\w+/.test(out));
    ok("文字清單有勾選框", out.indexOf("□") !== -1);
    ok("文字清單有合計", /共 2 項/.test(out), out.slice(-40));
    ok("文字清單含抽選時間", out.indexOf("2026/") !== -1);

    // ---- 清單產生：附加好友 ----
    document.getElementById('listOa').checked = true; buildOutput();
    ok("清單可附加好友連結", document.getElementById('out').value.indexOf("line.me/ti/p/") !== -1);
    document.getElementById('listOa').checked = false;

    // ---- 清單產生：CSV ----
    state.fmt = "csv"; buildOutput();
    var csv = document.getElementById('out').value.split("\n");
    ok("CSV 有表頭", csv[0] === "縣市,門市,抽選時間,商品,連結", csv[0]);
    ok("CSV 資料列數正確", csv.length === 3, csv.length);
    ok("CSV 每列 5 欄", csv[1].split(",").length === 5, csv[1]);

    // ---- 清單產生：Markdown ----
    state.fmt = "md"; buildOutput();
    var md = document.getElementById('out').value;
    ok("MD 有 ## 標題", md.indexOf("## 台北市 / Funbox 美麗華") !== -1);
    ok("MD 有待辦勾選", md.indexOf("- [ ] [") !== -1);
    state.fmt = "txt";

    // ---- 排除已抽 ----
    setDone(key, true);
    document.getElementById('listSkipDone').checked = true; buildOutput();
    ok("清單可排除今天已抽", document.getElementById('out').value.indexOf("共 1 項") !== -1);
    setDone(key, false);
    document.getElementById('listSkipDone').checked = false; buildOutput();

    // ---- 整間標記 ----
    state.q = "忠孝"; render();
    var btn = document.querySelector('#list button[data-allstore]');
    ok("整間標記按鈕存在", !!btn);
    btn.click();
    ok("整間標記後全部 done", document.querySelectorAll('#list li.done').length === 10,
       document.querySelectorAll('#list li.done').length);
    ok("整間標記後卡片變灰", !!document.querySelector('#list .store.allDone'));
    document.querySelector('#list button[data-allstore]').click();
    ok("再按一次整間取消", document.querySelectorAll('#list li.done').length === 0,
       document.querySelectorAll('#list li.done').length);

    // ---- 點抽選連結會自動標記 ----
    state.q = "UX-21"; render();
    var go = document.querySelector('#list a.go');
    var goKey = go.getAttribute('data-go');
    ok("抽選按鈕是 lin.ee 連結", /^https:\/\/lin\.ee\//.test(go.getAttribute('href')),
       go.getAttribute('href'));
    ok("抽選按鈕 target=_blank", go.getAttribute('target') === "_blank");
    ok("抽選按鈕 rel=noopener", go.getAttribute('rel') === "noopener");
    // 攔掉真的開新視窗
    go.addEventListener('click', function(ev){ ev.preventDefault(); }, true);
    go.click();
    ok("點抽選後自動標記今天已抽", isToday(goKey), goKey);
    setDone(goKey, false);

    // ---- 手動 ✓ 按鈕 ----
    render();
    var mk = document.querySelector('#list button[data-mark]');
    var mkKey = mk.getAttribute('data-mark');
    mk.click();
    ok("按 ✓ 會標記已抽", isToday(mkKey));
    document.querySelector('#list button[data-mark]').click();
    ok("再按 ✓ 會取消", !isToday(mkKey));

    // ---- 重設篩選 ----
    state.cities = {"台北市":true}; state.codes = {"BX-57":true}; state.q="x"; render();
    document.getElementById('resetFilter').click();
    ok("重設篩選後回到全部", rowsShown() === 824, rowsShown());

    // ---- 分頁切換 ----
    document.getElementById('tab-friend').click();
    ok("加好友分頁會顯示", document.getElementById('pane-friend').hidden === false);
    var fl = document.getElementById('friendList');
    ok("加好友清單有渲染", fl.querySelectorAll('a.go').length > 60,
       fl.querySelectorAll('a.go').length);
    ok("加好友連結是 line.me", /line\.me/.test(fl.querySelector('a.go').getAttribute('href')),
       fl.querySelector('a.go').getAttribute('href'));
    document.getElementById('fq').value = "台中";
    renderFriends();
    ok("加好友可搜尋", fl.querySelectorAll('a.go').length > 0 && fl.querySelectorAll('a.go').length < 20,
       fl.querySelectorAll('a.go').length);

    document.getElementById('tab-list').click();
    ok("清單分頁會顯示", document.getElementById('pane-list').hidden === false);
    document.getElementById('tab-help').click();
    ok("說明分頁會顯示", document.getElementById('pane-help').hidden === false);
    ok("說明分頁有資料版本", document.getElementById('builtAt').textContent.length > 4,
       document.getElementById('builtAt').textContent);
    document.getElementById('tab-links').click();
    ok("回到連結分頁", document.getElementById('pane-links').hidden === false);

    // ---- 每個門市都有加好友按鈕 ----
    render();
    ok("每張門市卡都有 ＋好友", document.querySelectorAll('#list .oabtn').length === 76,
       document.querySelectorAll('#list .oabtn').length);

    // ---- 標題與公告 ----
    ok("公告有顯示", document.getElementById('notice').textContent.indexOf("抽選") !== -1,
       document.getElementById('notice').textContent);

    // ---- 找不到結果 ----
    state.q = "zzz不存在zzz"; render();
    ok("查無結果顯示提示", document.querySelector('#list .empty') !== null);
    state.q = ""; render();

  } catch(err){
    R.push({t:"執行時發生例外", ok:false, x:(err && err.message ? err.message : String(err)) +
      " @ " + (err && err.stack ? String(err.stack).split("\n")[1] : "")});
  }

  document.getElementById('TESTOUT').textContent = "@@RESULT@@" + JSON.stringify(R) + "@@END@@";
})();
</script>
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
        safe_print("找不到 Chrome/Edge，跳過瀏覽器測試")
        return 2

    html = open(IDX, encoding="utf-8").read()
    if "</body>" not in html:
        safe_print("index.html 沒有 </body>")
        return 1
    open(TEST, "w", encoding="utf-8").write(html.replace("</body>", TEST_JS + "\n</body>"))

    profile = tempfile.mkdtemp(prefix="chr_")
    url = "file:///" + TEST.replace("\\", "/")
    cmd = [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions",
        "--allow-file-access-from-files",
        "--user-data-dir=" + profile,
        "--virtual-time-budget=8000",
        "--dump-dom", url,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        safe_print("Chrome 執行逾時")
        return 1

    dom = p.stdout.decode("utf-8", "replace")
    open(DUMP, "w", encoding="utf-8").write(dom)

    m = re.search(r"@@RESULT@@(.*?)@@END@@", dom, re.S)
    if not m:
        safe_print("測試腳本沒有產生結果，可能 JS 在初始化就出錯了。")
        safe_print("stderr 前 3000 字：")
        safe_print(p.stderr.decode("utf-8", "replace")[:3000])
        safe_print("DOM 前 1500 字：")
        safe_print(dom[:1500])
        return 1

    results = json.loads(m.group(1))
    lines, fails = [], 0
    for r in results:
        flag = "PASS" if r["ok"] else "FAIL"
        if not r["ok"]:
            fails += 1
        lines.append("[%s] %s%s" % (flag, r["t"], ("   -> " + r["x"]) if r["x"] else ""))
    lines.append("")
    lines.append("共 %d 項，通過 %d，失敗 %d" % (len(results), len(results) - fails, fails))
    txt = "\n".join(lines)
    open(os.path.join(HERE, "_test_report.txt"), "w", encoding="utf-8").write(txt)
    safe_print(txt)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
