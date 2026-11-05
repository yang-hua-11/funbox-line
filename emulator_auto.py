# -*- coding: utf-8 -*-
"""
Funbox 陀螺 LINE 抽選 — 電腦端「多開模擬器平行抽」版（MuMu 12 + ADB + uiautomator2）
================================================================================
在電腦上同時控制多個模擬器實例，每個實例登入不同 LINE 帳號，平行把抽選連結抽完。

【前置需求（只做一次）】
  1. 裝好 MuMu 模擬器 12，用多開器開 3~5 個實例。
  2. 每個實例：設定 → 開啟「允許 ADB 連線」；裝 LINE、登入不同帳號、加好友。
  3. 本機已安裝：adb（本專案在 ../android-tools）、Python 套件 uiautomator2。

【用法】
  先確認模擬器都開著、LINE 都在前景，然後：
      python emulator_auto.py                # 自動偵測所有實例，全部連結平均分配
      python emulator_auto.py --list         # 只列出目前連得到的模擬器，不執行
      python emulator_auto.py --city 台北市  # 只抽指定縣市（可用來分流）
      python emulator_auto.py --max 2        # 最多用前 2 個模擬器

【運作方式】
  - 用 adb 偵測所有已連線的模擬器序號（含 MuMu 常見埠號）。
  - 讀 data.json 的所有連結，去重後平均分配給各模擬器。
  - 每個模擬器各一條執行緒：adb 開連結 → 偵測「參加抽獎」→ 點擊 → 換下一個。
  - 偵測按鈕「出現就點、點完消失就換下一個」，不固定空等（跟手機高速版同理）。
"""

import os
import sys
import json
import time
import argparse
import threading
import subprocess

# Windows 終端機預設編碼常是 cp1252，印中文會爆 UnicodeEncodeError。
# 強制把 stdout/stderr 改成 UTF-8，確保中文訊息正常顯示。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
RESOLVED = os.path.join(HERE, "resolved_links.json")  # 預解析後的加速清單（liff 網址）

# adb 執行檔：優先用本專案旁邊 android-tools 裡的，找不到就用系統 PATH 的 adb
ADB_LOCAL = os.path.join(HERE, "..", "android-tools", "platform-tools", "adb.exe")
ADB = ADB_LOCAL if os.path.exists(ADB_LOCAL) else "adb"

# ============ 設定（通常不用改） ============
LINE_PACKAGE       = "jp.naver.line.android"  # LINE App 的套件名，連結強制用它開（不要丟給瀏覽器）
# 抽選按鈕可能的文字（不同活動/語言用字不同）。程式會依序找，哪個出現就點哪個。
# 若你實際看到的按鈕字不在這裡，加進這個清單即可。
抽獎按鈕候選 = [
    "參加抽獎", "參加抽選", "參加",
    "立即參加", "立即抽獎", "我要參加",
    "抽選に参加", "応募する", "応募",
    "領取", "兌換", "領取優惠券",
]
# 「已經抽過/沒中」會出現的字 → 看到這些就直接判定這個連結結束，不用再等按鈕
已結束文字 = ["沒有熱中", "沒有熱", "可惜", "已使用", "已參加", "已抽過", "查看我的優惠券"]
等按鈕最久秒數     = 4.0          # 一個連結最多等幾秒還沒出現按鈕就跳過
確認消失最久秒數   = 1.2          # 點完後最多等幾秒確認按鈕消失（消失=成功，立刻換下一個）
掃描間隔秒數       = 0.1          # 多久掃一次按鈕
下一個前等秒數     = 0.1          # 開下一個連結前的極短緩衝

# MuMu 12 常見的多開 adb 埠號（第 N 個實例 = 16384 + 32*N）。找不到時用來主動嘗試連線。
MUMU_PORTS = [16384 + 32 * i for i in range(0, 8)]
# 其他模擬器常見埠號（雷電 5555/5557...、夜神 62001...），一併嘗試
EXTRA_PORTS = [5555, 5557, 5559, 5561, 62001, 62025, 21503]


def adb(*args, serial=None, timeout=30):
    """執行一次 adb 指令，回傳 (returncode, stdout 字串)。"""
    cmd = [ADB]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"


def 嘗試連線所有埠():
    """主動對常見模擬器埠號下 adb connect，讓它們出現在 devices 清單。"""
    for port in MUMU_PORTS + EXTRA_PORTS:
        adb("connect", "127.0.0.1:%d" % port, timeout=5)


def 列出模擬器():
    """回傳目前狀態為 device 的序號清單。"""
    嘗試連線所有埠()
    code, out = adb("devices")
    devices = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def 讀連結(city_filter=None):
    """
    讀出所有抽選連結，去重。回傳 [{url,name,p}]。
    優先用 resolved_links.json 的 liff 加速網址（跳過 lin.ee 跳轉，快很多）；
    找不到該檔才退回 data.json 的原始 lin.ee 網址。
    """
    # 1) 優先：預解析後的加速清單
    if os.path.exists(RESOLVED):
        try:
            data = json.load(open(RESOLVED, encoding="utf-8"))
            out, seen = [], set()
            for link in data.get("links", []):
                if city_filter and link.get("city") != city_filter:
                    continue
                # 用解析後的 liff 網址；沒有就退回原始 lin.ee
                u = link.get("resolved") or link.get("url")
                if not u or u in seen:
                    continue
                seen.add(u)
                out.append({"url": u, "name": link.get("name", ""), "p": link.get("p", "")})
            if out:
                liff = sum(1 for x in out if x["url"].startswith("https://liff.line.me"))
                print("使用加速清單 resolved_links.json（%d 連結，其中 %d 個 liff 加速網址）"
                      % (len(out), liff))
                return out
        except Exception as e:
            print("讀 resolved_links.json 失敗，改用 data.json：%s" % e)

    # 2) 退回：原始 data.json
    print("未找到加速清單，使用原始 data.json（lin.ee，速度較慢）。"
          "建議先跑：python resolve_links.py")
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
            out.append({"url": u, "name": s.get("name", ""), "p": it.get("p", "")})
    return out


