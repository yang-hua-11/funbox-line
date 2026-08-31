@echo off
chcp 65001 >nul
REM ============================================================
REM  一鍵更新 + 上傳：抓最新連結 -> 重做 index.html -> 傳上 GitHub
REM  點兩下這個檔就好。第一次執行會跳出瀏覽器要你登入 GitHub 授權。
REM ============================================================
setlocal
cd /d "%~dp0"

echo ============================================
echo [1/4] 下載並解析最新抽選連結...
echo ============================================
python extract.py
if errorlevel 1 goto fail

echo.
echo ============================================
echo [2/4] 產生 index.html 與清單...
echo ============================================
python build.py
if errorlevel 1 goto fail

echo.
echo ============================================
echo [3/4] 記錄變更...
echo ============================================
git add index.html template.html data.json extract.py build.py validate.py update.bat deploy.bat checklist.txt checklist.csv .gitignore
REM 若沒有任何變更，git commit 會回傳錯誤，這裡吞掉不當成失敗
git commit -m "更新抽選連結 %date% %time%"
if errorlevel 1 (
  echo （沒有偵測到變更，或已經是最新，略過上傳。）
  goto done
)

echo.
echo ============================================
echo [4/4] 上傳到 GitHub...
echo ============================================
git branch -M main
git push -u origin main
if errorlevel 1 goto pushfail

:done
echo.
echo ============================================
echo  完成！約 1 分鐘後，手機重新整理即可看到最新資料：
echo  https://yang-hua-11.github.io/funbox-line/
echo ============================================
goto end

:fail
echo.
echo [錯誤] 抓資料或產生網頁失敗。請確認網路正常、Python 有安裝。
goto end

:pushfail
echo.
echo [錯誤] 上傳失敗。
echo  - 若跳出登入視窗，請完成 GitHub 登入後再點一次本檔。
echo  - 若顯示衝突(rejected)，請把這個訊息截圖問 Kiro。
goto end

:end
echo.
pause
endlocal
