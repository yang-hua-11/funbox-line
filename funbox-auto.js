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
var 抽獎按鈕文字     = "參加抽獎";  // 官方若改字（例如「參加」「應募」），改這裡
var 等按鈕最久秒數   = 12;          // 一個連結最多等幾秒還沒出現按鈕就跳過
var 點完停留秒數     = 1.2;         // 點下去後停多久再開下一個
var 開頁面後等秒數   = 0.8;         // 開連結後先等一下讓 LINE 起來
var STORAGE_NAME   = "funbox_auto"; // 存已抽記錄用
// ==========================================

var storage = storages.create(STORAGE_NAME);

// 全域資料
var DATA = null;        // 抓下來的 data.json
var STORES = [];        // 門市陣列
var CITIES = [];        // 縣市清單
var CODES = [];         // 型號清單
var selCities = {};     // 已選縣市
var selCodes = {};      // 已選型號
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
    <vertical padding="12">
        <text textSize="18sp" textColor="#1f3f66" textStyle="bold">Funbox 陀螺 · 全自動連抽</text>
        <text id="status" textSize="12sp" textColor="#6b7480" marginTop="2">載入資料中…</text>

        <input id="kw" hint="搜尋型號或門市，例如 UX-21、忠孝" textSize="15sp" marginTop="8"/>

        <text textSize="13sp" textColor="#6b7480" textStyle="bold" marginTop="6">縣市</text>
        <ScrollView android:scrollbars="none" marginTop="2">
            <horizontal id="cityChips"/>
        </ScrollView>

        <text textSize="13sp" textColor="#6b7480" textStyle="bold" marginTop="8">型號</text>
        <ScrollView android:scrollbars="none" marginTop="2">
            <horizontal id="codeChips"/>
        </ScrollView>

        <horizontal marginTop="10" gravity="center_vertical">
            <checkbox id="skipDone" checked="true"/>
            <text textSize="14sp" marginLeft="4">排除今天已抽</text>
        </horizontal>

        <text id="count" textSize="15sp" textColor="#06c755" textStyle="bold" marginTop="10">—</text>

        <button id="start" style="Widget.AppCompat.Button.Colored" marginTop="10">▶ 開始自動抽</button>
        <button id="reset" style="Widget.AppCompat.Button.Borderless" marginTop="2">清除今天的已抽記錄</button>
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
    var citySeen = {}, codeSeen = {};
    CITIES = []; CODES = [];
    STORES.forEach(function (s) {
        if (!citySeen[s.city]) { citySeen[s.city] = true; CITIES.push(s.city); }
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
}

// ============ 篩選晶片 ============
function makeChip(label, on, onTap) {
    var v = ui.inflate(
        <text padding="10 6" margin="0 4 0 0" textSize="13sp"/>, ui.cityChips, false);
    v.setText(label);
    styleChip(v, on);
    v.on("click", onTap);
    return v;
}
function styleChip(v, on) {
    v.setBackgroundColor(colors.parseColor(on ? "#1f3f66" : "#eef0f2"));
    v.setTextColor(colors.parseColor(on ? "#ffffff" : "#3d444c"));
}
function anyOn(o) { for (var k in o) { if (o[k]) return true; } return false; }

function renderChips() {
    // 縣市
    ui.cityChips.removeAllViews();
    var allCity = makeChip("全部", !anyOn(selCities), function () {
        selCities = {}; renderChips(); updateCount();
    });
    ui.cityChips.addView(allCity);
    CITIES.forEach(function (c) {
        var chip = makeChip(c, !!selCities[c], function () {
            selCities[c] = !selCities[c]; renderChips(); updateCount();
        });
        ui.cityChips.addView(chip);
    });

    // 型號
    ui.codeChips.removeAllViews();
    var allCode = ui.inflate(<text padding="10 6" margin="0 4 0 0" textSize="13sp"/>, ui.codeChips, false);
    allCode.setText("全部");
    styleChip(allCode, !anyOn(selCodes));
    allCode.on("click", function () { selCodes = {}; renderChips(); updateCount(); });
    ui.codeChips.addView(allCode);
    CODES.forEach(function (c) {
        var chip = ui.inflate(<text padding="10 6" margin="0 4 0 0" textSize="13sp"/>, ui.codeChips, false);
        chip.setText(c);
        styleChip(chip, !!selCodes[c]);
        chip.on("click", function () { selCodes[c] = !selCodes[c]; renderChips(); updateCount(); });
        ui.codeChips.addView(chip);
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
    var cityOn = anyOn(selCities), codeOn = anyOn(selCodes);
    var skip = ui.skipDone.isChecked();
    var out = [], seen = {};
    STORES.forEach(function (s) {
        if (cityOn && !selCities[s.city]) return;
        s.items.forEach(function (it) {
            var c = it.c || "其他";
            if (codeOn && !selCodes[c]) return;
            if (!matchKw(s, it)) return;
            var k = itemKey(s, it);
            if (skip && isToday(k)) return;
            if (!it.u || seen[it.u]) return;
            seen[it.u] = 1;
            out.push({ url: it.u, key: k, name: s.name, p: it.p });
        });
    });
    return out;
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
        var 成功 = 0, 跳過 = 0;
        for (var i = 0; i < list.length; i++) {
            if (!running) break;
            var item = list[i];
            var 序 = "(" + (i + 1) + "/" + list.length + ") ";
            ui.run(function () { ui.status.setText(序 + item.name + " " + item.p); });

            app.openUrl(item.url);
            sleep(開頁面後等秒數 * 1000);

            var btn = 找抽獎按鈕(等按鈕最久秒數 * 1000);
            if (btn) {
                點它(btn);
                markDone(item.key);
                成功++;
                sleep(點完停留秒數 * 1000);
            } else {
                跳過++;
            }
            home();
            sleep(500);
        }
        running = false;
        ui.run(function () {
            ui.status.setText("抽完了：成功 " + 成功 + "、跳過 " + 跳過);
            updateCount();
        });
        toast("抽完了！成功 " + 成功 + "、跳過 " + 跳過);
    });
}

// 切回 App 按返回 → 停止自動抽
ui.emitter.on("back_pressed", function () {
    if (running) { running = false; toast("已停止"); }
});

function 找抽獎按鈕(timeoutMs) {
    var 截止 = Date.now() + timeoutMs;
    while (Date.now() < 截止) {
        if (!running) return null;
        var w = text(抽獎按鈕文字).findOnce();
        if (!w) w = textContains(抽獎按鈕文字).findOnce();
        if (!w) w = desc(抽獎按鈕文字).findOnce();
        if (w) return w;
        sleep(400);
    }
    return null;
}
function 點它(w) {
    try { if (w.click()) return; } catch (e) {}
    try { var b = w.bounds(); click(b.centerX(), b.centerY()); }
    catch (e) {}
}

// ============ 啟動 ============
loadData();