def 平均分配(links, n):
    """把 links 輪流分給 n 個桶子（round-robin），讓各模擬器量平均。"""
    buckets = [[] for _ in range(n)]
    for i, link in enumerate(links):
        buckets[i % n].append(link)
    return buckets


def 連模擬器(serial):
    """用 uiautomator2 連上一個模擬器，回傳 device 物件。"""
    import uiautomator2 as u2
    return u2.connect(serial)


def 找並點按鈕(d):
    """在單一模擬器上：等「參加抽獎」出現→點→等它消失。回傳 True=成功點到。"""
    截止 = time.time() + 等按鈕最久秒數
    btn = None
    while time.time() < 截止:
        # 文字完全相符或包含；再退而求其次找 description
        el = d(text=抽獎按鈕文字)
        if not el.exists:
            el = d(textContains=抽獎按鈕文字)
        if el.exists:
            btn = el
            break
        time.sleep(掃描間隔秒數)
    if btn is None:
        return False
    # 點擊：先用元件 click，收不到時 uiautomator2 也會退回座標點擊
    try:
        btn.click()
    except Exception:
        try:
            b = btn.info["bounds"]
            d.click((b["left"] + b["right"]) // 2, (b["top"] + b["bottom"]) // 2)
        except Exception:
            pass
    # 等按鈕消失＝頁面有反應＝視為成功
    截止2 = time.time() + 確認消失最久秒數
    while time.time() < 截止2:
        if not d(textContains=抽獎按鈕文字).exists:
            return True
        time.sleep(0.06)
    # 還在 → 再補點一次
    try:
        btn.click()
    except Exception:
        pass
    return True


def 開連結(serial, url):
    """
    用 adb 叫模擬器開啟連結。關鍵：強制指定用 LINE App 開（-p LINE_PACKAGE），
    否則系統會丟給瀏覽器，卡在「下載LINE / 在LINE中打開」中轉頁，根本進不去抽選。
    """
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
        "-d", url, "-p", LINE_PACKAGE, serial=serial, timeout=15)


def 跑一台(serial, links, 統計, lock):
    """單一模擬器的工作執行緒：把分到的連結一個個抽完。"""
    try:
        d = 連模擬器(serial)
    except Exception as e:
        with lock:
            print("[%s] 連線失敗，跳過：%s" % (serial, e))
            統計[serial] = {"ok": 0, "skip": len(links), "err": str(e)}
        return

    成功 = 跳過 = 0
    total = len(links)
    for i, link in enumerate(links, 1):
        開連結(serial, link["url"])
        got = 找並點按鈕(d)
        if got:
            成功 += 1
            tag = "OK  "
        else:
            跳過 += 1
            tag = "SKIP"
        with lock:
            print("[%s] (%d/%d) %s %s %s" %
                  (serial, i, total, tag, link["name"], link["p"]))
        time.sleep(下一個前等秒數)

    with lock:
        統計[serial] = {"ok": 成功, "skip": 跳過}
        print("[%s] 完成：成功 %d、跳過 %d" % (serial, 成功, 跳過))


def main():
    ap = argparse.ArgumentParser(description="模擬器多開平行抽")
    ap.add_argument("--list", action="store_true", help="只列出連得到的模擬器")
    ap.add_argument("--city", default=None, help="只抽指定縣市")
    ap.add_argument("--max", type=int, default=0, help="最多使用幾個模擬器（0=全部）")
    args = ap.parse_args()

    print("使用 adb：%s" % ADB)
    devices = 列出模擬器()
    if not devices:
        print("找不到任何模擬器。請確認：")
        print("  1. MuMu 模擬器已開啟（至少一個實例）")
        print("  2. 實例設定裡已開啟『允許 ADB 連線』")
        print("  3. 稍等模擬器完全開機後再執行")
        return 1

    print("偵測到 %d 個模擬器：" % len(devices))
    for s in devices:
        print("   -", s)
    if args.list:
        return 0

    if args.max and args.max < len(devices):
        devices = devices[:args.max]
        print("依 --max 限制，使用前 %d 個" % len(devices))

    links = 讀連結(args.city)
    if not links:
        print("data.json 裡沒有可抽的連結（city 篩選？）")
        return 1
    print("共 %d 個連結，分配給 %d 個模擬器平行抽" % (len(links), len(devices)))

    buckets = 平均分配(links, len(devices))
    統計, lock, threads = {}, threading.Lock(), []
    for serial, bucket in zip(devices, buckets):
        print("   %s ← %d 個連結" % (serial, len(bucket)))
        t = threading.Thread(target=跑一台, args=(serial, bucket, 統計, lock))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    print("\n=========== 全部完成 ===========")
    tot_ok = tot_skip = 0
    for serial in devices:
        r = 統計.get(serial, {})
        tot_ok += r.get("ok", 0)
        tot_skip += r.get("skip", 0)
        print("  %s：成功 %d、跳過 %d%s" %
              (serial, r.get("ok", 0), r.get("skip", 0),
               ("、錯誤 " + r["err"]) if r.get("err") else ""))
    print("  合計：成功 %d、跳過 %d" % (tot_ok, tot_skip))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
