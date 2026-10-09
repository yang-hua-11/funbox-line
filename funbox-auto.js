"ui";
/**
 * Funbox 陀螺 LINE 抽選 — App 內全功能版（Auto.js / AutoX）
 * ============================================================
 * 打開就有畫面：線上抓最新資料 → 搜尋/篩選縣市與型號 → 按「開始自動抽」
 *   → App 自動一個個開連結、看到「參加抽獎」就點、點完立刻換下一個。
 *
 * 你平常只要：打開 App → 勾要抽的 → 按開始。不用複製貼上任何連結。
 *
 * 第一次要做的（只做一次）：
 *   1. 手機裝 Auto.js / AutoX，開好「無障礙 / 協助工具」權限。
 *   2. 把這個檔案內容整段貼進 Auto.js 新建的腳本，存檔。
 *   3. 抽之前，先在網頁「加好友」分頁把要抽的門市官方帳號加好友
 *      （沒加好友的連結會卡在加入好友畫面，會被自動跳過）。
 */

// ============ 設定（通常不用改） ============
var DATA_URL       = "https://yang-hua-11.github.io/funbox-line/data.json";
var SOURCE_URL     = "https://uxux11.github.io/funbox-line/";  // 原始來源（同步清單用）
var LINE_PACKAGE   = "jp.naver.line.android";  // LINE App 套件名，連結強制用它開（不要丟給瀏覽器）
var LINE_PACKAGE   = "jp.naver.line.android";  // LINE App 套件名，強制用它開連結（避免被瀏覽器攔走）
var 抽獎按鈕文字     = "參加抽獎";  // 官方若改字（例如「參加」「應募」），改這裡
var 等按鈕最久秒數   = 4;           // 一個連結最多等幾秒還沒出現按鈕就跳過
var 掃描間隔秒數     = 0.08;        // 多久掃一次按鈕，越小抓越快
var 確認消失最久秒數 = 1.2;         // 點完後最多等幾秒確認按鈕消失（消失=成功，立刻換下一個）
var 點完停留秒數     = 0;           // 已改成偵測按鈕消失，不再固定空等
var 下一個前等秒數   = 0.05;        // 開下一個連結前的極短緩衝
var STORAGE_NAME   = "funbox_auto"; // 存已抽記錄用
// ==========================================

var storage = storages.create(STORAGE_NAME);

// ============ 短網址加速（加速核心） ============
// lin.ee 開啟時 LINE 要先做一次短網址跳轉，很慢。改用電腦預先算好的對照表
// （lin.ee → 最終 liff.line.me 網址），抽的時候直接開 liff，省掉每個連結 1~3 秒。
var RESOLVED_URL = "https://yang-hua-11.github.io/funbox-line/resolved_links.json";
var LIFF_MAP = {};        // { "lin.ee網址": "liff最終網址" }

// 載入對照表（在 loadData 時一起抓；抓不到就算了，照樣用原始 lin.ee 抽）
function loadLiffMap() {
    try {
        var res = http.get(RESOLVED_URL);
        if (res.statusCode === 200) {
            var obj = JSON.parse(res.body.string());
            var arr = obj.links || [];
            for (var i = 0; i < arr.length; i++) {
                var o = arr[i];
                if (o.url && o.resolved && o.resolved.indexOf("liff.line.me") >= 0) {
                    LIFF_MAP[o.url] = o.resolved;
                }
            }
        }
    } catch (e) {}
}
// 查某個 lin.ee 對應的 liff；沒有就回傳 null
function 查liff(url) {
    return LIFF_MAP[url] || null;
}

