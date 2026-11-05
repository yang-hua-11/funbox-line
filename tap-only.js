"auto";
/**
 * 極簡「只點參加抽獎」腳本（搭配 FunboxDraw APK 使用）
 * ============================================================
 * 分工：APK 負責開抽選畫面、換下一個；這支腳本只做一件事——
 *       畫面上一出現「參加抽獎」按鈕，就立刻點下去。
 *
 * 用法：
 *   1. 先在 AutoX 開好「無障礙服務」權限。
 *   2. 執行這支腳本（會一直盯著畫面）。
 *   3. 再開 FunboxDraw APK 開始跑。
 *      APK 開到抽選頁、按鈕出現，這支腳本就自動點掉。
 *   4. 要停：切回 AutoX 畫面，模擬器按 ESC（返回）即可停止腳本。
 */

var 抽獎按鈕文字 = "參加抽獎";  // 要點的按鈕文字
var 掃描間隔毫秒 = 60;          // 多久掃一次畫面（越小抓越快）
var 等消失最久毫秒 = 2500;      // 點完後最多等幾毫秒確認按鈕消失（消失=已送出，才找下一顆）

// 確認無障礙服務已開（沒開就提示並開設定頁）
if (!auto.service) {
    toast("請先開啟 AutoX 的無障礙服務");
    app.startActivity({ action: "android.settings.ACCESSIBILITY_SETTINGS" });
    exit();
}

console.show();
console.log("啟動：一出現「" + 抽獎按鈕文字 + "」就自動點");
toast("只點參加抽獎：已啟動");

// 往上找可點的父層（真正的按鈕通常是文字的父容器）
function 找可點父層(w) {
    var p = w;
    for (var i = 0; i < 6 && p; i++) {
        try { if (p.clickable()) return p; } catch (e) {}
        p = p.parent();
    }
    return w;
}
// 座標硬點中心（LINE 的 WebView 一定收得到）
function 座標點(w) {
    try {
        var b = w.bounds();
        return click(b.centerX(), b.centerY());
    } catch (e) { return false; }
}
// 找按鈕：文字完全相符 → 包含 → 無障礙描述
function 找按鈕() {
    var w = text(抽獎按鈕文字).findOnce();
    if (!w) w = textContains(抽獎按鈕文字).findOnce();
    if (!w) w = desc(抽獎按鈕文字).findOnce();
    return w;
}
// 畫面上還有沒有「參加抽獎」
function 還在() {
    return !!(text(抽獎按鈕文字).findOnce() || textContains(抽獎按鈕文字).findOnce() || desc(抽獎按鈕文字).findOnce());
}
// 等「參加抽獎」消失（代表已送出、畫面換了）。回傳 true=消失、false=逾時還在
function 等消失() {
    var 截止 = Date.now() + 等消失最久毫秒;
    while (Date.now() < 截止) {
        if (!還在()) return true;
        sleep(50);
    }
    return false;
}

var 點擊次數 = 0;
while (true) {
    var w = 找按鈕();
    if (w) {
        // 先點可點父層，再座標硬點一次，雙保險
        var target = 找可點父層(w);
        try { target.click(); } catch (e) {}
        座標點(w);
        點擊次數++;
        console.log("已點第 " + 點擊次數 + " 次（送出中…）");
        // 關鍵：點完等這顆「參加抽獎」消失，才去找下一顆，避免在原地狂點同一顆
        等消失();
    } else {
        sleep(掃描間隔毫秒);
    }
}