// 手機端把一個 lin.ee 解析成最終 liff 網址（用 Java HttpURLConnection 跟隨跳轉）。
// 有快取先用快取；解析不出來回傳 null（照樣用原始 lin.ee 抽）。
var liff快取 = storages.create("funbox_liff");  // 永久存已解析結果
function 解析一個liff(url) {
    var cached = liff快取.get(url, null);
    if (cached) return cached;
    try {
        var URLClass = java.net.URL;
        var conn = new URLClass(url).openConnection();
        conn.setInstanceFollowRedirects(true);   // 自動跟隨跳轉
        conn.setConnectTimeout(8000);
        conn.setReadTimeout(8000);
        conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 10)");
        conn.connect();
        conn.getResponseCode();                   // 觸發連線完成跳轉
        var 最終 = String(conn.getURL().toString());
        conn.getInputStream().close();
        if (最終 && 最終.indexOf("liff.line.me") >= 0) {
            liff快取.put(url, 最終);
            return 最終;
        }
    } catch (e) {}
    return null;
}

// 把一批連結平行解析成 liff，寫進 LIFF_MAP。onProgress(已完成, 總數) 回報進度。
// 用 Java 的 AtomicInteger 做共享計數/取索引（不依賴 Auto.js 特有的 lock API，較穩）。
function 批次解析liff(urls, onProgress) {
    // 先把已快取的灌進 LIFF_MAP，並挑出還沒解析的
    var 待解析 = [];
    for (var i = 0; i < urls.length; i++) {
        var hit = liff快取.get(urls[i], null);
        if (hit) { LIFF_MAP[urls[i]] = hit; continue; }
        if (urls[i].indexOf("lin.ee") >= 0 && !LIFF_MAP[urls[i]]) 待解析.push(urls[i]);
    }
    if (待解析.length === 0) { if (onProgress) onProgress(0, 0); return; }

    var Atomic = java.util.concurrent.atomic.AtomicInteger;
    var 下標 = new Atomic(0);     // 下一個要處理的索引
    var 已完成 = new Atomic(0);   // 已完成數
    var 總數 = 待解析.length;
    var 並發 = 8;
    var 緒 = [];
    for (var t = 0; t < 並發; t++) {
        緒.push(threads.start(function () {
            while (true) {
                var k = 下標.getAndIncrement();   // 原子取下一個索引
                if (k >= 總數) break;
                var u = 待解析[k];
                var liff = 解析一個liff(u);
                if (liff) LIFF_MAP[u] = liff;      // 不同 key 寫入，衝突可忽略
                var d = 已完成.incrementAndGet();
                if (onProgress) onProgress(d, 總數);
            }
        }));
    }
    緒.forEach(function (th) { th.join(); });
}

// ============ 同步清單：直接解析 uxux11 的 HTML（翻自 extract.py） ============
// 去標籤、解 HTML 實體、壓空白
function 清字串(s) {
    s = s.replace(/<[^>]+>/g, "");
    s = s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
         .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ");
    s = s.replace(/\u3000/g, " ");
    return s.replace(/\s+/g, " ").trim();
}
// 從品名抓型號，例如 UX-21、BXG-01、CX-00
function 抓型號(name) {
    var m = name.toUpperCase().match(/([A-Z]{2,4}-\d{1,3})/);
    return m ? m[1] : "";
}
// 解析整個 HTML，回傳門市陣列 [{city,name,time,st,items:[{p,c,u}]}]
function 解析門市(src) {
    var stores = [];
    // 以 data-draw-city 當每間門市的切點
    var storeRe = /<div class="draw-store"[^>]*data-draw-city="([^"]*)"[^>]*>/g;
    var starts = [];
    var mm;
    while ((mm = storeRe.exec(src)) !== null) {
        starts.push({ city: mm[1], tag: mm[0], begin: storeRe.lastIndex });
    }
    for (var i = 0; i < starts.length; i++) {
        var city = 清字串(starts[i].city);
        var begin = starts[i].begin;
        var end = (i + 1 < starts.length) ? (starts[i + 1].begin - starts[i + 1].tag.length) : src.length;
        // 用下一個門市標籤的起點當結束；上面 begin 已過標籤，這裡用 src 片段
        var block = src.substring(begin, (i + 1 < starts.length) ? src.indexOf(starts[i + 1].tag, begin) : src.length);

        // 門市開始時段
        var st = "";
        var stm = starts[i].tag.match(/data-draw-start-time="([^"]*)"/);
        if (stm) st = 清字串(stm[1]);

        // 門市名
        var nm = block.match(/<div class="draw-store-name"[^>]*>([\s\S]*?)<\/div>/);
        var name = nm ? 清字串(nm[1]) : "";
        if (!name) continue;

        // 抽選時間
        var tm = block.match(/<div class="draw-start"[^>]*>([\s\S]*?)<\/div>/);
        var timeTxt = tm ? 清字串(tm[1]) : "";
        timeTxt = timeTxt.replace(/^抽選時間[：:]\s*/, "");

        // 商品項：draw-item 外層帶 data-draw-href，內層 draw-product 是品名
        var items = [], seen = {};
        var itemRe = /<div[^>]*class="draw-item[^"]*"[^>]*data-draw-href="([^"]+)"[^>]*>\s*<div class="draw-product"[^>]*>([\s\S]*?)<\/div>/g;
        var im;
        while ((im = itemRe.exec(block)) !== null) {
            var u = 清字串(im[1]);
            var p = 清字串(im[2]);
            if (!p || !u || seen[u]) continue;
            seen[u] = 1;
            items.push({ p: p, c: 抓型號(p), u: u });
        }
        if (items.length > 0) {
            stores.push({ city: city, name: name, time: timeTxt, st: st, items: items });
        }
    }
    return stores;
}

// 全域資料
var DATA = null;        // 抓下來的 data.json
var STORES = [];        // 門市陣列
var CITIES = [];        // 縣市清單
var CODES = [];         // 型號清單
var TIMES = [];         // 開始時間清單
var selCities = {};     // 已選縣市
var selCodes = {};      // 已選型號
var selTimes = {};      // 已選時間
var keyword = "";       // 搜尋關鍵字

// ---------- 已抽記錄：{ "門市|品名": "YYYY-MM-DD" } ----------
function todayStr() {
    var d = new Date();
    var m = d.getMonth() + 1, day = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (day < 10 ? "0" : "") + day;
}
var TODAY = todayStr();
function getDone() { return storage.get("done", {}); }
function setDoneMap(o) { storage.put("done", o); }
function itemKey(store, item) { return store.name + "|" + item.p; }
function isToday(k) { var d = getDone(); return d[k] === TODAY; }
function markDone(k) { var d = getDone(); d[k] = TODAY; setDoneMap(d); }

// ============ 畫面 ============
ui.layout(
    <vertical>
        <ScrollView layout_weight="1">
            <vertical padding="12">
                <text textSize="18sp" textColor="#1f3f66" textStyle="bold">Funbox 陀螺 · 全自動連抽</text>
                <text id="status" textSize="12sp" textColor="#6b7480" marginTop="2">載入資料中…</text>

                <input id="kw" hint="搜尋型號或門市，例如 UX-21、忠孝" textSize="15sp" marginTop="8"/>

                <text textSize="13sp" textColor="#6b7480" textStyle="bold" marginTop="6">縣市（可複選，不選=全部）</text>
                <vertical id="cityChips" marginTop="2"/>

                <text textSize="13sp" textColor="#6b7480" textStyle="bold" marginTop="8">型號（可複選，不選=全部）</text>
                <vertical id="codeChips" marginTop="2"/>

                <text textSize="13sp" textColor="#6b7480" textStyle="bold" marginTop="8">開始時間（可複選，不選=全部）</text>
                <vertical id="timeChips" marginTop="2"/>

                <horizontal marginTop="10" gravity="center_vertical">
                    <checkbox id="skipDone" checked="true"/>
                    <text textSize="14sp" marginLeft="4" layout_weight="1">排除今天已抽</text>
                    <button id="reset" style="Widget.AppCompat.Button.Borderless" textSize="12sp" textColor="#9aa0a6">清除今天已抽記錄</button>
                </horizontal>
            </vertical>
        </ScrollView>

        <vertical padding="12 8">
            <text id="count" textSize="15sp" textColor="#06c755" textStyle="bold">—</text>
            <horizontal marginTop="2">
                <button id="sync" style="Widget.AppCompat.Button.Borderless" layout_weight="1">🔄 同步清單</button>
                <button id="sortcfg" style="Widget.AppCompat.Button.Borderless" layout_weight="1">⇅ 排序設定</button>
            </horizontal>
            <button id="start" style="Widget.AppCompat.Button.Colored" marginTop="2">▶ 開始自動抽</button>
        </vertical>
    </vertical>
);

// ============ 抓資料 ============
function loadData() {
    ui.status.setText("載入資料中…");
    threads.start(function () {
        var ok = false, err = "";
        try {
            var res = http.get(DATA_URL);
            if (res.statusCode === 200) {
                DATA = JSON.parse(res.body.string());
                STORES = DATA.stores || [];
                buildIndex();
                loadLiffMap();   // 順便抓短網址加速對照表
                ok = true;
            } else {
                err = "HTTP " + res.statusCode;
            }
        } catch (e) {
            err = "" + e;
        }
        ui.run(function () {
            if (ok) {
                var items = 0;
                STORES.forEach(function (s) { items += s.items.length; });
                ui.status.setText("資料 " + (DATA.builtAt || "") + " · " + STORES.length + " 門市 · " + items + " 項");
                renderChips();
                updateCount();
            } else {
                ui.status.setText("載入失敗：" + err + "（檢查網路後重開）");
                toast("抓不到資料：" + err);
            }
        });
    });
}

function buildIndex() {
    var citySeen = {}, codeSeen = {}, timeSeen = {};
    CITIES = []; CODES = []; TIMES = [];
    STORES.forEach(function (s) {
        if (!citySeen[s.city]) { citySeen[s.city] = true; CITIES.push(s.city); }
        var t = (s.st || "").trim();
        if (t && !timeSeen[t]) { timeSeen[t] = true; TIMES.push(t); }
        s.items.forEach(function (it) {
            var c = it.c || "其他";
            if (!codeSeen[c]) { codeSeen[c] = true; CODES.push(c); }
        });
    });
    CODES.sort(function (a, b) {
        if (a === "其他") return 1;
        if (b === "其他") return -1;
        var pa = a.split("-"), pb = b.split("-");
        if (pa[0] !== pb[0]) return pa[0] < pb[0] ? -1 : 1;
        return (parseInt(pa[1]) || 0) - (parseInt(pb[1]) || 0);
    });
    TIMES.sort(function (a, b) { return a.localeCompare(b, undefined, { numeric: true }); });
}

// ============ 篩選晶片（自動換行，每排 PER_ROW 個） ============
var PER_ROW = 4;   // 一排放幾個按鈕，太擠可改小

function styleChip(v, on) {
    v.setBackgroundColor(colors.parseColor(on ? "#1f3f66" : "#eef0f2"));
    v.setTextColor(colors.parseColor(on ? "#ffffff" : "#3d444c"));
}
function anyOn(o) { for (var k in o) { if (o[k]) return true; } return false; }

// 把一堆標籤，一排 PER_ROW 個，塞進 container（縱向容器）
function fillChips(container, labels, isOn, onTap) {
    container.removeAllViews();
    var row = null;
    for (var i = 0; i < labels.length; i++) {
        if (i % PER_ROW === 0) {
            row = ui.inflate(<horizontal/>, container, false);
            container.addView(row);
        }
        var label = labels[i];
        var chip = ui.inflate(
            <text padding="12 8" margin="0 6 6 0" textSize="13sp" gravity="center"/>, row, false);
        chip.setText(label);
        styleChip(chip, isOn(label));
        (function (lb) { chip.on("click", function () { onTap(lb); }); })(label);
        row.addView(chip);
    }
}

function renderChips() {
    // 縣市：第一個是「全部」
    var cityLabels = ["全部"].concat(CITIES);
    fillChips(ui.cityChips, cityLabels,
        function (lb) { return lb === "全部" ? !anyOn(selCities) : !!selCities[lb]; },
        function (lb) {
            if (lb === "全部") selCities = {};
            else selCities[lb] = !selCities[lb];
            renderChips(); updateCount();
        });

    // 型號：第一個是「全部」
    var codeLabels = ["全部"].concat(CODES);
    fillChips(ui.codeChips, codeLabels,
        function (lb) { return lb === "全部" ? !anyOn(selCodes) : !!selCodes[lb]; },
        function (lb) {
            if (lb === "全部") selCodes = {};
            else selCodes[lb] = !selCodes[lb];
            renderChips(); updateCount();
        });

    // 開始時間：第一個是「全部」
    var timeLabels = ["全部"].concat(TIMES);
    fillChips(ui.timeChips, timeLabels,
        function (lb) { return lb === "全部" ? !anyOn(selTimes) : !!selTimes[lb]; },
        function (lb) {
            if (lb === "全部") selTimes = {};
            else selTimes[lb] = !selTimes[lb];
            renderChips(); updateCount();
        });
}

// ============ 篩選邏輯（跟網頁一致） ============
function matchKw(store, item) {
    if (!keyword) return true;
    var hay = (store.city + " " + store.name + " " + item.p + " " + (item.c || "")).toLowerCase();
    var parts = keyword.toLowerCase().split(/\s+/).filter(Boolean);
    for (var i = 0; i < parts.length; i++) { if (hay.indexOf(parts[i]) === -1) return false; }
    return true;
}
function filteredLinks() {
    var cityOn = anyOn(selCities), codeOn = anyOn(selCodes), timeOn = anyOn(selTimes);
    var skip = ui.skipDone.isChecked();
    var out = [], seen = {};
    STORES.forEach(function (s) {
        if (cityOn && !selCities[s.city]) return;
        if (timeOn && !selTimes[(s.st || "").trim()]) return;
        s.items.forEach(function (it) {
            var c = it.c || "其他";
            if (codeOn && !selCodes[c]) return;
            if (!matchKw(s, it)) return;
            var k = itemKey(s, it);
            if (skip && isToday(k)) return;
            if (!it.u || seen[it.u]) return;
            seen[it.u] = 1;
            out.push({ url: it.u, key: k, name: s.name, p: it.p, city: s.city, code: c });
        });
    });
    return 套用排序(out);
}

// ============ 排序設定 ============
// 設定存這裡：{ codes:["UX-21",...], cities:["台北市",...], mode:"code" | "city" }
var 排序設定儲存 = storages.create("funbox_sort");
function 讀排序設定() {
    return {
        codes: 排序設定儲存.get("codes", []),   // 想抽的型號/商品關鍵字，越前面越優先
        cities: 排序設定儲存.get("cities", []),  // 地區，越前面越優先
        mode: 排序設定儲存.get("mode", "code")   // "code"=商品優先；"city"=地區優先
    };
}
function 存排序設定(codes, cities, mode) {
    排序設定儲存.put("codes", codes);
    排序設定儲存.put("cities", cities);
    排序設定儲存.put("mode", mode);
}
// 算一個項目在某份優先清單裡的名次（越小越優先）；沒列出的排最後（給一個大數）
function 優先名次(值, 清單) {
    for (var i = 0; i < 清單.length; i++) {
        var kw = 清單[i];
        if (!kw) continue;
        // 型號用「開頭相符或包含」，地區用完全相符或包含，都用 indexOf 容錯
        if (值 && 值.indexOf(kw) >= 0) return i;
    }
    return 99999;  // 沒列出 → 排後面
}
// 依設定排序（穩定排序：相同權重維持原本順序）
function 套用排序(list) {
    var cfg = 讀排序設定();
    var 有排序 = (cfg.codes.length > 0 || cfg.cities.length > 0);
    if (!有排序) return list;  // 沒設定就維持原順序
    // 幫每個項目算 code 名次、city 名次，並記原始索引（穩定排序用）
    for (var i = 0; i < list.length; i++) {
        list[i]._ci = 優先名次((list[i].code || "") + " " + (list[i].p || ""), cfg.codes);
        list[i]._ri = 優先名次(list[i].city || "", cfg.cities);
        list[i]._idx = i;
    }
    list.sort(function (a, b) {
        var 第一, 第二;
        if (cfg.mode === "city") { 第一 = ["_ri", "_ci"]; }  // 地區優先
        else { 第一 = ["_ci", "_ri"]; }                      // 商品優先（預設）
        if (a[第一[0]] !== b[第一[0]]) return a[第一[0]] - b[第一[0]];
        if (a[第一[1]] !== b[第一[1]]) return a[第一[1]] - b[第一[1]];
        return a._idx - b._idx;  // 權重相同 → 維持原順序
    });
    return list;
}
function updateCount() {
    var n = filteredLinks().length;
    ui.count.setText("目前篩選出 " + n + " 個連結");
}

// ============ 事件 ============
ui.kw.on("text_changed", function (s) { keyword = s.toString().trim(); updateCount(); });
ui.skipDone.on("check", function () { updateCount(); });
ui.reset.on("click", function () {
    var d = getDone(), cnt = 0;
    Object.keys(d).forEach(function (k) { if (d[k] === TODAY) { delete d[k]; cnt++; } });
    setDoneMap(d);
    updateCount();
    toast("已清除今天 " + cnt + " 筆記錄");
});

// 排序設定：輸入優先型號、優先地區、選商品/地區優先
ui.sortcfg.on("click", function () {
    var cfg = 讀排序設定();
    var codesStr = cfg.codes.join("\n");
    var citiesStr = cfg.cities.join("\n");
    // 1) 問型號優先順序（多行，一行一個，越上面越優先）
    dialogs.rawInput("想抽的陀螺/商品優先順序\n（每行一個，越上面越優先，例如 UX-21）", codesStr)
        .then(function (c1) {
            if (c1 === null) return;  // 取消
            var newCodes = ("" + c1).split("\n").map(function (x) { return x.trim(); }).filter(Boolean);
            // 2) 問地區優先順序
            dialogs.rawInput("地區優先順序\n（每行一個縣市，越上面越優先，例如 台北市）", citiesStr)
                .then(function (c2) {
                    if (c2 === null) return;
                    var newCities = ("" + c2).split("\n").map(function (x) { return x.trim(); }).filter(Boolean);
                    // 3) 選主排序：商品優先 or 地區優先
                    dialogs.select("先依哪個排序？", ["商品優先，再依地區", "地區優先，再依商品"])
                        .then(function (idx) {
                            if (idx < 0) return;
                            var mode = (idx === 1) ? "city" : "code";
                            存排序設定(newCodes, newCities, mode);
                            updateCount();
                            toast("排序已儲存：" + (mode === "city" ? "地區優先" : "商品優先")
                                  + "，型號 " + newCodes.length + " 項、地區 " + newCities.length + " 項");
                        });
                });
        });
});

// 同步清單：直接抓 uxux11 最新 HTML、解析、更新清單（不用等電腦）
var syncing = false;
ui.sync.on("click", function () {
    if (syncing) return;
    syncing = true;
    ui.status.setText("同步中…抓取 uxux11 最新資料");
    threads.start(function () {
        var 新門市 = null, err = "";
        try {
            var res = http.get(SOURCE_URL, { headers: { "User-Agent": "Mozilla/5.0" } });
            if (res.statusCode === 200) {
                var html = res.body.string();
                新門市 = 解析門市(html);
            } else {
                err = "HTTP " + res.statusCode;
            }
        } catch (e) {
            err = "" + e;
        }

        // 保護：抓到 0 筆幾乎一定是來源改版/解析失效，保留舊清單不覆蓋
        if (!新門市 || 新門市.length === 0) {
            ui.run(function () {
                syncing = false;
                ui.status.setText("同步失敗：" + (err || "沒解析到門市，可能來源改版") + "（已保留原清單）");
                toast("同步失敗，已保留原本清單");
            });
            return;
        }

        // 1) 先更新門市清單與畫面
        STORES = 新門市;
        var items = 0, 全部連結 = [];
        STORES.forEach(function (s) {
            items += s.items.length;
            s.items.forEach(function (it) { if (it.u) 全部連結.push(it.u); });
        });
        (function (st, it) { ui.run(function () {
            buildIndex();
            renderChips();
            updateCount();
            ui.status.setText("已同步 " + st + " 門市 · " + it + " 項，開始加速解析…");
        }); })(STORES.length, items);

        // 2) 同步後直接在手機上把 lin.ee 全部解析成 liff（加速），顯示進度
        LIFF_MAP = {};  // 重算（可能是全新一批連結）
        批次解析liff(全部連結, function (done, tot) {
            if (tot > 0 && (done % 20 === 0 || done === tot)) {
                (function (d, t) { ui.run(function () {
                    ui.status.setText("加速解析中… " + d + "/" + t);
                }); })(done, tot);
            }
        });

        // 3) 完成
        var 加速數 = 0;
        for (var kk in LIFF_MAP) { if (LIFF_MAP.hasOwnProperty(kk)) 加速數++; }
        (function (st, it, acc) { ui.run(function () {
            syncing = false;
            ui.status.setText("同步+加速完成 · " + st + " 門市 · " + it + " 項 · 加速網址 " + acc + " 個");
            toast("完成！" + st + " 門市 / " + it + " 項，已加速 " + acc + " 個");
        }); })(STORES.length, items, 加速數);
    });
});

ui.start.on("click", function () {
    var list = filteredLinks();
    if (!list.length) { toast("目前沒有可抽的連結"); return; }
    // 需要無障礙權限才能自動點
    if (!auto.service) {
        toast("請先開啟無障礙服務");
        app.startActivity({ action: "android.settings.ACCESSIBILITY_SETTINGS" });
        return;
    }
    dialogs.confirm("開始自動抽", "共 " + list.length + " 個連結，開始後手機會自動操作，中途要停就切回本 App 按返回。要開始嗎？")
        .then(function (yes) {
            if (yes) runAuto(list);
        });
});

// ============ 自動連抽（背景執行緒跑，不卡 UI） ============
var running = false;
function runAuto(list) {
    if (running) return;
    running = true;
    threads.start(function () {
        // ===== 加速：把 lin.ee 換成已預解析好的 liff 網址 =====
        // 開抽前，用網站上已算好的對照表（lin.ee → liff），直接換掉連結，
        // 抽的時候直接開 liff，省掉 LINE 的短網址跳轉（每個省 1~3 秒）。
        var 換掉 = 0;
        for (var m = 0; m < list.length; m++) {
            var liff = 查liff(list[m].url);
            if (liff) { list[m].url = liff; 換掉++; }
        }
        if (換掉 > 0) {
            (function (n) { ui.run(function () {
                ui.status.setText("已套用加速網址 " + n + " 個，開始抽…");
            }); })(換掉);
        }

        // ===== 連抽 =====
        var 成功 = 0, 跳過 = 0, 處理數 = 0;
        var 跳過清單 = [];   // 記下沒抽成功的門市+品名
        for (var i = 0; i < list.length; i++) {
            if (!running) break;
            處理數++;
            var item = list[i];
            var 序 = "(" + (i + 1) + "/" + list.length + ") ";
            // 用區域變數，避免閉包抓到迴圈最後一個值
            (function (txt) { ui.run(function () { ui.status.setText(txt); }); })(序 + item.name + " " + item.p);

            開連結用LINE(item.url);
            // 開了連結就立刻狂掃按鈕，一出現馬上點，不固定空等
            var btn = 找抽獎按鈕(等按鈕最久秒數 * 1000);
            if (btn) {
                點它(btn);   // 內部會偵測按鈕消失，一消失立刻回來，不固定空等
                markDone(item.key);
                成功++;
            } else {
                跳過++;
                跳過清單.push("• " + item.name + "｜" + item.p);
            }
            // 不回桌面，直接開下一個連結（省掉 home + 重載的時間）
            if (下一個前等秒數 > 0) sleep(下一個前等秒數 * 1000);
        }
        running = false;
        var 停了 = (處理數 < list.length);  // 中途被按返回停掉
        ui.run(function () {
            var head = (停了 ? "已停止" : "抽完了") + "：成功 " + 成功 + "、跳過 " + 跳過;
            var body;
            if (跳過清單.length === 0) {
                body = "\n（全部都抽到了，沒有跳過的）";
            } else {
                body = "\n\n沒抽成功的：\n" + 跳過清單.join("\n");
            }
            ui.status.setText(head + body);
            updateCount();
        });
        toast((停了 ? "已停止" : "抽完了") + "！成功 " + 成功 + "、跳過 " + 跳過);
    });
}

// 切回 App 按返回 → 停止自動抽
ui.emitter.on("back_pressed", function () {
    if (running) { running = false; toast("已停止"); }
});

// 強制用 LINE App 開連結（不要丟給瀏覽器，否則會卡在「下載LINE/在LINE中打開」頁）
// 直接用 Android 原生 Intent 並 setPackage，等同 adb 的 am start -p，最強制。
function 開連結用LINE(url) {
    try {
        var Intent = android.content.Intent;
        var Uri = android.net.Uri;
        var intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        intent.setPackage(LINE_PACKAGE);                    // 強制指定用 LINE 開
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);     // 從背景啟動需要
        context.startActivity(intent);
        return;
    } catch (e) {}
    // 退路 1：用 app.startActivity 指定套件
    try {
        app.startActivity({ action: "android.intent.action.VIEW", data: url, packageName: LINE_PACKAGE });
        return;
    } catch (e2) {}
    // 退路 2：一般開法（可能會進瀏覽器）
    try { app.openUrl(url); } catch (e3) {}
}

function 找抽獎按鈕(timeoutMs) {
    var 截止 = Date.now() + timeoutMs;
    while (Date.now() < 截止) {
        if (!running) return null;
        var w = text(抽獎按鈕文字).findOnce();
        if (!w) w = textContains(抽獎按鈕文字).findOnce();
        if (!w) w = desc(抽獎按鈕文字).findOnce();
        if (w) return w;
        sleep(掃描間隔秒數 * 1000);
    }
    return null;
}
// 往上找「可點」的父層；找不到就回傳自己
function 找可點父層(w) {
    var p = w;
    for (var i = 0; i < 6 && p; i++) {
        try { if (p.clickable()) return p; } catch (e) {}
        p = p.parent();
    }
    return w;
}
// 用座標硬點 w 的中心（LINE 一定收得到）
function 座標點(w) {
    try {
        var b = w.bounds();
        return click(b.centerX(), b.centerY());
    } catch (e) { return false; }
}
// 等「參加抽獎」從畫面消失，代表點擊真的生效、頁面有在反應
// 回傳 true=已消失(成功)，false=等到逾時還在
function 等按鈕消失(timeoutMs) {
    var 截止 = Date.now() + timeoutMs;
    while (Date.now() < 截止) {
        if (!running) return true;
        if (!textContains(抽獎按鈕文字).findOnce() && !desc(抽獎按鈕文字).findOnce()) return true;
        sleep(60);
    }
    return false;
}
function 點它(w) {
    // 1) 先點可點父層（真正的按鈕通常是文字的父容器）
    var target = 找可點父層(w);
    try { target.click(); } catch (e) {}
    // 點完立刻偵測按鈕是否消失，一消失就馬上回去開下一個，不死等
    if (等按鈕消失(確認消失最久秒數 * 1000)) return;
    // 2) 還在 → 用座標硬點一次文字中心（LINE 一定收得到），再等一下
    座標點(w);
    等按鈕消失(確認消失最久秒數 * 1000);
}

// ============ 啟動 ============
loadData();
